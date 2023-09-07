#pragma once
#include <llvm/IR/PassManager.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoInstrCollector.h>

namespace llvm {
class DomTreeUpdater;
class LoopInfo;
class DominatorTree;
}

namespace hwtHls {

class StreamIoRewriter {
protected:
	std::pair<std::vector<llvm::BasicBlock*>, llvm::BasicBlock*> _createBranchForEachOffsetVariant(
			llvm::IRBuilder<> &builder,
			const std::vector<size_t> &possibleOffsets);
public:
	StreamIoDetector &cfg;
	const StreamChannelProps &streamProps;
	llvm::DomTreeUpdater *DTU;
	llvm::LoopInfo *LI;

	StreamIoRewriter(StreamIoDetector &cfg,
			const StreamChannelProps &streamProps, llvm::DomTreeUpdater *DTU,
			llvm::LoopInfo *LI);
	void rewriteAdtAccessToWordAccess(llvm::BasicBlock &_curBlock);
	virtual void _rewriteAdtAccessToWordAccessInstruction(
			StreamIoDetector::HlsReadOrWrite *read) = 0;
	virtual ~StreamIoRewriter() = default;
};
void finalizeStreamIoLowerig(llvm::Function &F,
		llvm::FunctionAnalysisManager &FAM, llvm::DominatorTree &DT,
		const std::vector<StreamChannelProps> &streamProps, bool rmOutputs,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas);
}
