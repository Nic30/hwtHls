#include <deque>
#include <hwtHls/llvm/Transforms/IoPortVectorizationPass/InstructionGraph.h>

#include <llvm/Analysis/PostDominators.h>
#include <llvm/IR/CFG.h>
#include <llvm/IR/Instructions.h>

using namespace llvm;

namespace hwtHls {

void InstructionGraph::removeNodeAndTransitivelyReconnect(
	llvm::Instruction *node) {
	const auto &preds = predecessors[node];
	const auto &succs = successors[node];
	for (Instruction *pred : preds) {
		// remove the edge to node and add edge to each successor
		if (pred == node)
			continue;
		// Remove 'node' from pred's successors
		auto &pred_succs = successors[pred];
		pred_succs.remove(node);
		// Add direct edges from pred to each successor of node
		for (Instruction *succ : succs) {
			if (succ == node)
				continue; // Avoid self-loops
			pred_succs.insert(succ);

			// Add pred to succ's predecessors
			predecessors[succ].insert(pred);
		}
	}

	for (Instruction *succ : succs) {
		// remove the edge from node and add edge from each predecessor
		if (succ == node)
			continue;

		// Remove 'node' from succ's predecessors
		auto &succ_preds = predecessors[succ];
		succ_preds.remove(node);

		// Add direct edges from each predecessor of node to succ
		for (Instruction *pred : preds) {
			if (pred == node)
				continue; // Avoid self-loops
			succ_preds.insert(pred);

			// Add succ to pred's successors
			successors[pred].insert(succ);
		}
	}

	// Finally remove the node itself from both maps
	predecessors.erase(node);
	successors.erase(node);
}

InstructionGraph InstructionGraph::buildFromInstuctionsInLoopBodyOnly(
	llvm::Loop &L, llvm::ArrayRef<llvm::Instruction *> &instrs) {
	auto self = InstructionGraph();
	// build supplementary BBInstrGroups to resolve members ship and order
	// of instructions for each block
	std::unordered_map<BasicBlock *, SmallVector<Instruction *, 8>>
		BBInstrGroups;
	for (auto *I : instrs) {
		BBInstrGroups[I->getParent()].push_back(I);
	}
	for (auto &[BB, Insts] : BBInstrGroups) {
		llvm::sort(Insts, [](Instruction *A, Instruction *B) {
			return A->comesBefore(B);
		});
	}

	// initialize successors from blocks and BBInstrGroups, for block
	// without target instruction, terminator is temporally used to
	// represent the node
	SmallVector<Instruction *> nodesToRm;
	auto header = L.getHeader();
	for (BasicBlock *BB : L.blocks()) {
		SetVector<Instruction *> sucVector;
		for (BasicBlock *suc : llvm::successors(BB)) {
			if (suc == header || !L.contains(BB))
				continue;
			auto sucInstrs = BBInstrGroups.find(suc);
			Instruction *sucBegin;
			if (sucInstrs == BBInstrGroups.end()) {
				sucBegin = suc->getTerminator();
			} else {
				sucBegin = sucInstrs->second.back();
			}
			sucVector.insert(sucBegin);
		}
		auto bbInstrs = BBInstrGroups.find(BB);
		Instruction *BBlast;
		if (bbInstrs == BBInstrGroups.end()) {
			BBlast = BB->getTerminator();
			nodesToRm.push_back(BBlast); // it is useless to keep this terminator
			// in the graph of target instructions as this block does not contain any target
			// instruction
		} else {
			if (bbInstrs->second.size() > 1) {
				Instruction * prev = nullptr;
				for (auto* I: bbInstrs->second) {
					if (prev != nullptr) {
						self.successors[prev].insert(I);
						self.predecessors[I].insert(prev);
					}
					prev = I;
				}
			}

    		BBlast = bbInstrs->second.back();
		}
		self.successors[BBlast] = sucVector;
		for (auto suc : sucVector) {
			self.predecessors[suc].insert(BBlast);
		}
	}
	for (auto n : nodesToRm) {
		self.removeNodeAndTransitivelyReconnect(n);
	}
	return self;
}

void InstructionGraph::partialTopologicalSort(
	llvm::ArrayRef<Instruction *> &instructions,
	SmallVector<SmallVector<llvm::Instruction *, 8>> &order) {

	// Pre-compute in-degrees to avoid seen predecessor set checks
	// Initialize queue with 0 in-degree blocks (EntryBB first)
	DenseMap<Instruction *, unsigned> InDegree;
	std::deque<Instruction *> _Queue0;
	std::deque<Instruction *> _Queue1;
	auto *Queue = &_Queue0;
	auto *QueueNext = &_Queue1;

	for (auto *I : instructions) {
		size_t predSize = predecessors[I].size();
		if (predSize == 0) {
			Queue->push_back(I);
			InDegree[I] = -1; // Mark as processed
		} else {
			InDegree[I] = predSize;
		}
	}

	order.reserve(instructions.size());

	for (;;) {
		if (!Queue->empty()) {
			// the Queue contains Instruction on same level in CFG, 
			// it is known that there is no path in CFG which
			// contains more than 1 instruction from this set, so they may be
			// mapped to same lane as they never co-execute.
			order.push_back(
				SmallVector<Instruction *, 8>(Queue->begin(), Queue->end()));
		} else {
			break;
		}
		while (!Queue->empty()) {
			auto *I = Queue->front();
			Queue->pop_front();
			// :note: in original Kahn's alg. there would be I placed to
			//  output, but we doing in on layer basis by pushing whole
			//  Queue
			for (auto *Succ : successors[I]) {
				if (--InDegree[Succ] == 0) {
					QueueNext->push_back(Succ);
				}
			}
		}
		std::swap(Queue, QueueNext);
	}
}

void InstructionGraph::print(llvm::raw_ostream &OS) const {
	OS << "<InstructionGraph \n";
	for (const auto &[pred, succs] : successors) {
		OS << pred << " " << *pred << ":\n";
		for (auto suc : succs) {
			OS << "   " << suc << " " << *suc << ":\n";
		}
	}
}

} // namespace hwtHls