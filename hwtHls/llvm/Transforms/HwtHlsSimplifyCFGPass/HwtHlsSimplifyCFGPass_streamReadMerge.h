#pragma once

#include <llvm/IR/BasicBlock.h>

namespace llvm {
class DomTreeUpdater;
class SimplifyQuery;
}

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_streamReadMerge(llvm::IRBuilderBase & Builder, llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BBContainingStreamRead, llvm::SimplifyQuery &SQ);

}
