#pragma once

#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

void formDedicatedUniqueLoopExitingAndLatchBB(llvm::IRBuilder<> & Builder, llvm::DomTreeUpdater &DTU,
		llvm::LoopInfo &LI);

}
