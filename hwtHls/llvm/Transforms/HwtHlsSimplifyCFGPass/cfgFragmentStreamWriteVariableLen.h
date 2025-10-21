#pragma once
#include <llvm/IR/Instructions.h>
#include <llvm/ADT/SmallVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentChainOfblocksWithSameSucc.h>

namespace llvm {
class SimplifyQuery;
}

namespace hwtHls {

/*
 * Structure for pattern:
 * .. code-block::text
 *      bb0-bb1-bb2 ... # sequence of blocks containing stream write to same out,
 *        \  \  \       #  only bb0 is allowed to have multiple predecessors
 *          exitbb      #  only bb0 may contain non hoistable instructions
 *                      # :note: common exitbb is important because if it is not detected
 *                      #   it is not certain whenever hoist from other branches should be performed first
 * */
struct CfgFragmentStreamWriteVariableLen: public CfgFragmentChainOfblocksWithSameSucc {
public:
	llvm::IRBuilderBase &Builder;
	llvm::SimplifyQuery &SQ;
	llvm::Value *streamIoPtr;

	struct BasicBlockWithStreamWriteAndBrCond: BasicBlockAndBrCond {
		llvm::CallInst *streamWrite;
		BasicBlockWithStreamWriteAndBrCond(const BasicBlockAndBrCond &bbAndCond,
				llvm::CallInst *streamWrite);
	};
	llvm::SmallVector<BasicBlockWithStreamWriteAndBrCond> blocks;

	CfgFragmentStreamWriteVariableLen(llvm::IRBuilderBase &Builder,
			llvm::SimplifyQuery &SQ);
	std::pair<llvm::BasicBlock*,
			std::optional<
					CfgFragmentStreamWriteVariableLen::BasicBlockWithStreamWriteAndBrCond>> detectOne(
			llvm::BasicBlock &BB, llvm::BasicBlock &exit);
	// :note: searchBegin is required because there may be multiple separate block sequence matched by this function in exitBB predecessors
	//    inf only exitBB would be specified only the first sequence would be possible to find
	static std::optional<CfgFragmentStreamWriteVariableLen> detect(
			llvm::IRBuilderBase &Builder, llvm::SimplifyQuery &SQ,
			llvm::BasicBlock &searchBegin, llvm::BasicBlock &exitBB);
};

}
