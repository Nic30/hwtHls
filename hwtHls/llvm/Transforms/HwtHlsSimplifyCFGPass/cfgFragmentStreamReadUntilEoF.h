#pragma once
#include <llvm/IR/Instructions.h>
//#include <llvm/Analysis/DomTreeUpdater.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>

namespace llvm {
class IRBuilderBase;
}

namespace hwtHls {

/*
 * Structure for pattern with linear sequence of blocks with a common successor which is on T branch and branch condition is EoF of each read:
 * .. code-block::text
 *      BB0-BB1 ...
 *        \ |  /
 *        exit
 * */
struct StreamReadUntilEoFCFGFragment {
public:

	llvm::Value *ioPtr;
	llvm::SmallVector<llvm::CallInst*> reads;
	llvm::BasicBlock *exit;
	std::optional<StreamChannelFormatInfo> streamProps;

	StreamReadUntilEoFCFGFragment();
	// :attention: merges streamReads in same block into first one
	static std::optional<StreamReadUntilEoFCFGFragment> detect(
			llvm::IRBuilderBase &Builder, llvm::BasicBlock &BlockWithRead,
			llvm::SmallPtrSetImpl<const llvm::BasicBlock*> &LoopHeaders);

	static llvm::CallInst* mergeReads(llvm::IRBuilderBase &Builder,
			//llvm::DomTreeUpdater &DTU,
			const StreamChannelFormatInfo &streamProps,
			const llvm::SmallVector<llvm::CallInst*> &reads);
};

}
