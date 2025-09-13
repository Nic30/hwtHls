#include <set>
#include <list>
#include <map>

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CFG.h>
#include <llvm/IR/Instructions.h>
#include <llvm/ADT/SetVector.h>
#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/liveness.h>

using namespace llvm;

namespace hwtHls {

bool isLiveInUsingMergeSet(BasicBlock &root, BasicBlock *block, Instruction *variable,
		const DominatorTree & dominators,
		const MergeSets& mergeSets) {
	if (variable->use_empty()) {
		return false;
	}

	auto mr = mergeSets.find(block);
	std::set<BasicBlock*> phiUses;
	for (User *user : variable->users()) {
		if (Instruction *userI = dyn_cast<Instruction>(user)) {
			auto t = userI->getParent();
			for (;;) {
				if (variable->getParent() == t)
					break;
				if (t == block
						|| (mr != mergeSets.end() && mr->second.contains(t))) {
					if (!isa<PHINode>(user)) {
						return true;
					}
					phiUses.insert(t);
				}
				if (t == block || t == &root) {
					break;
				}
				t = dominators.getNode(t)->getIDom()->getBlock();
			}
		}
	}
	if (phiUses.empty()) {
		return false;
	}
	auto t = dominators.getNode(block)->getIDom()->getBlock();
	if (t == block) {
		return true; // bb without predecessor
	}
	for (;;) {
		// orig code contained check for redefs, it is not required there because we work with SSA and there are no redefs
		//  auto defs = blockDefines.find(t);
		//  if (defs != blockDefines.end()) {
		//	for (auto def : defs->second) {
		//	  if (def.name == variable.name && def.version > variable.version) {
		//		return false;
		//	  }
		//	}
		//  }
		BasicBlock *idom = dominators.getNode(t)->getIDom()->getBlock();
		if (idom == block || idom == &root) {
			return true;
		}
		phiUses.erase(t);
		if (phiUses.empty())
			return true;

		t = idom;
	}
	llvm_unreachable("isLiveInUsingMergeSet: previous loop should exit by return");
}

std::map<BasicBlock*, SetVector<Instruction*>> allLiveInUsingMergeSet(BasicBlock &root,
		const DominatorTree & dominators,
		const MergeSets &mergeSets) {
	std::map<BasicBlock*, SetVector<Instruction*>> liveInSets;
	std::list<std::tuple<BasicBlock*, BasicBlock*, SetVector<Instruction*>>> worklist;
	std::set<std::pair<BasicBlock*, BasicBlock*>> visitedEdges;

	worklist.push_back( { nullptr, &root, { } });
	while (!worklist.empty()) {
		BasicBlock *fromBB;
		BasicBlock *idBB;
		SetVector<Instruction*> vin; // varibles defined before block
		std::tie(fromBB, idBB, vin) = worklist.front();
		worklist.pop_front();
		if (visitedEdges.contains( { fromBB, idBB })) {
			continue; // multiple jumps from fromBB to idBB
		} else {
			visitedEdges.insert( { fromBB, idBB });
		}

		SetVector<Instruction*> liveIn;
		for (Instruction* v : vin) {
			if (isLiveInUsingMergeSet(root, idBB, v, dominators,
					mergeSets))
				liveIn.insert(v);
		}
		liveInSets[idBB] = liveIn;

		auto next = liveIn; // copy
		for (auto &I: *idBB)
			next.insert(&I);
		for (auto succ : successors(idBB)) {
			worklist.push_back( { idBB, succ, next });
		}
	}

	return liveInSets;
}
/*
 /// Compute liveout sets using the livein sets of successor blocks.
 std::map<BasicBlock*, std::set<Value*>> allLiveOutUsingMergeSet(
 Function& F,
 BasicBlock* root,
 std::map<BasicBlock*, std::set<Value*>> blockDefines,
 std::map<Value*, std::set<SpecifiedOperation>> uses,
 std::map<BasicBlock*, BasicBlock*> dominators,
 std::map<BasicBlock*, std::set<BasicBlock*>> mergeSets) {
 final liveOutSets = <int, std::set<Value*>>{};
 final postorder = graph.depthFirstPostOrder(root).toList();
 final livein = allLiveInUsingMergeSet(
 root, graph, blockDefines, uses, dominators, mergeSets);
 for (final id in postorder) {
 final successors = graph.successorsOf(id);
 final ins = successors.map((s) => livein[s] ?? const {});
 if (ins.isEmpty) {
 liveOutSets[id] = {};
 continue;
 }

 liveOutSets[id] = ins.reduce((a, b) => a.union(b));
 }
 return liveOutSets;
 }

 bool isLiveOutUsingMergeSet(
 int block,
 Value* variable,
 CFG graph,
 std::map<BasicBlock*, std::set<Value*>> blockDefines,
 std::map<Value*, std::set<SpecifiedOperation>> uses,
 std::map<BasicBlock*, BasicBlock*> dominators,
 std::map<BasicBlock*, std::set<BasicBlock*>> mergeSets,
 std::map<BasicBlock*, std::set<BasicBlock*>> liveoutMsCache) {
 final bd = blockDefines[block];
 final u = uses[variable];

 if (u == null || u.isEmpty) {
 return false;
 }

 if (bd != null && bd.contains(variable)) {
 // Case when variable is defined in block, if any of the uses are outside
 // the block then it must be live-out.
 for (final use in u) {
 if (use.blockId != block) {
 return true;
 }
 }
 }

 final std::set<BasicBlock*> ms;
 if (liveoutMsCache.containsKey(block)) {
 ms = liveoutMsCache[block]!;
 } else {
 ms = {};
 final successors = graph.depthFirst(block).skip(1);
 for (final successor in successors) {
 final set = mergeSets[successor];
 if (set != null) {
 ms.addAll(set);
 }
 }
 liveoutMsCache[block] = ms;
 }

 for (final use in u) {
 var t = use.blockId;
 while (!(blockDefines[t] ?? const {}).contains(variable)) {
 if (ms.contains(t)) {
 return true;
 }
 t = dominators[t]!;
 }
 }

 return false;
 }
 */
}
