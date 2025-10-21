#pragma once

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>

namespace hwtHls {
void splitBBsOnIOAccess(llvm::DomTreeUpdater &DTU, llvm::LoopInfo &LI,
		llvm::Loop &L, llvm::Argument &IoArg, bool &ioIsInput,
		llvm::SmallVector<llvm::BasicBlock*> &BBs,
		llvm::SmallVector<llvm::Instruction*> &IoInstructions);
}
