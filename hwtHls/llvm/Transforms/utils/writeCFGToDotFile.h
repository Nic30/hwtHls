#pragma once
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/Analysis/BlockFrequencyInfo.h>

namespace hwtHls {

void writeCFGToDotFile(llvm::Function &F, const std::string &Filename,
		llvm::BlockFrequencyInfo *BFI=nullptr, llvm::BranchProbabilityInfo *BPI=nullptr,
		bool debugMsgs = false, bool CFGOnly = false);
void writeCFGToDotFile(llvm::Function &F, const std::string &Filename,
		llvm::FunctionAnalysisManager &FAM, bool debugMsgs = false,
		bool CFGOnly = false);

}
