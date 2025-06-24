#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Transforms/Utils/SimplifyCFGOptions.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>

namespace hwtHls {

struct HwtHlsSimplifyCFGOptions: public llvm::SimplifyCFGOptions {
	// move AND/OR/XOR/Select/bitrange.get/bitrange.concat instructions to predecessor block
	bool HoistCheapInsts = true;
	//// same as HoistCheapInsts just move successor block
	//bool SinkCheapInsts = true;

	HwtHlsSimplifyCFGOptions& bonusInstThreshold(int I) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::bonusInstThreshold(
				I));
	}
	HwtHlsSimplifyCFGOptions& forwardSwitchCondToPhi(bool B) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::forwardSwitchCondToPhi(
				B));
	}
	HwtHlsSimplifyCFGOptions& convertSwitchRangeToICmp(bool B) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::convertSwitchRangeToICmp(
				B));
	}
	HwtHlsSimplifyCFGOptions& convertSwitchToLookupTable(bool B) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::convertSwitchToLookupTable(
				B));
	}
	HwtHlsSimplifyCFGOptions& needCanonicalLoops(bool B) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::needCanonicalLoops(
				B));
	}
	HwtHlsSimplifyCFGOptions& hoistCommonInsts(bool B) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::hoistCommonInsts(
				B));
	}
	HwtHlsSimplifyCFGOptions& sinkCommonInsts(bool B) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::sinkCommonInsts(
				B));
	}
	HwtHlsSimplifyCFGOptions& setAssumptionCache(llvm::AssumptionCache *Cache) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::setAssumptionCache(
				Cache));
	}

	HwtHlsSimplifyCFGOptions& setSimplifyCondBranch(bool B) {
		return reinterpret_cast<HwtHlsSimplifyCFGOptions&>(SimplifyCFGOptions::setSimplifyCondBranch(
				B));
	}

	HwtHlsSimplifyCFGOptions& setHoistCheapInsts(bool B) {
		HoistCheapInsts = B;
		return *this;
	}

	//HwtHlsSimplifyCFGOptions& setSinkCheapInsts(bool B) {
	//	SinkCheapInsts = B;
	//	return *this;
	//}

};

/// same as original LLVM SimplifyCFGPass but with:
//  * cheap instruction hoist/sink
//  * fixed merge of large switch instructions :attention: should be removed once https://github.com/llvm/llvm-project/issues/61391 is fixed
//  :attention: this potentially removes empty preheaders and latches, L->isLoopSimplifyForm() may not be satisfied
//             L->getLoopPreheader() and L->getLoopLatch() may return nullptr
class HwtHlsSimplifyCFGPass: public llvm::SimplifyCFGPass {
	// [copied] copied from llvm base class because of SimplifyCFG::Options is private,
	// which can not be accessed through inheritance
	HwtHlsSimplifyCFGOptions Options;

public:
	HwtHlsSimplifyCFGPass();
	/// Construct a pass with optional optimizations.
	HwtHlsSimplifyCFGPass(const HwtHlsSimplifyCFGOptions &PassOptions);
	static llvm::StringRef name() {
		return "hwtHls::HwtHlsSimplifyCFGPass";
	}
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);

};

}

