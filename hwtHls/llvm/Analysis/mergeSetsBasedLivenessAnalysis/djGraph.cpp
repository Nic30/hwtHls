#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/djGraph.h>

using namespace llvm;

namespace hwtHls {

// based on https://github.com/ethanblake4/control_flow_graph/blob/main/lib/src/dj_graph.dart#L11
DJGraph computeDJGraph(llvm::Function &F, llvm::DominatorTree &DT) {
	DJGraph djGraph;
	for (BasicBlock &BB : F) {
		djGraph.addNode(&BB);
	}
	for (BasicBlock &BB : F) {
		auto idom = DT.getNode(&BB)->getIDom();
		if (idom) {
			auto et = DJ_EDGE_TYPE::DJ_EDGE_TYPE_D;
			djGraph.addEdge(idom->getBlock(), &BB, et);
		}
	}

	for (BasicBlock &BB : F) {
		for (auto *successor : successors(&BB)) {
			if (DT.getNode(successor)->getIDom()->getBlock() != &BB) {
				auto et = DJ_EDGE_TYPE::DJ_EDGE_TYPE_J;
				djGraph.addEdge(&BB, successor, et);
			}
		}
	}

	return djGraph;
}

}
