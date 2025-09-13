#pragma once

#include <set>
#include <list>
#include <map>

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>

#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/mergeSets.h>

// Efficient liveness computation using merge sets and DJ-graphs
// https://dl.acm.org/doi/10.1145/2086696.2086706
// based on https://github.com/ethanblake4/control_flow_graph/blob/main/lib/src/liveness.dart

namespace hwtHls {
std::map<llvm::BasicBlock*, llvm::SetVector<llvm::Instruction*>> allLiveInUsingMergeSet(
		llvm::BasicBlock &root, const llvm::DominatorTree &dominators,
		const MergeSets &mergeSets);
}
