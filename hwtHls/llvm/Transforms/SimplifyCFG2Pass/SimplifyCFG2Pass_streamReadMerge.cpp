#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_streamWriteMerge.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFGUtils.h>
#include <llvm/IR/IRBuilder.h>

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/ValueTracking.h>

#include <llvm/Analysis/InstructionSimplify.h>

#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/cfgFragmentStreamReadUntilEoF.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

#define DEBUG_TYPE "simplifycfg2"
//#define DBG_VERIFY_AFTER_EVERY_MODIFICATION

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <llvm/IR/Verifier.h>
#endif

using namespace llvm;

namespace hwtHls {

bool SimplifyCFG2Pass_streamReadMerge(IRBuilderBase & Builder, llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BBContainingStreamRead, llvm::SimplifyQuery &SQ) {
	// :attention: detect may merge streamReads instructions
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	auto &F = *BBContainingStreamRead.getParent();
	assert(!verifyFunction(*BBContainingStreamRead.getParent(), &errs()));
#endif
	auto _reads = StreamReadUntilEoFCFGFragment::detect(Builder, BBContainingStreamRead);
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
	StreamReadUntilEoFCFGFragment::mergeReads(Builder, reads.streamProps.value(), reads.reads);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(F, &errs()));
#endif
	return true;
}

}
