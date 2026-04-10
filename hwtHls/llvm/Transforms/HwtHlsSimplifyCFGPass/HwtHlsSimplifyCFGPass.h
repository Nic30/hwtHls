#pragma once
/**
 * Common hard-to-guess pitfalls during development of SimplifyCFG
 * * block replaced by UnreachableInst from no obvious reason
 *   * if llvm removeUndefIntroducingPredecessor sees any incoming value which may cause undefined behavior later
 *     (using passingValueIsAlwaysUndefined) it removes predecessor
 *     * bugs of this type are commonly caused by too aggressive code hoisting or phi operand swaps
 * */

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Transforms/Utils/SimplifyCFGOptions.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>
#include <llvm/Analysis/DomTreeUpdater.h>

namespace llvm {
class IRBuilderBase;
}

namespace hwtHls {

struct HwtHlsSimplifyCFGOptions: public llvm::SimplifyCFGOptions {
	// move AND/OR/XOR/Select/bitrange.get/bitrange.concat instructions to predecessor block
	bool HoistCheapInsts = true;
	// allow llvm::ReduceSwitchRange
	bool SwitchReduceRange = true;
	size_t ITERATION_LIMIT = 1000;
	// for meaning of following parameters see function HwtHlsSimplifyCFGPass_{optionName}
	bool HoistHoistableAssumes = true;
	bool MemHoistToNewBB = true;
	bool NormalizeLookupTableIndex = true;
	bool RewriteMaskPatternsFromCFGToData = true;
	bool StoreHoist = true;
	bool AggresiveStoreSink = true;
	bool MergePredecessorsStore = true;
	bool PhiToLogicalExpr = true;
	bool UnswitchComplementarySequentialBlocks = true;
	bool SpeculatePredecessor = true;
	bool StreamWriteMerge = true;
	bool StreamReadMerge = true;
	bool SwitchToSelectOrRomLoad = true;
	bool SwitchSuccClusterReduceFewExit = true;
	bool NormalizeBrCond = true;
	bool ConstantFoldTerminator = true;
	bool EliminateDuplicatePHINodes = true;
	bool EemoveUndefIntroducingPredecessor = true;
	bool MergeBlockIntoPredecessor = true;

	// for doc of following members see the doc for pass it enables
	bool RunEarlyCSEPass = true;
	bool RunRomExtractPass = true;
	bool RunHwtHlsInstCombinePass = true;
	bool RunTrivialSimplifyCFGPass = true;
	bool RunSimplifyCFGPass = true;
	bool RunBitcountMergePass = true;
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
	HwtHlsSimplifyCFGOptions& setSwitchReduceRange(bool B) {
		SwitchReduceRange = B;
		return *this;
	}

};
class SimplifyCFGOpt2;
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
	static llvm::StringRef name() { // :note: required otherwise llvm::SimplifyCFGPass::name is used
		return "hwtHls::HwtHlsSimplifyCFGPass";
	}
	bool runOpt0(llvm::Function &F, llvm::DomTreeUpdater &DTU,
			SimplifyCFGOpt2 &opt, bool &exprChanged);
	bool runOpt1(llvm::FunctionAnalysisManager &AM,
			llvm::IRBuilderBase &Builder, const llvm::DataLayout &DL,
			llvm::AssumptionCache &AC, llvm::Function &F,
			llvm::DomTreeUpdater &DTU, SimplifyCFGOpt2 &opt, bool &exprChanged);
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);

};

}

