#include <llvm/Analysis/CFGPrinter.h>
#include <llvm/Support/GraphWriter.h>
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/Analysis/BlockFrequencyInfo.h>
#include <iostream>
#include <fstream>

namespace hwtHls {

void writeCFGToDotFile(llvm::Function &F, const std::string &Filename,
		llvm::BlockFrequencyInfo *BFI, llvm::BranchProbabilityInfo *BPI,
		bool debugMsgs = false, bool CFGOnly = false);
void writeCFGToDotFile(llvm::Function &F, const std::string &Filename,
		llvm::FunctionAnalysisManager &FAM, bool debugMsgs = false,
		bool CFGOnly = false);

}
