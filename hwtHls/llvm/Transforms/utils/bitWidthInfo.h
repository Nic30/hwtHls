#pragma once
#include <llvm/IR/Value.h>
#include <llvm/IR/Type.h>

namespace hwtHls {

inline size_t getIntegerBitWidthOr1(const llvm::Value * v) {
	auto Ty = v->getType();
	return Ty->isIntegerTy() ? Ty->getIntegerBitWidth() : 1;
}

}
