#pragma once
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/TargetTransformInfo.h>

namespace hwtHls {
// :note: this should be the only modified function, the modification is that
//    this implementation preserves loop metadata
bool SimplifyCondBranchToCondBranch(llvm::BranchInst *PBI, llvm::BranchInst *BI,
		llvm::DomTreeUpdater *DTU, const llvm::DataLayout &DL,
		const llvm::TargetTransformInfo &TTI);
}
