#pragma once
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/Analysis/BlockFrequencyInfo.h>

namespace hwtHls {

// :note: writeCFGToDotFile requires DT, PDT, LI, BFI, BPI to be not present or valid
void writeCFGToDotFile(llvm::Function &F, const std::string &Filename,
		llvm::BlockFrequencyInfo *BFI=nullptr, llvm::BranchProbabilityInfo *BPI=nullptr,
		bool debugMsgs = false, bool CFGOnly = false);
// :param discardNewlyRequestedAnalysis: useful when calling this during other transformation
//       which modifies CFG and thus may invalidate requested analyses
void writeCFGToDotFile(llvm::Function &F, const std::string &Filename,
		llvm::FunctionAnalysisManager &FAM, bool debugMsgs = false,
		bool CFGOnly = false,  bool discardNewlyRequestedAnalysis = true);

}
