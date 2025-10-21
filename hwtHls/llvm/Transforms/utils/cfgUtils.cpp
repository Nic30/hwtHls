#include <hwtHls/llvm/Transforms/utils/cfgUtils.h>
#include <llvm/IR/Instructions.h>

using namespace llvm;

namespace hwtHls {

void replaceSuccessorWith(BasicBlock &BB, DomTreeUpdater &DTU,
		llvm::BasicBlock *curSuc, llvm::BasicBlock *newSuc) {
	if (curSuc == newSuc)
		return;

	BB.getTerminator()->replaceSuccessorWith(curSuc, newSuc);
	DTU.applyUpdates( { //
			{ DominatorTree::Delete, &BB, curSuc }, //
					{ DominatorTree::Insert, &BB, newSuc } //
			});
	for (auto &PHI : newSuc->phis()) {
		PHI.replaceIncomingBlockWith(curSuc, &BB);
	}
}

void replaceSuccessorWith(const SetVector<BasicBlock*> &blocks,
		DomTreeUpdater &DTU, llvm::BasicBlock *curSuc,
		llvm::BasicBlock *newSuc) {
	if (curSuc == newSuc)
		return;

	for (BasicBlock *BB : blocks) {
		replaceSuccessorWith(*BB, DTU, curSuc, newSuc);
	}
}

}
