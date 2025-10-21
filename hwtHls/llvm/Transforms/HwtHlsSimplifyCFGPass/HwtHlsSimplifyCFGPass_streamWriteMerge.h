#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>

namespace llvm {
class DomTreeUpdater;
class SimplifyQuery;
}

namespace hwtHls {

llvm::CallInst* HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock(
		llvm::IRBuilderBase &Builder, llvm::BasicBlock &BBPossiblyContainingStreamWrite,
		llvm::SimplifyQuery &SQ);
/*
 *  .. code-block:: python3
 *
 *    #  wr0.guard
 *    #   /   \
 *    # w0    w0.else
 *    #   \   /
 *    #  wr0.exit
 *    #  wr1.guard
 *    #   /   \
 *    # w1    w1.else
 *    #   \   /
 *    #  wr1.exit
 *
 *    if c0:
 *       tx.write(v0)
 *    if c1:
 *       tx.write(v1)
 *
 *    # or
 *    # wr0-wr1-...
 *    #   \  |  /
 *    #   bb.exit
 *
 *    if c0:
 *      tx.write(v0)
 *      if c1:
 *         tx.write(v1)
 *
 *    # to (if c1 ==> c0)
 *    tx.write(Concat(v1, v0), mask=Concat(c1, c0), eof=v0.eof | v1.eof)
*/
bool HwtHlsSimplifyCFGPass_streamWriteMerge(llvm::IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU, llvm::BasicBlock &BBMaybeContainingStreamWrite,
		llvm::SimplifyQuery &SQ);

}
