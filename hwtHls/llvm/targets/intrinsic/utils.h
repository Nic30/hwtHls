#pragma once
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

void AddDefaultFunctionAttributes(llvm::Function &TheFn);
std::string Intrinsic_getName(const std::string &baseName,
		llvm::ArrayRef<llvm::Type*> Tys);
std::string getMangledTypeStr(llvm::Type *Ty);
void IRBuilder_setInsertPointBehindPhi(llvm::IRBuilder<> &builder,
		llvm::Instruction *I);

}
