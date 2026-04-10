#include <fstream>
#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#include <iostream>
#include <limits>
#include <llvm/Analysis/CFGPrinter.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/PostDominators.h>
#include <llvm/IR/Analysis.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Support/GraphWriter.h>

using namespace llvm;

namespace hwtHls {

// based on llvm/Analysis/CFGPrinter.cpp
void writeCFGToDotFile(Function &F, const std::string &Filename,
					   llvm::FunctionAnalysisManager &FAM, bool debugMsgs,
					   bool CFGOnly, bool discardNewlyRequestedAnalysis) {
	// requested by BlockFrequencyInfo, BranchProbabilityInfo
	auto *LI = FAM.getCachedResult<LoopAnalysis>(F);
	// requested by BranchProbabilityInfo
	auto *DT = FAM.getCachedResult<DominatorTreeAnalysis>(F);
	auto *PDT = FAM.getCachedResult<PostDominatorTreeAnalysis>(F);

	auto *BFI = FAM.getCachedResult<BlockFrequencyAnalysis>(F);
	auto *BPI = FAM.getCachedResult<BranchProbabilityAnalysis>(F);
	bool hadBFI = BFI != nullptr;
	bool hadBPI = BPI != nullptr;
	if (!BFI) {
		BFI = &FAM.getResult<BlockFrequencyAnalysis>(F);
	}
	if (!BPI) {
		BPI = &FAM.getResult<BranchProbabilityAnalysis>(F);
	}
	writeCFGToDotFile(F, Filename, BFI, BPI, debugMsgs, CFGOnly);
	if (discardNewlyRequestedAnalysis) {
		auto PA = PreservedAnalyses::all();

		if (!hadBPI) {
			PA.abandon<BranchProbabilityAnalysis>();
		}
		if (hadBFI) {
			PA.abandon<BlockFrequencyAnalysis>();
		}
		if (!LI) {
			PA.abandon<LoopAnalysis>();
		}
		if (!PDT) {
			PA.abandon<PostDominatorTreeAnalysis>();
		}
		if (!DT) {
			PA.abandon<DominatorTreeAnalysis>();
		}
		FAM.invalidate(F, PA);
	}
}

void writeCFGToDotFile(Function &F, const std::string &Filename,
					   BlockFrequencyInfo *BFI, BranchProbabilityInfo *BPI,
					   bool debugMsgs, bool CFGOnly) {
	// for loop passes use flags of to provide these
	// createFunctionToLoopPassAdaptor
	assert(BFI && "required after llvm-16");
	assert(BPI && "required after llvm-16");
	if (debugMsgs)
		errs() << "Writing '" << Filename << "'...";

	std::error_code EC;
	raw_fd_ostream File(Filename, EC, sys::fs::OF_Text);
	uint64_t MaxFreq = BFI != nullptr
						   ? getMaxFreq(F, BFI)
						   : (uint64_t)std::numeric_limits<uint64_t>::max;
	DOTFuncInfo CFGInfo(&F, BFI, BPI, MaxFreq);
	CFGInfo.setHeatColors(false);
	CFGInfo.setEdgeWeights(BFI && BPI);
	CFGInfo.setRawEdgeWeights(false);

	if (!EC)
		WriteGraph(File, &CFGInfo, CFGOnly);
	else if (debugMsgs)
		errs() << "  error opening file for writing!";
	else
		throw std::ifstream::failure("error opening file for writing!");
	if (debugMsgs)
		errs() << "\n";
}

} // namespace hwtHls
