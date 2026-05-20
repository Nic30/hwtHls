#pragma once

#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Transforms/Utils/LoopSimplify.h>
#include <llvm/Transforms/Utils/LoopUtils.h>

namespace hwtHls {

bool normalizeLoopsForUnrolling(llvm::LoopInfo &LI, llvm::DominatorTree &DT,
								llvm::ScalarEvolution *SE,
								llvm::AssumptionCache *AC);
}