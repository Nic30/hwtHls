#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Transforms/Utils/UnrollLoop.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/cfgFragmentStreamCopyLikeLoop.h>

namespace hwtHls {

// :see: llvm::UnrollLoop
llvm::LoopUnrollResult UnrollLoopStreamCopyLike(llvm::Function& F, llvm::Loop *L,
		llvm::UnrollLoopOptions ULO, llvm::LoopInfo *LI,
		llvm::ScalarEvolution *SE, llvm::DominatorTree *DT,
		llvm::AssumptionCache *AC, const llvm::TargetTransformInfo *TTI,
		llvm::OptimizationRemarkEmitter *ORE, bool PreserveLCSSA,
		CfgFragmentStreamCopyLikeLoop &cpFrag, llvm::IRBuilder<> &Builder,
		StreamChannelProps & streamProps,
		llvm::Loop **RemainderLoop = nullptr);
}
