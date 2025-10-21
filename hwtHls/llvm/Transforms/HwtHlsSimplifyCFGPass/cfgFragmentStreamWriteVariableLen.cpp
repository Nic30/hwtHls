#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentStreamWriteVariableLen.h>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/ValueTracking.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamWriteMerge.h>

using namespace llvm;

namespace hwtHls {

CfgFragmentStreamWriteVariableLen::BasicBlockWithStreamWriteAndBrCond::BasicBlockWithStreamWriteAndBrCond(
		const BasicBlockAndBrCond &bbAndCond, llvm::CallInst *streamWrite) :
		BasicBlockAndBrCond(bbAndCond), streamWrite(streamWrite) {
	assert(streamWrite->getParent() == BB);
}

CfgFragmentStreamWriteVariableLen::CfgFragmentStreamWriteVariableLen(
		llvm::IRBuilderBase &Builder, llvm::SimplifyQuery &SQ) :
		CfgFragmentChainOfblocksWithSameSucc(), Builder(Builder), SQ(SQ), streamIoPtr(
				nullptr) {
}

std::pair<BasicBlock*,
		std::optional<
				CfgFragmentStreamWriteVariableLen::BasicBlockWithStreamWriteAndBrCond>> CfgFragmentStreamWriteVariableLen::detectOne(
		BasicBlock &BB, BasicBlock &exit) {
	auto frag = CfgFragmentChainOfblocksWithSameSucc::detectOne(BB, exit);
	if (frag.second.has_value()) {
		// matched one block of CfgFragmentChainOfblocksWithSameSucc
		// now we have to check if it also contains correct stream write
		auto wr = HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock(Builder,
				*frag.second.value().BB, SQ);
		if (!wr)
			return {nullptr, {}};

		auto wrStreamIo = streamWriteGetIoArg(wr);
		if (streamIoPtr) {
			if (streamIoPtr != wrStreamIo)
				return {nullptr, {}};
		} else {
			streamIoPtr = wrStreamIo; // case for first part of the fragment just found
		}
		BasicBlockWithStreamWriteAndBrCond bbWithStream(frag.second.value(),
				wr);
		return {frag.first, bbWithStream};
	}
	return {nullptr, {}};
}

std::optional<CfgFragmentStreamWriteVariableLen> CfgFragmentStreamWriteVariableLen::detect(
		llvm::IRBuilderBase &Builder, llvm::SimplifyQuery &SQ,
		llvm::BasicBlock &searchBegin, llvm::BasicBlock &exitBB) {
	CfgFragmentStreamWriteVariableLen res(Builder, SQ);
	return CfgFragmentChainOfblocksWithSameSucc::detect<
			CfgFragmentStreamWriteVariableLen,
			CfgFragmentStreamWriteVariableLen::BasicBlockWithStreamWriteAndBrCond>(
			exitBB, res, &searchBegin, /*exitMayHaveAdditionalPreds*/true);
}

}
