#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamWriteMerge.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/IR/IRBuilder.h>

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/InstructionSimplify.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentStreamReadUntilEoF.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>


using namespace llvm;

namespace hwtHls {

// based on llvm18 JumpThreadingPass::findLoopHeaders(Function &F)
void findLoopHeaders(Function &F, llvm::SmallPtrSetImpl<const llvm::BasicBlock*> & LoopHeaders) {
  SmallVector<std::pair<const BasicBlock*,const BasicBlock*>, 32> Edges;
  FindFunctionBackedges(F, Edges);

  for (const auto &Edge : Edges)
    LoopHeaders.insert(Edge.second);
}

bool HwtHlsSimplifyCFGPass_streamReadMerge(IRBuilderBase & Builder, llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BBContainingStreamRead, llvm::SimplifyQuery &SQ) {
	// :attention: detect may merge streamReads instructions
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	auto &F = *BBContainingStreamRead.getParent();
	assert(!verifyFunction(*BBContainingStreamRead.getParent(), &errs()));
#endif
	SmallPtrSet<const BasicBlock*, 16> LoopHeaders;
	findLoopHeaders(*BBContainingStreamRead.getParent(), LoopHeaders);
	auto _reads = StreamReadUntilEoFCFGFragment::detect(Builder, BBContainingStreamRead, LoopHeaders);
	if (!_reads.has_value()) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(F, &errs()));
#endif
		return false;
	}
	auto & reads = _reads.value();
	if (!reads.streamProps.has_value()) {
		assert(isa<Argument>(reads.ioPtr));
		reads.streamProps = StreamChannelFormatInfo::findInMetadata(*cast<Argument>(reads.ioPtr));
	}
	auto &DT = DTU.getDomTree();
	auto BB0 = reads.reads[0]->getParent();
	for (auto r: reads.reads) {
		auto BB = r->getParent();
		if (BB == BB0)
			continue;
		if (!DT.dominates(BB0, BB))
			return false;
	}
	StreamReadUntilEoFCFGFragment::mergeReads(Builder, reads.streamProps.value(), reads.reads);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(F, &errs()));
#endif
	return true;
}

}
