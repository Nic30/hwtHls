#pragma once

#include <map>
#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/LoopInfo.h>

namespace hwtHls {

void demoteAllLiveVarsOnLaneCrossingToTmpAlloca(llvm::IRBuilder<> &Builder,
		llvm::Function &F, bool ioIsInput,
		std::map<llvm::BasicBlock*, llvm::SetVector<llvm::Instruction*>> &allLiveins,
		const llvm::SmallVector<llvm::BasicBlock*>& BBs,
		const llvm::SmallVector<llvm::Instruction*> &IoInstructions,
		std::vector<llvm::AllocaInst*> &tmpAllocas);
void demoteBlockPHIsToAlloca(std::vector<llvm::AllocaInst *> &tmpAllocas,
							 llvm::BasicBlock &BB);
void demoteBlockPHIsToAlloca(std::vector<llvm::AllocaInst *> &tmpAllocas,
							 llvm::Loop &L);
}
