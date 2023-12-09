#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitwidthReducePass.h>

#include <algorithm>

#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/GlobalsModRef.h>

#include <hwtHls/llvm/Transforms/bitwidthReducePass/constBitPartsAnalysis.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitPartsUseAnalysis.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitRewriter.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/utils/bitSliceFlattening.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>


using namespace llvm;

// #include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
// #include <llvm/IR/Verifier.h>
// #define DBG_VERIFY_AFTER_MODIFICATION

namespace hwtHls {

static bool runBitwidthReduction(Function &F, TargetLibraryInfo *TLI) {
//#ifdef DBG_VERIFY_AFTER_MODIFICATION
//	{
//		std::string errTmp = "hwtHls::BitwidthReductionPass received corrupted function ";
//		llvm::raw_string_ostream errSS(errTmp);
//		errSS << F.getName().str();
//		errSS << "\n";
//		if (verifyModule(*F.getParent(), &errSS)) {
//			throw std::runtime_error(errSS.str());
//		}
//	}
//#endif

	ConstBitPartsAnalysisContext A;
	std::list<Instruction*> Worklist;
	bool didModify = false;
	// discover all value constraints
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			A.visitValue(&I);
			Worklist.push_back(&I);
		}
	}
	// transitively propagate constant bits until something changes (def -> use)
	while (!Worklist.empty()) {
		Instruction *I = Worklist.front();
		Worklist.pop_front();
		if (A.updateInstruction(I)) {
			for (auto user : I->users()) {
				if (auto *u = dyn_cast<Instruction>(user)) {
					if (A.constraints.find(u) != A.constraints.end()
							&& std::find(Worklist.begin(), Worklist.end(), u)
									== Worklist.end()) {
						Worklist.push_back(u);
					}
				}
			}
		}
	}

	// use the knowledge about bits constant values to resolve truly used bits (use -> def)
	BitPartsUseAnalysisContext AU(A.constraints);
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (isa<StoreInst>(&I)
					|| (isa<LoadInst>(&I)
							&& dyn_cast<LoadInst>(&I)->isVolatile())
					|| I.isTerminator() || I.isExceptionalTerminator()) { // || dyn_cast<BranchInst>(&I) || dyn_cast<SwitchInst>(&I)
				AU.updateUseMaskEntirelyUsed(&I);
			}
		}
	}

	// errs() << "BitwidthReductionPass::run runBitwidthReduction\n";
	// for (const auto& c: A.constraints) {
	// 	if (c.first->getType()->isIntegerTy() && !isa<ConstantInt>(c.first)) {
	// 		errs() << c.first << " " << *c.first << "\n";
	// 		errs() << "    " << *c.second << "\n";
	// 	}
	// }
	// F.dump();
	// writeCFGToDotFile(F, "before.BitwidthReducePass.dot", nullptr, nullptr);
	BitPartsRewriter rew(A.constraints);
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			rew.rewriteIfRequired(&I);
			didModify = true;
		}
	}

	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (auto *PHI = dyn_cast<PHINode>(&I)) {
				rew.rewritePHINodeArgsIfRequired(PHI);
				didModify = true;
			} else {
				break; // no more PHIs in this block
			}
		}
	}
	// DCE
	DceWorklist dce(TLI, nullptr);
	for (BasicBlock &BB : F) {
		for (auto I = BB.begin(); I != BB.end();) {
			if (dce.tryRemoveIfDead(*I, I)) {
				dce.runToCompletition(I);
				didModify = true;
			} else {
				++I;
			}
		}
	}

	// rewriteExtractOnMergeValues + DCE
	IRBuilder<> Builder(&*F.begin()->begin());
	for (BasicBlock &BB : F) {
		for (auto I = BB.begin(); I != BB.end();) {
			if (CallInst *CI = dyn_cast<CallInst>(&*I)) {
				if (IsBitRangeGet(CI)) {
					if (rewriteExtractOnMergeValues(Builder, CI) != CI
							&& dce.tryRemoveIfDead(*I, I)) {
						dce.runToCompletition(I);
						didModify = true;
						continue;
					}
				}
			}
			++I;
		}
	}
// 	writeCFGToDotFile(F, "after.BitwidthReducePass.dot", nullptr, nullptr);
// #ifdef DBG_VERIFY_AFTER_MODIFICATION
// 	{
// 		std::string errTmp = "hwtHls::BitwidthReductionPass corrupted function ";
// 		llvm::raw_string_ostream errSS(errTmp);
// 		errSS << F.getName().str();
// 		errSS << "\n";
// 		if (verifyModule(*F.getParent(), &errSS)) {
// 			throw std::runtime_error(errSS.str());
// 		}
// 	}
// #endif
	return didModify;
}

llvm::PreservedAnalyses BitwidthReductionPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);

	if (!runBitwidthReduction(F, TLI)) {
		return PreservedAnalyses::all();
	}

	auto PA = PreservedAnalyses();
	PA.preserve<GlobalsAA>();
	PA.preserveSet<CFGAnalyses>();
	return PA;
}

}
