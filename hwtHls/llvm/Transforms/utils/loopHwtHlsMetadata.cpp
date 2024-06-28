#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopInfo.h>
#include <llvm/IR/Constants.h>

using namespace llvm;
namespace hwtHls {

// based on llvm::Loop::getLoopID()
llvm::MDNode* Loop_getHwtHlsLoopID(const llvm::Loop &L) {
	MDNode *LoopID = nullptr;

	// Go through the latch blocks and check the terminator for the metadata.
	SmallVector<BasicBlock*, 4> LatchesBlocks;
	L.getLoopLatches(LatchesBlocks);
	for (BasicBlock *BB : LatchesBlocks) {
		Instruction *TI = BB->getTerminator();
		MDNode *MD = TI->getMetadata("hwthls.loop");

		if (!MD)
			return nullptr;

		if (!LoopID)
			LoopID = MD;
		else if (MD != LoopID)
			return nullptr;
	}
	if (!LoopID || LoopID->getNumOperands() == 0
			|| LoopID->getOperand(0) != LoopID)
		return nullptr;
	return LoopID;
}

// based on llvm::findOptionMDForLoop
llvm::MDNode* findOptionMDForHwtHlsLoop(const llvm::Loop *TheLoop,
		llvm::StringRef Name) {
	return findOptionMDForLoopID(Loop_getHwtHlsLoopID(*TheLoop), Name);
}

// based on llvm::findStringMetadataForLoop()
std::optional<const llvm::MDOperand*> findStringMetadataForHwtHlsLoop(
		const llvm::Loop *TheLoop, llvm::StringRef Name) {
	MDNode *MD = findOptionMDForHwtHlsLoop(TheLoop, Name);
	if (!MD)
		return std::nullopt;
	switch (MD->getNumOperands()) {
	case 1:
		return nullptr;
	case 2:
		return &MD->getOperand(1);
	default:
		llvm_unreachable("loop metadata has 0 or 1 operand");
	}
}
// based on llvm::getOptionalIntLoopAttribute()
std::optional<int> getOptionalIntHwtHlsLoopAttribute(const llvm::Loop *TheLoop,
		llvm::StringRef Name) {
	const MDOperand *AttrMD =
			findStringMetadataForHwtHlsLoop(TheLoop, Name).value_or(nullptr);
	if (!AttrMD)
		return std::nullopt;

	ConstantInt *IntMD = mdconst::extract_or_null<ConstantInt>(AttrMD->get());
	if (!IntMD)
		return std::nullopt;

	return IntMD->getSExtValue();
}

//// extracted from llvm LoopUnrollPass.cpp tryToUnrollLoop()
//void loopAnalyzeTripCounts( Loop *L,
//		 ScalarEvolution &SE) {
//
//	// Find the smallest exact trip count for any exit. This is an upper bound
//	// on the loop trip count, but an exit at an earlier iteration is still
//	// possible. An unroll by the smallest exact trip count guarantees that all
//	// branches relating to at least one exit can be eliminated. This is unlike
//	// the max trip count, which only guarantees that the backedge can be broken.
//	unsigned TripCount = 0;
//	unsigned TripMultiple = 1;
//	SmallVector<BasicBlock*, 8> ExitingBlocks;
//	L->getExitingBlocks(ExitingBlocks);
//	for (BasicBlock *ExitingBlock : ExitingBlocks)
//		if (unsigned TC = SE.getSmallConstantTripCount(L, ExitingBlock))
//			if (!TripCount || TC < TripCount)
//				TripCount = TripMultiple = TC;
//
//	if (!TripCount) {
//		// If no exact trip count is known, determine the trip multiple of either
//		// the loop latch or the single exiting block.
//		// TODO: Relax for multiple exits.
//		BasicBlock *ExitingBlock = L->getLoopLatch();
//		if (!ExitingBlock || !L->isLoopExiting(ExitingBlock))
//			ExitingBlock = L->getExitingBlock();
//		if (ExitingBlock)
//			TripMultiple = SE.getSmallConstantTripMultiple(L, ExitingBlock);
//	}
//
//	// Try to find the trip count upper bound if we cannot find the exact trip
//	// count.
//	unsigned MaxTripCount = 0;
//	bool MaxOrZero = false;
//	if (!TripCount) {
//		MaxTripCount = SE.getSmallConstantMaxTripCount(L);
//		MaxOrZero = SE.isBackedgeTakenCountMaxOrZero(L);
//	}
//}

}
