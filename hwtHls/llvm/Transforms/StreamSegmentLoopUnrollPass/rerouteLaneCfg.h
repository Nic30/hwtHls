#pragma once

#include <map>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/IRBuilder.h>

#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <llvm/Transforms/Utils/ValueMapper.h>

namespace hwtHls {

// :attention: invalidates LI
void rerouteLaneCfgAndSegmentValue(llvm::IRBuilder<> &Builder, llvm::Function &F,
		llvm::DomTreeUpdater &DTU,
		llvm::LoopInfo & LI,
		const StreamChannelProps &streamProps,
		std::vector<llvm::AllocaInst*> &tmpAllocas,
		const llvm::SmallVector<llvm::Instruction*> &IoInstructions,
		const std::unique_ptr<llvm::ValueToValueMapTy[]> &valueMaps,
		std::map<llvm::BasicBlock*, unsigned> &BBToLaneIndex,
		std::map<llvm::BasicBlock*, unsigned> &BBToIndexInloopBodyCopies,
		const llvm::SmallVector<llvm::SmallVector<llvm::BasicBlock*>> &loopBodyCopies,
		const std::optional<llvm::SmallVector<int>> &allowSoFOnlyFor);
}
