#pragma once
#include <llvm/IR/Dominators.h>

namespace hwtHls {
bool hoistIntoDominatingBlock(llvm::Value &V, llvm::Instruction &insertPoint,
		const llvm::DominatorTree &DT);
}
