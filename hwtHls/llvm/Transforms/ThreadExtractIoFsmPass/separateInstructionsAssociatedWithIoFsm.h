#pragma once

#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Transforms/Utils/ValueMapper.h>

#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractorIoArgUtils.h>


namespace hwtHls {

/*
 * :param argsToAddToOldFn: records about tmp allocas for communication channels between
 *                          new (extracted) and old (original) function on old function side
 * :param argsToAddToNewFn: same as argsToAddToOldFn just for new function
 * */
void separateInstructionsAssociatedWithIoFsm(llvm::IRBuilder<> &Builder,
		llvm::Argument &Arg, llvm::Function &F, llvm::Function &extractedF,
		llvm::ValueToValueMapTy &VMap, llvm::DomTreeUpdater &DUT, llvm::LoopInfo &LI,
		llvm::SmallVector<ArgToAddToParentFn> &argsToAddToOldFn,
		llvm::SmallVector<ArgToAddToParentFn> &argsToAddToNewFn);
}
