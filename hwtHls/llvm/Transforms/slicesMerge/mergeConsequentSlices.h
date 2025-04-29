#pragma once

#include <llvm/IR/Instructions.h>

namespace hwtHls {

bool IsBitwiseOperator(const llvm::BinaryOperator &I);
bool IsBitwiseInstruction(const llvm::Instruction &I);

std::pair<llvm::Value*, uint64_t> getSliceOffset(llvm::Value *op0);

}

