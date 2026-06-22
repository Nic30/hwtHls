#pragma once

#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/Support/raw_ostream.h>
#include <unordered_map>

using namespace llvm;

namespace hwtHls {

class InstructionGraph {
public:
	using AdjacentMap =
		std::unordered_map<llvm::Instruction *,
						   llvm::SetVector<llvm::Instruction *>>;
	// :note: predecessors/successors have always record for every node so we do
	// not have update extra list on every node add/remove
	AdjacentMap predecessors;
	AdjacentMap successors;
	
	// Build this graph for instructions inside loop body, ignoring backedges
	// and loop exit edges
	static InstructionGraph buildFromInstuctionsInLoopBodyOnly(
		llvm::Loop &L, llvm::ArrayRef<llvm::Instruction *> &instrs);

	//  a->b->c; rm b; results in a->c
	// if node has reflexive edge, the edge is ignored during update of
	// predecessors/successors
	void removeNodeAndTransitivelyReconnect(llvm::Instruction *node);
	// Kahn's algorithm for topological order (DAG partial order)
	// :note: instructions are as parameter because predecessors/successors do
	// not preserver order of the nodes for determinism
	using NeverCoexecutingInstrVec = SmallVector<llvm::Instruction *, 8>;
	using NeverCoexecutingStoreInstrVec = SmallVector<llvm::StoreInst *, 8>;
	void partialTopologicalSort(
		llvm::ArrayRef<Instruction *> &instructions,
		SmallVector<NeverCoexecutingInstrVec> &order);
	void print(llvm::raw_ostream &OS) const;
};

} // namespace hwtHls

namespace llvm {

inline llvm::raw_ostream &operator<<(llvm::raw_ostream &OS,
									 const hwtHls::InstructionGraph &V) {
	V.print(OS);
	return OS;
}
} // namespace llvm