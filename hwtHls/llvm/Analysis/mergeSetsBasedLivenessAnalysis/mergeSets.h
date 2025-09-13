#pragma once
#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/djGraph.h>
#include <map>
#include <set>

namespace hwtHls {

// A merge set of a block is the set of all blocks where its control flow can 'merge' with a
// different path.
using MergeSets = std::map<llvm::BasicBlock*, std::set<llvm::BasicBlock*>>;
/// ### Algorithm: Complete Top Down Merge Set Computation (CTDMSC)
/// #### Input: GDJ
/// #### Output: Complete Merge sets for every node of the DJ graph
MergeSets completeTopDownMergeSetComputation(const DJGraph &djGraph,
		llvm::Function &F, const llvm::DominatorTree &dominators);
}
