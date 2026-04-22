#pragma once

#include <llvm/Analysis/PostDominators.h>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

/// https://doi.org/10.48550/arXiv.2510.04890
/// This function is used to resolve mapping IOStore instruction to a minimal
/// number of lanes. The clique represent 1 lane in vector and may be
/// occupied by multiple mutually exclusive instructions from IOStores.
llvm::SmallVector<llvm::SmallVector<llvm::StoreInst *>>
findComplementaryCliques(llvm::ArrayRef<llvm::StoreInst *>& IOStores,
						 llvm::PostDominatorTree &PDT);
} // namespace hwtHls