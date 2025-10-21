#pragma once

#include <llvm/IR/BasicBlock.h>

namespace llvm {
class DomTreeUpdater;
class SimplifyQuery;
}

namespace hwtHls {

/**
 * This optimization detect of block which conditionally read data until eof
 * and merges them into a single unreliable read
 * BB0-BB1 ...
 *   \ |  /
 *  BB.exit
 *
 * .. code-block:: python3
 *
 *    # bb0
 *    r0 = rx.read(u8)
 *    if ~r0._isEoF():
 *       # bb1
 *       r1 = rx.read(u8)
 *    # BB.exit
 *
 *    # to
 *    r01 = rx.read(u16, reliable=False)
*/
bool HwtHlsSimplifyCFGPass_streamReadMerge(llvm::IRBuilderBase & Builder, llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BBContainingStreamRead, llvm::SimplifyQuery &SQ);

}
