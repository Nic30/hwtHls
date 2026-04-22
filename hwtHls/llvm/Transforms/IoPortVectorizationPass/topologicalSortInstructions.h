#pragma once

#include <deque>
#include <llvm/Analysis/LoopInfo.h>

namespace hwtHls {

template <typename InstructionT>
void topologicalSortInstructions(
	llvm::Loop &L, llvm::ArrayRef<InstructionT *> instructions,
	llvm::SmallVector<InstructionT *> &instructionsOrdered) {
	// Group by BasicBlock for O(1) intra-BB ordering
	llvm::DenseMap<llvm::BasicBlock *, llvm::SmallVector<InstructionT *, 8>>
		BBInstrGroups;
	for (InstructionT *I : instructions) {
		BBInstrGroups[I->getParent()].push_back(I);
	}
	// Intra-BB linear order (O(n log n))
	// (ordered in advance so we can skip the dominance check )
	for (auto &[BB, Insts] : BBInstrGroups) {
		llvm::sort(Insts, [](InstructionT *A, InstructionT *B) {
			return A->comesBefore(B);
		});
	}
	// Kahn's algorithm for topological order (DAG partial order)
	llvm::DenseMap<llvm::BasicBlock *, unsigned> InDegree;
	// Phase 1: Pre-compute in-degrees to avoid seen predecessor set checks
	// Phase 2: Initialize queue with 0 in-degree blocks (EntryBB first)
	std::deque<llvm::BasicBlock *> Queue;
	auto header = L.getHeader();
	assert(header);
	for (auto *BB : L.blocks()) {
		size_t predSize;
		if (BB == header) {
			predSize =
				0; // backedges or edges outside of the loop are not counted
		} else {
			predSize = pred_size(BB);
		}
		if (predSize == 0) {
			Queue.push_back(BB);
			InDegree[BB] = -1; // Mark as processed
		} else {
			InDegree[BB] = predSize;
		}
	}

	// Phase 3: Kahn's algorithm
	while (!Queue.empty()) {
		auto *BB = Queue.front();
		Queue.pop_front();
		auto instrs = BBInstrGroups.find(BB);
		if (instrs != BBInstrGroups.end()) {
			for (auto *I : instrs->second) {
				instructionsOrdered.push_back(I);
			}
		}
		assert(instructionsOrdered.size() <= instructions.size() &&
			   "DAG can not contain cycles!");

		// Update successors
		for (auto *Succ : successors(BB)) {
			if (--InDegree[Succ] == 0) {
				Queue.push_back(Succ);
			}
		}
	}
	assert(instructionsOrdered.size() == instructions.size() &&
		   "All instructions of interest are expected to be reachable!");
}

} // namespace hwtHls