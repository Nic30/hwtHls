#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>

namespace llvm {
class DomTreeUpdater;
class SimplifyQuery;
}

namespace hwtHls {

bool SimplifyCFG2Pass_streamWriteMerge(llvm::IRBuilderBase & Builder, llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BBContainingStreamWrite, llvm::SimplifyQuery &SQ);

}
