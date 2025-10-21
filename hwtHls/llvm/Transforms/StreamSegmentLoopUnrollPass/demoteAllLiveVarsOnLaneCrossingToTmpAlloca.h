#pragma once

#include <map>
#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/SetVector.h>

namespace hwtHls {

void demoteAllLiveVarsOnLaneCrossingToTmpAlloca(llvm::IRBuilder<> &Builder,
		llvm::Function &F, bool ioIsInput,
		std::map<llvm::BasicBlock*, llvm::SetVector<llvm::Instruction*>> &allLiveins,
		const llvm::SmallVector<llvm::BasicBlock*>& BBs,
		const llvm::SmallVector<llvm::Instruction*> &IoInstructions,
		std::vector<llvm::AllocaInst*> &tmpAllocas);

}
