#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/djGraph.h>
#include <llvm/ADT/PostOrderIterator.h>

using namespace llvm;

namespace hwtHls {

// based on https://github.com/ethanblake4/control_flow_graph/blob/main/lib/src/dj_graph.dart#L11
DJGraph computeDJGraph(llvm::Function &F, llvm::DominatorTree &DT) {
	ReversePostOrderTraversal<Function*> RPOT(&F); // loop headers must be visited before loop blocks
	DJGraph djGraph;
	for (BasicBlock *BB : RPOT) {
		djGraph.addNode(BB);
	}
	for (BasicBlock *BB : RPOT) {
		auto idom = DT.getNode(BB)->getIDom();
		if (idom) {
			auto et = DJ_EDGE_TYPE::DJ_EDGE_TYPE_D;
			djGraph.addEdge(idom->getBlock(), BB, et);
		}
	}

	for (BasicBlock *BB : RPOT) {
		for (auto *successor : successors(BB)) {
			if (DT.getNode(successor)->getIDom()->getBlock() != BB) {
				auto et = DJ_EDGE_TYPE::DJ_EDGE_TYPE_J;
				djGraph.addEdge(BB, successor, et);
			}
		}
	}

	return djGraph;
}

}
