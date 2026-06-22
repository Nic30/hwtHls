#include <hwtHls/llvm/Transforms/slicesMerge/slicesMerge.h>

#include <llvm/Transforms/InstCombine/InstCombine.h>
#undef DEBUG_TYPE

#include <hwtHls/llvm/Transforms/slicesMerge/slicesMergeCombiner.h>

#include <map>
#include <sstream>

#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/MemorySSA.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Dominators.h>
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <llvm/IR/Verifier.h>
#endif
//#include <llvm/Transforms/Scalar/NewGVN.h>
#include <llvm/Transforms/Scalar/GVN.h>
#include <llvm/Support/DebugCounter.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
using namespace llvm;
using namespace std;

STATISTIC(NumWorklistIterations,
		"Number of instruction combining iterations performed");

STATISTIC(NumCombined, "Number of insts combined");
STATISTIC(NumConstProp, "Number of constant folds");
STATISTIC(NumDeadInst, "Number of dead inst eliminated");

DEBUG_COUNTER(VisitCounter, "slices-merge-visit",
		"Controls which instructions are visited");

namespace hwtHls {

SlicesMergeCombiner::SliceDict findSlices(Function &F) {
	SlicesMergeCombiner::SliceDict slices;
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			auto sliceItem = OffsetWidthValue::fromValue(&I);
			if (!(sliceItem.isIdentity() && sliceItem.value == &I)
					&& isa<Instruction>(sliceItem.value)) {
				auto curSlices = slices.find(
						{ sliceItem.value, sliceItem.offset });
				if (curSlices == slices.end()) {
					slices[ { sliceItem.value, sliceItem.offset }] = { &I };
				}
			}
			//if (auto *sext = dyn_cast<SExtInst>(&I)) {
			//	auto *bitVector = sext->getOperand(0);
			//	size_t offsetInt = bitVector->getType()->getIntegerBitWidth()
			//			- 1;
			//	auto curSlices = slices.find( { bitVector, offsetInt });
			//	if (curSlices == slices.end()) {
			//		slices[ { bitVector, offsetInt }] = { &I };
			//	}
			//}
		}
	}
	return slices;
}

PreservedAnalyses SlicesMergePass::run(Function &F,
		FunctionAnalysisManager &AM) {
	//verifyAfterUpdate(F, nullptr, "got corrupted function");
	//F.dump();
	AM.getResult<TargetLibraryAnalysis>(F); // for getBestSimplifyQuery
	AM.getResult<DominatorTreeAnalysis>(F); // for getBestSimplifyQuery
	auto SQ = getBestSimplifyQuery(AM, F);
	InstructionWorklist Worklist;
	bool anyChange = false;
	auto &DL = F.getParent()->getDataLayout();
	/// Builder - This is an IRBuilder that automatically inserts new
	/// instructions into the worklist when they are created.
	IRBuilder<TargetFolder, IRBuilderCallbackInserter> Builder(F.getContext(),
			TargetFolder(DL),
			IRBuilderCallbackInserter([&Worklist](Instruction *I) {
				Worklist.add(I);
			}));
	ReversePostOrderTraversal<BasicBlock*> RPOT(&F.front());
	// Iterate while there is work to do.
	unsigned Iteration = 0;
	for (;;) {
		++Iteration;
		if (Iteration > MaxIterations) {
			LLVM_DEBUG(
					dbgs() << "\n\n[" DEBUG_TYPE_SHORT "] Iteration limit #" << MaxIterations << " on " << F.getName() << " reached; stopping without verifying fixpoint\n");
			break;
		}

		++NumWorklistIterations;
		LLVM_DEBUG(
				dbgs() << "\n\n" DEBUG_TYPE_SHORT " #" << Iteration << " on " << F.getName() << "\n");
		SlicesMergeCombiner::SliceDict slices = findSlices(F);
		SlicesMergeCombiner IC(Builder, SQ, Worklist, F, NumCombined,
				NumConstProp, NumDeadInst, VisitCounter, slices, _dbgIrInstrCombineChangeCallbackFn);

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		IC.assertSlicesConsistency();
#endif
		for (BasicBlock &BB : F) {
			if (BB.phis().empty())
				continue;
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			IC.assertSlicesConsistency();
#endif
			if (IC.phiShiftPatternRewrite(BB)) {
				IC.onChangeCallback("phiShiftPatternRewrite", *BB.getParent());
				IC.MadeIRChange = true; 	
			}

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			IC.verifyAfterUpdate("phiShiftPatternRewrite corrupted function",
					nullptr);
			IC.assertSlicesConsistency();
#endif
		}
		//errs() << "SlicesMergePass " << Iteration << " after phiShiftPatternRewrite: " << "\n";
		//for (auto& BB: F) {
		//	errs() << BB.getName() << ": ";
		//	for (auto &I: BB) {
		//		errs() << "  " << &I << " " << I<< "\n";
		//	}
		//}

		bool MadeChangeInThisIteration = IC.prepareWorklist(RPOT);
		MadeChangeInThisIteration |= IC.run();
		if (Iteration > 1 && !MadeChangeInThisIteration)
			break;
		// discard all analysis used by NewGVNPass
		//PreservedAnalyses _PA;
		//_PA.preserve<AssumptionAnalysis>();
		//_PA.preserve<DominatorTreeAnalysis>();
		//_PA.preserve<TargetLibraryAnalysis>();
		//_PA.preserve<AAManager>();
		//_PA.preserve<MemorySSAAnalysis>();
		//AM.invalidate(F, _PA);
		InstCombinePass ic;
		auto ICres = ic.run(F, AM);
		if (!ICres.areAllPreserved()) {
			IC.onChangeCallback("SlicesMergePass - InstCombinePass", F);
			MadeChangeInThisIteration = true;
		}
		GVNPass gnv;
		//NewGVNPass gnv;
		auto gnvRes = gnv.run(F, AM);
		if (!gnvRes.areAllPreserved()) {
			IC.onChangeCallback("SlicesMergePass - GVNPass", F);
			MadeChangeInThisIteration = true;
		}
		anyChange |= MadeChangeInThisIteration;
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		IC.verifyAfterUpdate("corrupted function", nullptr);
#endif
		if (!MadeChangeInThisIteration)
			break;

		if (Iteration > MaxIterations) {
			report_fatal_error(
					"Instruction Combining did not reach a fixpoint after "
							+ Twine(MaxIterations) + " iterations");
		}
	}

	if (anyChange) {
		PreservedAnalyses PA;
		PA.preserve<DominatorTreeAnalysis>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}
}
}
