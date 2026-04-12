#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/mergeSets.h>

using namespace llvm;

namespace hwtHls {

BasicBlock* getIDomBB(const DominatorTree &DT, BasicBlock& BB) {
	auto idom = DT.getNode(&BB)->getIDom();
	if (!idom) {
		assert(predecessors(&BB).empty());
		return &BB;
	}
	return idom->getBlock();
}

template<typename T>
bool containsAll(const std::set<T> &a, const std::set<T> &b) {
	// std::includes returns true if all elements of b are found in a
	// :attention: this work because order of set is deterministic, it will not work for unordered_set
	return std::includes(a.begin(), a.end(), b.begin(), b.end());
}


/// An Incoming J Edge Inconsistent(x) is true if at least one of the incoming
/// J-edges to x is inconsistent, false otherwise.
// based  on https://github.com/ethanblake4/control_flow_graph/blob/main/lib/src/merge_set.dart#L76
bool _isIncomingJEdgeInconsistent(MergeSets &mergeSets, const DJGraph &djGraph,
		const std::set<std::pair<BasicBlock*, BasicBlock*>> &visited,
		BasicBlock &node) {
	for (auto incomingEdge : djGraph.incomingEdgesOf(&node)) {
		auto srcNode = incomingEdge.other;
		auto dstNode = &node;
		if (incomingEdge.data == DJ_EDGE_TYPE::DJ_EDGE_TYPE_J
				&& visited.contains( { incomingEdge.other, &node })) {
			auto srcMs = mergeSets.find(srcNode);
			auto dstMs = mergeSets.find(dstNode);
			assert(srcMs != mergeSets.end());
			assert(dstMs == mergeSets.end());
			if (!containsAll(srcMs->second, dstMs->second)) {
				return true;
			}
		}
	}
	return false;
}

/// ### Algorithm: Top Down Merge Set Computation (TDMSC-I)
/// #### Input : GDJ
/// #### Outputs:
/// - Partial/Complete Merge sets for every node of the DJ Graph
/// - A boolean value to indicate whether a subsequent pass is required
/// based on https://github.com/ethanblake4/control_flow_graph/blob/main/lib/src/merge_set.dart#L9
bool _topDownMergeSetComputation(MergeSets &mergeSets, const DJGraph &djGraph,
		const std::vector<BasicBlock*> &djGraphInBreadthFirstOrder,
		BasicBlock &root, const DominatorTree &dominators) {
	bool requireAnotherPass = false;
	std::set<std::pair<BasicBlock*, BasicBlock*>> visited;

	std::map<BasicBlock*, int> level;
	for (auto *node : djGraphInBreadthFirstOrder) {
		auto idom = getIDomBB(dominators, *node);
		auto ldom = level.find(idom);
		level[node] = ldom == level.end() ? 0 : ldom->second + 1;
	}

	for (BasicBlock *dstNode : djGraphInBreadthFirstOrder) {
		// errs() << "dstNode:";
		// dstNode->printAsOperand(errs());
		// errs()  << "\n"; 
		for (const auto &incomingEdge : djGraph.incomingEdgesOf(dstNode)) {
			auto srcNode = incomingEdge.other;
			if (incomingEdge.data == DJ_EDGE_TYPE::DJ_EDGE_TYPE_J
					&& !visited.contains( { srcNode, dstNode })) {
				visited.insert( { srcNode, dstNode });

				// errs() << "      incom:";
				// srcNode->printAsOperand(errs()); 
				// errs() << "\n";
				auto tmp = srcNode;
				BasicBlock *lnode = tmp;
				while (level[tmp] >= level[dstNode]) {
					// errs() << "merge ";
					// tmp->printAsOperand(errs());
					// errs() << " <- ";
					// dstNode->printAsOperand(errs());
					// errs() << "\n";	 
					auto mergeSetTmp = mergeSets.find(tmp);
					if (mergeSetTmp == mergeSets.end()) {
						mergeSets[tmp] = { };
						mergeSetTmp = mergeSets.find(tmp);
					}

					auto targetMergeSet = mergeSets.find(dstNode);
					if (targetMergeSet != mergeSets.end()) {
						mergeSetTmp->second.insert(targetMergeSet->second.begin(),
								targetMergeSet->second.end());
					}
					mergeSetTmp->second.insert(dstNode);
					lnode = tmp;
					auto dom = getIDomBB(dominators, *tmp);
					assert(dom);
					if (dom == tmp) {
						break;
					}
					tmp = dom;
				}
				assert(lnode);
				for (auto incomingEdgeToLNode : djGraph.incomingEdgesOf(lnode)) {
					auto srcNodeToLNode = incomingEdgeToLNode.other;
					if (incomingEdgeToLNode.data == DJ_EDGE_TYPE::DJ_EDGE_TYPE_J
							&& visited.contains( { srcNodeToLNode, lnode })) {
						if (!containsAll(mergeSets[srcNodeToLNode],
								mergeSets[lnode])) {
							auto node = srcNodeToLNode;
							while (level[node]
									>= (level.find(lnode) == level.end() ?
											0 : level[lnode])) {
								auto &ms = mergeSets[node];
								auto &ms1 = mergeSets[lnode];
								ms.insert(ms1.begin(), ms1.end());
								lnode = node;
								node = getIDomBB(dominators, *node);
							}
							if (_isIncomingJEdgeInconsistent(mergeSets, djGraph,
									visited, *lnode)) {
								requireAnotherPass = true;
							}
						}
					}
				}
			}
		}
	}
	return requireAnotherPass;
}

/// compute Complete Top Down Merge Set Computation (CTDMSC)
// based  on https://github.com/ethanblake4/control_flow_graph/blob/main/lib/src/merge_set.dart#L93
MergeSets completeTopDownMergeSetComputation(const DJGraph &djGraph,
		Function &F, const DominatorTree &DT) {
	// errs() << "completeTopDownMergeSetComputation\n";
	// F.dump();
	// errs() << "\n";
	// DT.print(errs());
	// errs() << "\n";
	// assert(DT.verify());
	MergeSets mergeSets;
	bool requireAnotherPass = true;
	std::vector<BasicBlock*> djGraphInBreadthFirstOrder = djGraph.breadthFirst(
			&F.getEntryBlock());
	while (requireAnotherPass) {
		requireAnotherPass = _topDownMergeSetComputation(mergeSets, djGraph,
				djGraphInBreadthFirstOrder, F.getEntryBlock(), DT);
	}
	return mergeSets;
}

}
