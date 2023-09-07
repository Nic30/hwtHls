#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#include <limits>
using namespace llvm;
namespace hwtHls {

// based on llvm/Analysis/CFGPrinter.cpp
void writeCFGToDotFile(Function &F, const std::string &Filename,
		llvm::FunctionAnalysisManager &FAM, bool debugMsgs, bool CFGOnly) {
	//auto *BFI = &FAM.getResult<BlockFrequencyAnalysis>(F);
	//auto *BPI = &FAM.getResult<BranchProbabilityAnalysis>(F);
	BlockFrequencyInfo *BFI = nullptr;
	BranchProbabilityInfo *BPI = nullptr;
	writeCFGToDotFile(F, Filename, BFI, BPI, debugMsgs, CFGOnly);
}

void writeCFGToDotFile(Function &F, const std::string &Filename,
		BlockFrequencyInfo *BFI, BranchProbabilityInfo *BPI, bool debugMsgs,
		bool CFGOnly) {
	if (debugMsgs)
		errs() << "Writing '" << Filename << "'...";

	std::error_code EC;
	raw_fd_ostream File(Filename, EC, sys::fs::OF_Text);
	uint64_t MaxFreq = BFI != nullptr ? getMaxFreq(F, BFI) : (uint64_t)std::numeric_limits<uint64_t>::max;
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

}
