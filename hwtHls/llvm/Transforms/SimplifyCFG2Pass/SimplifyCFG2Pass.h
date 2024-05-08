#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Transforms/Utils/SimplifyCFGOptions.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>

namespace hwtHls {

struct SimplifyCFG2Options: public llvm::SimplifyCFGOptions {
	// move AND/OR/XOR/Select/bitrange.get/bitrange.concat instructions to predecessor block
	bool HoistCheapInsts = true;
	//// same as HoistCheapInsts just move successor block
	//bool SinkCheapInsts = true;

	SimplifyCFG2Options& bonusInstThreshold(int I) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::bonusInstThreshold(
				I));
	}
	SimplifyCFG2Options& forwardSwitchCondToPhi(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::forwardSwitchCondToPhi(
				B));
	}
	SimplifyCFG2Options& convertSwitchRangeToICmp(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::convertSwitchRangeToICmp(
				B));
	}
	SimplifyCFG2Options& convertSwitchToLookupTable(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::convertSwitchToLookupTable(
				B));
	}
	SimplifyCFG2Options& needCanonicalLoops(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::needCanonicalLoops(
				B));
	}
	SimplifyCFG2Options& hoistCommonInsts(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::hoistCommonInsts(
				B));
	}
	SimplifyCFG2Options& sinkCommonInsts(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::sinkCommonInsts(
				B));
	}
	SimplifyCFG2Options& setAssumptionCache(llvm::AssumptionCache *Cache) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::setAssumptionCache(
				Cache));
	}

	SimplifyCFG2Options& setSimplifyCondBranch(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::setSimplifyCondBranch(
				B));
	}
	SimplifyCFG2Options& setFoldTwoEntryPHINode(bool B) {
		return reinterpret_cast<SimplifyCFG2Options&>(SimplifyCFGOptions::setFoldTwoEntryPHINode(
				B));
	}

	SimplifyCFG2Options& setHoistCheapInsts(bool B) {
		HoistCheapInsts = B;
		return *this;
	}

	//SimplifyCFG2Options& setSinkCheapInsts(bool B) {
	//	SinkCheapInsts = B;
	//	return *this;
	//}
};

/// same as original LLVM SimplifyCFGPass but with:
//  * cheap instruction hoist/sink
//  * fixed merge of large switch instructions :attention: should be removed once https://github.com/llvm/llvm-project/issues/61391 is fixed
//  :attention: this potentially removes empty preheaders and latches, L->isLoopSimplifyForm() may not be satisfied
//             L->getLoopPreheader() and L->getLoopLatch() may return nullptr
class SimplifyCFG2Pass: public llvm::SimplifyCFGPass {
	// [copied] copied from llvm base class because of SimplifyCFG::Options is private,
	// which can not be accessed through inheritance
	SimplifyCFG2Options Options;

public:
	SimplifyCFG2Pass();
	/// Construct a pass with optional optimizations.
	SimplifyCFG2Pass(const SimplifyCFG2Options &PassOptions);
	static llvm::StringRef name() {
		return "SimplifyCFG2Pass";
	}
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);

};

}

