#pragma once
#include <map>
#include <unordered_map>

#include <llvm/Transforms/Utils/ValueMapper.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>

#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

namespace hwtHls {

// create a clone of each BB streamProps.segmentCnt times
void copyCodeForLanes(const StreamChannelProps &streamProps, llvm::LoopInfo &LI,
		llvm::Loop &currentLoop, llvm::DomTreeUpdater &DTU,
		const llvm::SmallVector<llvm::BasicBlock*> &BBs,
		llvm::SmallVector<llvm::SmallVector<llvm::BasicBlock*> > &loopBodyCopies,
		const std::unique_ptr<llvm::ValueToValueMapTy[]> &valueMaps,
		llvm::Function &F);

void buildBlockIndexMaps(
		const llvm::SmallVector<llvm::SmallVector<llvm::BasicBlock*> > &loopBodyCopies,
		std::map<llvm::BasicBlock*, unsigned> &BBToIndexInloopBodyCopies,
		std::map<llvm::BasicBlock*, unsigned> &BBToLaneIndex);

void buildSegmentValueTmpVars(const StreamChannelProps &streamProps,
		llvm::SmallVector<llvm::AllocaInst*> &segmentValueTmps,
		llvm::Function &F, llvm::Argument &IoArg);

void replaceSegmentLoadInstWithLoadFromTmpVar(llvm::IRBuilder<> &Builder,
		const std::unique_ptr<llvm::ValueToValueMapTy[]> &valueMaps,
		llvm::Argument &IoArg, llvm::Type *busWordTy,
		const StreamChannelProps &streamProps, size_t segmentWordWidth,
		const llvm::SmallVector<llvm::AllocaInst*> &segmentValueTmps,
		std::unordered_map<llvm::BasicBlock*, llvm::LoadInst*> &segmentWordTmpLdForBBs,
		const std::map<llvm::BasicBlock*, unsigned> &BBToLaneIndex,
		llvm::Instruction &I);
}
