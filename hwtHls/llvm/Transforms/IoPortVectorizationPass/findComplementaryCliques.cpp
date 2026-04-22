// [deprecated] whole file	
#include <hwtHls/llvm/Transforms/IoPortVectorizationPass/findComplementaryCliques.h>
#include <llvm/Analysis/PostDominators.h>
#include <llvm/IR/Instructions.h>

using namespace llvm;

namespace hwtHls {

//	   b0
//    /  \
//  b1    b2
//   |\   /|
//   |  b3 |
//   |   | |
//    \  | /
//      b4
//	:note: If stores are in b1, b2, they do not have any post dominating store, l0:b1|b2
//         If stores are in b1, b2, b3 -> l0:b1|b2, l1:b3


SmallVector<SmallVector<StoreInst *>>
findComplementaryCliques(ArrayRef<StoreInst *> &IOStores,
						 PostDominatorTree &PDT) {
	// :note: the items in lane are those which can't co-execute, thus they can be 
	//   mapped to a single lane
	// :note: the lane corresponds the clique in post-dominance graph
	SmallVector<SmallVector<StoreInst *>> Lanes;

	// 0. Assume that all instructions are never executed in one pass and map them to a single lane
	// 1. DFS mine all paths trough the code
	
	// Simple path-interference analysis: ops are complementary if no common
	// execution path contains both of them
	for (StoreInst *SI : IOStores) {
		bool hasLane = false;
		for (auto &Lane : Lanes) {
			// Test if SI can co-execute with any in Lane
			bool isKnowToMaybeExecuteIfThisLaneExecute = true;
			for (StoreInst *Other : Lane) {
				// if every path through code always leads also through the
				// other store we know that the stores will always co-execute thus
				// they can not be in the same Lane
				auto BB0 = SI->getParent();
				auto BB1 = Other->getParent();
				if (!(BB0 == BB1 || PDT.dominates(BB0, BB1) ||
					PDT.dominates(BB1, BB0))) {
					isKnowToMaybeExecuteIfThisLaneExecute = false;
					break;
				}
			}
			if (!isKnowToMaybeExecuteIfThisLaneExecute) {
				// No conflicts (no path trough the code which contains SI and store from other Lane) -> pack into this Lane (lane reuse)
				// :note: order of Lanes for the StoreInst in the same block is given by original order in IOStores
				//    which should be topological order so the Lanes should preserve this order.
				Lane.push_back(SI);
				hasLane = true;
				break;
			}
		}
		if (!hasLane) {
			Lanes.push_back({SI});
		}
	}
	return Lanes;
}

} // namespace hwtHls