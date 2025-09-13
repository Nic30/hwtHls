#pragma once
#include <llvm/IR/Dominators.h>
#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/DirectedGraph.h>
namespace hwtHls {

enum class DJ_EDGE_TYPE {
	/// A D-edge in the DJ-graph, representing a dominance relationship.
	DJ_EDGE_TYPE_D,
	/// A J-edge in the DJ-graph, representing a non-dominance control flow
	/// relationship.
	DJ_EDGE_TYPE_J,
};

// The DJ-graph is a directed graph with D-edges, which link immediate dominators to their
// children, and J-edges, representing jumps in the control flow between
// blocks that are not immediate dominators.
using DJGraph = DirectedGraph<llvm::BasicBlock*, DJ_EDGE_TYPE>;
DJGraph computeDJGraph(llvm::Function &F, llvm::DominatorTree &DT);

}
