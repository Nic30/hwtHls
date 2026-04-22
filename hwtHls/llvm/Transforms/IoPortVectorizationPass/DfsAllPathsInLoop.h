#pragma once

#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CFG.h>

namespace hwtHls {

// [deprecated]
// 0. topological sort of all instructions
//    * it will be required when splitting instructions to lanes
//      The order at which lanes are splitting does not obey topological order
//      and thus some later lane may be extracted first before all predecessor
//      lanes are discovered because they jus were not enabled on this path
// 1. Split lanes for instructions in the same block (for how see next step)
// 2. DFS mine all paths trough the program and split lanes accordingly:
//    * for each instruction on path assert that they are in distinct lanes
//    * if two instructions are in the same lane, split the lane (use
//    topological order
//      to extract second instruction and all after it)
//    * by splitting using topological order it is asserted that the order of
//    lanes preserves
//      topological sort
//
//      .. code-block::text
//         b0
//         |\
//         b1 b2
//         |/
//         b3
//         |\
//         b4 b5
//         |/
//         b6
//        // assume that the store is in 2,5; if the  path 0 1 5 6 is found
//        before 0 2 3 4 6
//        // the output lanes would be {5}, {2} instead of {2}, {5}, that is why
//        we need the order
//        // to know where to extract the lane

// [todo] find if reverse (for successor relation DAG) topological order is
// better
// :note: [wrong] Modification of topological sort algorithm to retrieve
//        unorderable sets is not sufficient there,
//        For example if we iterate over layers of nodes which currently have
//        indegree=0 we receive instructions potentially executed exclusively
//        and thus potentially mapped to a shared lane. But the task is to find
//        instructions which may not be executed exclusively (may all pairwise
//        execute on some path trough program). It is also necessary to retrieve
//        mapping of instruction to lanes.
// :note: the DT/PDT and alike probably can not help with the lane assignment
//      because selection function is not transfer function (it is not even
//      distributive) and problem is not flow problem,
//

template <typename InstructionT> class DfsAllPathsInLoop {
public:
	using BlockInstructions =
		llvm::DenseMap<llvm::BasicBlock *,
					   llvm::SmallVector<InstructionT *, 8>>;
	using Path = llvm::SmallVector<
		std::pair<llvm::BasicBlock *, typename BlockInstructions::iterator>>;
	Path actualPath;
	llvm::Loop &L;
	BlockInstructions &BBInstrGroups;
	DfsAllPathsInLoop(llvm::Loop &L, BlockInstructions &BBInstrGroups) :
		L(L), BBInstrGroups(BBInstrGroups) {}

	// from given starting block BB0 call callback on all possible paths trough
	// the program
	void dfsAllPathsInLoop(llvm::BasicBlock &BB0,
						   std::function<void(Path &)> &callback) {
		auto header = L.getHeader();
		bool pathKnownToEndInBB0 = false;
		actualPath.push_back({&BB0, BBInstrGroups.find(&BB0)});
		for (auto sucBB : successors(&BB0)) {
			if (sucBB == header || !L.contains(sucBB)) {
				if (!pathKnownToEndInBB0) {
					callback(actualPath);
					pathKnownToEndInBB0 = true;
				}
			}
		}
		assert(actualPath.back().first == &BB0);
		actualPath.pop_back();
	}
};

} // namespace hwtHls