#pragma once
#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/TargetFolder.h>

namespace hwtHls {

void AddDefaultFunctionAttributes(llvm::Function &TheFn);
std::string Intrinsic_getName(const std::string &baseName,
		llvm::ArrayRef<llvm::Type*> Tys);
std::string getMangledTypeStr(llvm::Type *Ty, bool &HasUnnamedType);

void IRBuilder_setInsertPointBehindPhi(llvm::IRBuilderBase &builder,
		llvm::Instruction *I);
}
