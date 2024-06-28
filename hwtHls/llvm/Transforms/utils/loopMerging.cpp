#include <hwtHls/llvm/Transforms/utils/loopMerging.h>

#include <llvm/Analysis/ScalarEvolution.h>

using namespace llvm;


namespace hwtHls {

/*
 * :note: parent loop must contain all nodes from child loops, in order to recognize exit correctly
 * :param L0: parent loop which will remain
 * :param L1: child loop which will be merged into L0 and removed
 * */
void mergeNestedLoops(llvm::LoopInfo &LI, llvm::ScalarEvolution *SE, llvm::LPMUpdater & LPMU, llvm::Loop *L1,
		llvm::Loop *L0) {
	// :note: based on llvm/lib/Transforms/Scalar/LoopFuse.cpp
	std::string L1Name = std::string(L1->getName());
	//// Anything ScalarEvolution may know about this loop or the PHI nodes
	//// in its header will soon be invalidated. We should also invalidate
	//// all outer loops because insertion and deletion of blocks that happens
	//// during the rotation may violate invariants related to backedge taken
	//// infos in them.
	if (SE) {
		SE->forgetLoop(L1);
		// We may hoist some instructions out of loop. In case if they were cached
		// as "loop variant" or "loop computable", these caches must be dropped.
		// We also may fold basic blocks, so cached block dispositions also need
		// to be dropped.
		SE->forgetBlockAndLoopDispositions();
	}

	// Merge the loops. (L1 into L0)
	SmallVector<BasicBlock*, 8> Blocks(L1->blocks());
	for (BasicBlock *BB : Blocks) {
		// :note: may contain if L1 is inside of L0
		assert(L0->contains(BB) && "Must contain because L1 should be nested in L0");
		//	L0->addBlockEntry(BB);
		L1->removeBlockFromLoop(BB);
		if (LI.getLoopFor(BB) != L1)
			continue;
		LI.changeLoopFor(BB, L0);
	}
	while (!L1->isInnermost()) {
		const auto &ChildLoopIt = L1->begin();
		Loop *ChildLoop = *ChildLoopIt;
		L1->removeChildLoop(ChildLoopIt);
		L0->addChildLoop(ChildLoop);
	}
	LPMU.markLoopAsDeleted(*L1, L1Name);
	// Delete the now empty loop L1.
	LI.erase(L1);
}

}
