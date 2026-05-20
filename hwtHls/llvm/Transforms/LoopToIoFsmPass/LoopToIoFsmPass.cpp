#include <hwtHls/llvm/Transforms/LoopToIoFsmPass/LoopToIoFsmPass.h>

#include <llvm/ADT/STLExtras.h>
#include <stdexcept>

#include <llvm/ADT/PriorityWorklist.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/Analysis/ProfileSummaryInfo.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CFG.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Transforms/Scalar/LoopUnrollPass.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/LoopSimplify.h>
#include <llvm/Transforms/Utils/LoopUtils.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>
#include <llvm/Transforms/Utils/UnrollLoop.h>

#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/liveness.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/LoopToIoFsmPass/normalizeLoops.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/demoteAllLiveVarsOnLaneCrossingToTmpAlloca.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/splitBBsOnIOAccess.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/sinkStreamWritesInLoop.h>
#include <hwtHls/llvm/Transforms/utils/loopHwtHlsMetadata.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

// #include <llvm/IR/Verifier.h>
#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

#define DEBUG_TYPE "StreamSegmentLoopUnroll"
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(X) { X; }

using namespace llvm;

namespace hwtHls {

// based on llvm LoopUnrollPass.cpp tryToUnrollLoop(), StreamLoopUnrollPass
// :attention: invalidates LI, SE

static void setFsmStateBeforeEnteringSection(
	const SmallVector<Instruction *> &IoInstructions, IRBuilder<> &Builder,
	std::unordered_map<BasicBlock *, unsigned int> &entryBlockNumbers,
	IntegerType *&FsmStateTy, AllocaInst *fsmState) {
	// collect section/state numbers and update fsmState before section to
	// section id

	for (auto *I : IoInstructions) {
		auto *BB = I->getParent();
		auto *predBB = BB->getUniquePredecessor();
		assert(BB->begin() == I->getIterator());
		Builder.SetInsertPoint(predBB->getTerminator());
		unsigned nextBlockI = entryBlockNumbers[BB];
		Builder.CreateStore(ConstantInt::get(FsmStateTy, nextBlockI), fsmState);
	}
}

static void collectSectionIds(
	const SmallVector<Instruction *> &IoInstructions,
	std::unordered_map<BasicBlock *, unsigned> &entryBlockNumbers) {
	unsigned i = 0;
	for (auto *I : IoInstructions) {
		auto *BB = I->getParent();
		assert(BB->begin() == I->getIterator());
		entryBlockNumbers[BB] = i++;
	}
}

void rerouteSectionPredecessorToJumpToLatch(
	DomTreeUpdater &DTU, SmallVector<Instruction *> &IoInstructions,
	IRBuilder<> &Builder, BasicBlock *&newLatchBB,
	SmallVector<BasicBlock *> &newHeaderDsts) {
	for (auto *I : IoInstructions) {
		auto *BB = I->getParent();
		assert(BB->begin() == I->getIterator());
		auto *predBB = BB->getUniquePredecessor();
		assert(predBB);
		// predBB br-> newLatchBB
		predBB->getTerminator()->eraseFromParent();
		Builder.SetInsertPoint(predBB);
		Builder.CreateBr(newLatchBB);
		DTU.applyUpdates({
			{DominatorTree::Delete, predBB, BB}, //
			{DominatorTree::Insert, predBB, newLatchBB},
		});
		// :note: for later construction of newHeader sw-> BB
		newHeaderDsts.push_back(BB);
	}
}

void reroutePreheadersToJumpToNewHeaderAndInitFsmSt(
	Loop &L, llvm::BasicBlock *&oldHeader, DomTreeUpdater &DTU,
	IRBuilder<> &Builder, IntegerType *&FsmStateTy, AllocaInst *&fsmState,
	BasicBlock *&newHeaderBB) {
	{
		// reroute preheaders to jump to new header and initialize fsmState to 0
		assert(oldHeader != newHeaderBB);
		SetVector<BasicBlock *> preheaders;
		preheaders.insert_range(predecessors(oldHeader));
		for (auto pred : preheaders) {
			if (L.contains(pred))
				continue;
			pred->getTerminator()->replaceSuccessorWith(oldHeader, newHeaderBB);
			DTU.applyUpdates({
				{DominatorTree::Delete, pred, oldHeader}, //
				{DominatorTree::Insert, pred, newHeaderBB},
			});
			Builder.SetInsertPoint(pred->getTerminator());
			Builder.CreateStore(ConstantInt::get(FsmStateTy, 0), fsmState);
		}
	}
}

static bool tryConvertLoopToIoFsmLoop(
	llvm::Function &F, Loop &L, DominatorTree &DT, LoopInfo &LI,
	ScalarEvolution &SE, const TargetTransformInfo &TTI, AssumptionCache &AC,
	OptimizationRemarkEmitter &ORE, BlockFrequencyInfo *BFI,
	ProfileSummaryInfo *PSI, bool PreserveLCSSA,
	std::vector<AllocaInst *> &tmpAllocas,
	llvm::FunctionAnalysisManager &AMForDebug) {
	auto streamArgI = getOptionalIntHwtHlsLoopAttribute(
		&L, LoopToIoFsmPass::METADATA_NAME_io);
	if (!streamArgI.has_value()) {
		LLVM_DEBUG(dbgs() << "  Loop does not have "
						  << LoopToIoFsmPass::METADATA_NAME_io
						  << " "
							 "Attribute to enable this transformation.\n");
		// loop does not have Attribute to enable this transformation
		return false;
	}
	auto *oldHeader = L.getHeader();
	LLVM_DEBUG(dbgs() << "Stream Segment Loop Unroll: F["
					  << oldHeader->getParent()->getName() << "] Loop %"
					  << oldHeader->getName() << "\n");
	if (!L.isLoopSimplifyForm()) {
		LLVM_DEBUG(
			dbgs()
			<< "  Not unrolling loop which is not in loop-simplify form.\n");
		return false;
	}

	Argument &IoArg = *F.getArg(streamArgI.value());
	llvm::SmallVector<llvm::AllocaInst *> GeneratedAllocas;
	// get stream props for specified IoArg
	StreamChannelProps streamProps =
		findStreamIoPropsInMetadata(F, &IoArg, GeneratedAllocas);
	assert(GeneratedAllocas.empty());

	SE.forgetLoop(&L);
	demoteBlockPHIsToAlloca(tmpAllocas, L);
	// Save loop properties before it is transformed.
	std::optional<MDNode *> llvmLoopMdFollowup = makeFollowupLoopID(
		L.getLoopID(), {LoopToIoFsmPass::METADATA_NAME_followup});
	// MDNode *OrigHwtHlsLoopID = Loop_getHwtHlsLoopID(*L);
	L.setLoopID(nullptr); // temporary delete before CFG modifications
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
	bool ioIsInput;
	SmallVector<BasicBlock *> BBs;
	SmallVector<Instruction *> IoInstructions;
	// :note: verifies all ios are of the same type
	splitBBsOnIOAccess(DTU, LI, L, IoArg, ioIsInput, BBs, IoInstructions,
					   ".ioFsmStBefore");
	if (IoInstructions.empty()) {
		throw std::runtime_error("tryConvertLoopToIoFsmLoop: The loop does not "
								 "contain any load/store to selected IO");
	} else if (IoInstructions.size() == 1) {
		bool isAlreadyInDesiredFormat = false;
		if (ioIsInput) {
			// check if only load is the first instruction in the loop body
			// (phis were separated by splitBBsOnIOAccess, oldHeader is now the block after it)
		 	isAlreadyInDesiredFormat = IoInstructions[0] == &*oldHeader->begin();
		} else {
			if (auto latch = L.getLoopLatch()) {
				auto latchTerm = latch->getTerminator();
				if (latch->begin() != latchTerm->getIterator() && std::next(latchTerm, -1) == IoInstructions[0]) {
					// the store is last (non-branch) instruction in latch
					isAlreadyInDesiredFormat = true;
				}	
			}
		}
		// the loop is already in the format
		if (isAlreadyInDesiredFormat) {
			if (llvmLoopMdFollowup.has_value())
				L.setLoopID(llvmLoopMdFollowup
							.value()); // return id back after cfg modifications
			return false;
		}
	}


	oldHeader = L.getHeader();
	DTU.flush();
#ifndef NDEBUG
	LI.verify(DT);
#endif
	IRBuilder<> Builder(F.getContext());
	fixDublicitCfgEdgesByNewBBInsertion(&DTU, &LI, F);
	DTU.flush();
#ifndef NDEBUG
	assert(DT.verify());
#endif
	writeCFGToDotFile(F, "tmp/LoopToIoFsmPass.1.dot", AMForDebug, false, true);
	std::map<BasicBlock *, SetVector<Instruction *>> allLiveins =
		computeAllLiveins(F, DT);
	demoteAllLiveVarsOnLaneCrossingToTmpAlloca(
		Builder, F, ioIsInput, allLiveins, BBs, IoInstructions, tmpAllocas);
#ifndef NDEBUG
	LI.verify(DT);
#endif
	DTU.flush();
	Builder.SetInsertPoint(F.getEntryBlock().begin());
	auto FsmStateTy = Builder.getIntNTy(log2ceil(IoInstructions.size() + 1));
	auto fsmState = Builder.CreateAlloca(FsmStateTy, nullptr,
										 oldHeader->getName() + ".IoFsmSt");

	// if the original header did not begin with targeted IO instruction
	if (!oldHeader->getSingleSuccessor() ||
		oldHeader->getFirstInsertionPt() !=
			oldHeader->getTerminator()->getIterator() ||
		!is_contained(IoInstructions,
					  &*oldHeader->getSingleSuccessor()->begin())) {
		//      while(1) {
		//         load %i0
		//         %r1 = load %iStream0
		//         %r2 = load %iStream0
		//      }
		//      // to:
		//      st = 0
		//      while(1) {
		//         if (st == 0) { // this part is done there
		//            load %i0
		//         }	 
		//         switch(st) {
		//	       case 0:
		//            %r1 = load %iStream0
		//            st = 1;	   
		//            break;
		//	       case 1:
		//            %r1 = load %iStream0
		//            st = 0;	   
		//            break;
		//         }
		//      }
		//      // instead of:		
		//      st = 0
		//      load %i0
		//      while(1) {
		//         switch(st) {
		//	       case 0:
		//            %r1 = load %iStream0
		//            st = 1;	   
		//            break;
		//	       case 1:
		//            %r1 = load %iStream0
		//            load %i0  
		//            st = 0;	   
		//            break;
		//         }
		//      }
		// [todo] for loads the section between loop header and the first reads
		// 		  needs to be duplicated in preheader
		//        and similarly for stores before exit the "after store-before
		//        exit block section" must be duplicated in every exit block
		// :note: this section is empty if he load is at begin of header block
		// and for store if there is no exit or store is at the end of exiting
		// block
		// [todo] duplication in preheader may be undesired as it generates
		//      the access to IO out of this loop it would be much better 
		//      to group it with the first load.
		//      It is also desired that lanes of this io are aligned with
		//      lanes of other IOs in this loop in the case that the vectorization
		//      will be applied
		//      
		
		
		llvm_unreachable("[todo]");
	}
	
	// assert(DTU.getDomTree().verify());
	// errs() << F << "\n";
	// writeCFGToDotFile(F, "tmp/LoopToIoFsmPass.1.dot", AMForDebug, false, true);

	std::unordered_map<BasicBlock *, unsigned> entryBlockNumbers;
	collectSectionIds(IoInstructions, entryBlockNumbers);

	Builder.SetInsertPoint(F.getEntryBlock().begin());
	setFsmStateBeforeEnteringSection(IoInstructions, Builder, entryBlockNumbers,
									 FsmStateTy, fsmState);
	auto newHeaderBB = BasicBlock::Create(
		F.getContext(), oldHeader->getName() + ".IoFsmHeader", &F, oldHeader);
	L.addBasicBlockToLoop(newHeaderBB, LI);
	L.moveToHeader(newHeaderBB);

	auto newLatchBB = BasicBlock::Create(
		F.getContext(), oldHeader->getName() + ".IoFsmLatch", &F);
	L.addBasicBlockToLoop(newLatchBB, LI);

	SmallVector<BasicBlock *> newHeaderDsts;
	rerouteSectionPredecessorToJumpToLatch(DTU, IoInstructions, Builder,
										   newLatchBB, newHeaderDsts);
	reroutePreheadersToJumpToNewHeaderAndInitFsmSt(
		L, oldHeader, DTU, Builder, FsmStateTy, fsmState, newHeaderBB);
	// newLatchBB br-> newHeaderBB
	BranchInst::Create(newHeaderBB, newLatchBB);
	DTU.applyUpdates({
		{DominatorTree::Insert, newHeaderBB, newLatchBB},
	});

	// construct switch jumping to every io operation region
	auto newHeaderDefDest = BasicBlock::Create(
		F.getContext(), oldHeader->getName() + ".IoFsmDefDest", &F);
	L.addBasicBlockToLoop(newHeaderDefDest, LI);
	new UnreachableInst(F.getContext(), newHeaderDefDest);
	{
		// build switch cases for jumps from header to begins of sections
		Builder.SetInsertPoint(newHeaderBB);
		auto nextStateIVal = Builder.CreateLoad(FsmStateTy, fsmState);
		auto sw = Builder.CreateSwitch(nextStateIVal, newHeaderDefDest);
		SmallVector<DominatorTree::UpdateType> dtUpdates;
		dtUpdates.push_back(
			{DominatorTree::Insert, newHeaderBB, newHeaderDefDest});
		for (auto dstBB : newHeaderDsts) {
			auto sectionId = entryBlockNumbers[dstBB];
			sw->addCase(ConstantInt::get(FsmStateTy, sectionId), dstBB);
			dtUpdates.push_back({DominatorTree::Insert, newHeaderBB, dstBB});
		}
		DTU.applyUpdates(dtUpdates);
		if (ioIsInput) {
			// replace all loads with a single load in the header
			Builder.SetInsertPoint(sw);
			auto *I = IoInstructions[0];
			auto *ld =
				Builder.CreateLoad(I->getType(), &IoArg, I->isVolatile());
			for (auto I : IoInstructions) {
				I->replaceAllUsesWith(ld);
				I->eraseFromParent();
			}
		} else {
			llvm_unreachable("[todo]");
		}
	}

	// errs() << F << "\n";
	// writeCFGToDotFile(F, "tmp/LoopToIoFsmPass.2.dot", AMForDebug, false, false);

	if (llvmLoopMdFollowup.has_value())
		L.setLoopID(llvmLoopMdFollowup
						.value()); // return id back after cfg modifications
	DTU.flush();
	assert(DT.verify());

	return true;
}

const std::string LoopToIoFsmPass::METADATA_NAME_io =
	"hwthls.loop.looptoiofsm.io";
const std::string LoopToIoFsmPass::METADATA_NAME_followup =
	"hwthls.loop.looptoiofsm.followup";

llvm::PreservedAnalyses
LoopToIoFsmPass::run(llvm::Function &F, llvm::FunctionAnalysisManager &AM) {
	// same as LoopUnrollPass::run just with different main function for loop
	// transformation (tryToUnrollStreamLoop)
	auto &LI = AM.getResult<LoopAnalysis>(F);
	// There are no loops in the function. Return before computing other
	// expensive analyses.
	if (LI.empty())
		return PreservedAnalyses::all();

	auto &SE = AM.getResult<ScalarEvolutionAnalysis>(F);
	auto &TTI = AM.getResult<TargetIRAnalysis>(F);
	auto &DT = AM.getResult<DominatorTreeAnalysis>(F);
	auto &AC = AM.getResult<AssumptionAnalysis>(F);
	auto &ORE = AM.getResult<OptimizationRemarkEmitterAnalysis>(F);

	auto &MAMProxy = AM.getResult<ModuleAnalysisManagerFunctionProxy>(F);
	ProfileSummaryInfo *PSI =
		MAMProxy.getCachedResult<ProfileSummaryAnalysis>(*F.getParent());
	auto *BFI = (PSI && PSI->hasProfileSummary())
					? &AM.getResult<BlockFrequencyAnalysis>(F)
					: nullptr;

	bool Changed = normalizeLoopsForUnrolling(LI, DT, &SE, &AC);
	// F.dump();
	// writeCFGToDotFile(F, "tmp/LoopToIoFsmPass.0.dot", AM, false,
	// 		true);
	// Add the loop nests in the reverse order of LoopInfo. See method
	// declaration.
	SmallPriorityWorklist<Loop *, 4> Worklist;
	appendLoopsToWorklist(LI, Worklist);
	std::vector<AllocaInst *> tmpAllocas;
	while (!Worklist.empty()) {
		// Because the LoopInfo stores the loops in RPO, we walk the worklist
		// from back to front so that we work forward across the CFG, which
		// for unrolling is only needed to get optimization remarks emitted in
		// a forward order.
		Loop &L = *Worklist.pop_back_val();
#ifndef NDEBUG
		Loop *ParentL = L.getParentLoop();
#endif

		std::string LoopName = std::string(L.getName());
		// The API here is quite complex to call and we allow to select some
		// flavors of unrolling during construction time (by setting
		// UnrollOpts).
		bool _changed =
			tryConvertLoopToIoFsmLoop(F, L, DT, LI, SE, TTI, AC, ORE, BFI, PSI,
									  /*PreserveLCSSA*/ true, tmpAllocas, AM);
		// DT.verify(DominatorTree::VerificationLevel::Full);
		if (_changed) {
			// SE.forgetLoop(&L);
			SE.forgetAllLoops();
			Changed = true;
		}

		// The parent must not be damaged by unrolling!
#ifndef NDEBUG
		if (_changed && ParentL)
			ParentL->verifyLoop();
#endif
	}

	if (!Changed)
		return PreservedAnalyses::all();

	llvm::PromoteMemToReg(tmpAllocas, DT, &AC);
	if (tmpAllocas.size()) {
		for (auto &BB : F) {
			// :note: llvm-21 PromoteMemToReg somehow generates phis with
			// reversed order of operands according to block predecessors
			sortPhiOperands(BB);
		}
	}
	assert(DT.verify());
	// errs() << "\n";

	// must recompute because rerouteLaneCfgAndSegmentValue currently does not
	// update LI the LI may become invalid if L contains sub loops which are
	// rerouted, they can be potentially merged together or with parent loop or
	// they may become cycle
	PreservedAnalyses PA;
	PA.preserve<DominatorTreeAnalysis>();
	// PA.preserve<LoopAnalysis>();
	// PA.preserve<LoopAnalysisManagerFunctionProxy>();
	// PA.preserve<ScalarEvolutionAnalysis>();
	AM.invalidate(F, PA);
	auto &LI2 = AM.getResult<LoopAnalysis>(F);
	auto &SE2 = AM.getResult<ScalarEvolutionAnalysis>(F);

	// assert(!verifyFunction(F, &errs()));
	// for (auto &L : LI2) {
	//	L->dump();
	//	errs() << "\n";
	//}
	// #ifndef NDEBUG
	//	LI2.verify(DT);
	// #endif
	normalizeLoopsForUnrolling(LI2, DT, &SE2, &AC);
	PA.preserve<LoopAnalysis>();
	PA.preserve<LoopAnalysisManagerFunctionProxy>();
	PA.preserve<ScalarEvolutionAnalysis>();
	// assert(DT.verify());
	// assert(LI2.verify());
	return PA;
	// return getLoopPassPreservedAnalyses();
}

} // namespace hwtHls
