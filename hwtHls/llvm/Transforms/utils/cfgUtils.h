#pragma once

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>

namespace hwtHls {
// update blocks to jump to newSuc instead of curSuc
void replaceSuccessorWith(const llvm::SetVector<llvm::BasicBlock*> &blocks,
		llvm::DomTreeUpdater &DTU, llvm::BasicBlock *curSuc,
		llvm::BasicBlock *newSuc);
}
