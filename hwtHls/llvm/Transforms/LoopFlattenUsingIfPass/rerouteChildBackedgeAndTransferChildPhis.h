#pragma once

#include <map>

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>
#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass.h>

namespace hwtHls {

void rerouteChildBackedgeAndTransferChildPhis(const LoopFlattenUsingIfPass::Mode mode, llvm::BasicBlock *childPreHeader,
		llvm::BasicBlock *childHeader, llvm::BasicBlock *extractedSectionGuard,
		llvm::Loop &LChild, llvm::BasicBlock *oldLatchBlock,
		llvm::BasicBlock *newLatchBlock, llvm::BasicBlock *parentHeader,
		llvm::Loop &LParent, llvm::PHINode *phiInLatchDrivingBranch,
		llvm::Value *valueForPhiInLatchCausingReenter, llvm::PHINode &isChildLoopSwitchPhi,
		const std::map<llvm::PHINode*, llvm::PHINode*> &associatedPhis,
		llvm::MemorySSAUpdater *MSSAU, llvm::DomTreeUpdater &DTU);

}
