#pragma once

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

// Convert the loop into format where it has only 1 latch and up to 1 exit block
// This conversion collect all latches/exits and creates a proxy block with
// switch /cond branch. to jump in to proper latch/exit.
//
// :note: The 1 latch/exit per loop is useful for transformations
//        which are modifying/extracting loop body as loop body will
//        form single entry (header)-single exit (newLatch) region.
void formDedicatedUniqueLoopExitingAndLatchBB(
	llvm::IRBuilder<> &Builder, llvm::DomTreeUpdater &DTU, llvm::LoopInfo &LI,
	llvm::Loop *L, llvm::SmallVector<llvm::AllocaInst *> &tmpAllocas);

// Variant which processes all loops in LI.
void formDedicatedUniqueLoopExitingAndLatchBB(
	llvm::IRBuilder<> &Builder, llvm::DomTreeUpdater &DTU, llvm::LoopInfo &LI,
	llvm::FunctionAnalysisManager &FAM_forDebug);

}
