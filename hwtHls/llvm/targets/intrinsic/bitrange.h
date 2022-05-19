#pragma once
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

extern const std::string BitRangeGetName;
llvm::CallInst* CreateBitRangeGet(llvm::IRBuilder<> *Builder,
		llvm::Value *bitVec, llvm::Value *lowBitNo, size_t bitWidth);
bool IsBitRangeGet(const llvm::CallInst * C);
bool IsBitRangeGet(const llvm::Function * F);

extern const std::string BitConcatName;
llvm::CallInst* CreateBitConcat(llvm::IRBuilder<> *Builder,
		llvm::ArrayRef<llvm::Value*> OpsHighFirst);
bool IsBitConcat(const llvm::CallInst * C);
bool IsBitConcat(const llvm::Function * F);