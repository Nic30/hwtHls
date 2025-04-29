#pragma once

#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>


namespace hwtHls {

// :attention: BitRangeGet is always created directly behind the sliced bitVec instead of insertion point of a builder
extern const std::string BitRangeGetName;
// search for existing BitRangeGet instruction directly behind the definition of bitVec
llvm::Value* SearchBitRangeGet(llvm::Instruction *bitVec, llvm::Value *lowBitNo,
		size_t bitWidth);
llvm::Value* SearchBitRangeGetConst(llvm::Instruction *bitVec, size_t lowBitNo,
		size_t bitWidth);
llvm::Value* CreateBitRangeGetConst(llvm::IRBuilderBase *Builder,
		llvm::Value *bitVec, size_t lowBitNo, size_t bitWidth, const llvm::Twine &Name = "");

// lowBitNo must be constant and must be added into the name of function so variants with different lowBitNo will not get merged to a single instruction
llvm::Value* CreateBitRangeGet(llvm::IRBuilderBase *Builder, llvm::Value *bitVec,
		llvm::Value *lowBitNo, size_t bitWidth, const llvm::Twine &Name = "");
bool IsBitRangeGetInst(const llvm::Instruction *I);
bool IsBitRangeGet(const llvm::CallInst *C);
bool IsBitRangeGet(const llvm::Function *F);
llvm::Value* BitRangeGetSrc(const llvm::CallInst *C);
size_t BitRangeGetOffset(const llvm::CallInst *C);

extern const std::string BitConcatName;
/*
 * :note: operands does not have to be of same type
 * */
llvm::Value* CreateBitConcat(llvm::IRBuilderBase *Builder,
		llvm::ArrayRef<llvm::Value*> OpsLowFirst, const llvm::Twine &Name = "");

bool IsBitConcatInst(const llvm::Instruction *I);
bool IsBitConcat(const llvm::CallInst *C);
bool IsBitConcat(const llvm::Function *F);

bool isAnyFormOfBitRangeGet(llvm::Instruction *I);
bool isAnyFormOfBitRangeGet(llvm::Instruction *I, llvm::Value *&src);
bool isAnyFormOfBitRangeGet(llvm::Instruction *I, llvm::Value *&src, size_t& offset);

}
