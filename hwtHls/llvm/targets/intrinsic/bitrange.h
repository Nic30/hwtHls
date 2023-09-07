#pragma once
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

namespace hwtHls {

// :attention: BitRangeGet is always created directly behind the sliced bitVec instead of insertion point of a builder
extern const std::string BitRangeGetName;
// search for existing BitRangeGet instruction directly behind the definition of bitVec
llvm::Value* SearchBitRangeGet(llvm::Instruction *bitVec, llvm::Value *lowBitNo,
		size_t bitWidth);
llvm::Value* CreateBitRangeGetConst(llvm::IRBuilder<> *Builder,
		llvm::Value *bitVec, size_t lowBitNo, size_t bitWidth);
// lowBitNo must be constant and must be added into the name of function so variants with different lowBitNo will not get merged to a single instruction
llvm::Value* CreateBitRangeGet(llvm::IRBuilder<> *Builder, llvm::Value *bitVec,
		llvm::Value *lowBitNo, size_t bitWidth);
bool IsBitRangeGet(const llvm::CallInst *C);
bool IsBitRangeGet(const llvm::Function *F);

extern const std::string BitConcatName;
/*
 * :note: operands does not have to be of same type
 * */
llvm::Value* CreateBitConcat(llvm::IRBuilder<> *Builder,
		llvm::ArrayRef<llvm::Value*> OpsLowFirst);

bool IsBitConcat(const llvm::CallInst *C);
bool IsBitConcat(const llvm::Function *F);
}
