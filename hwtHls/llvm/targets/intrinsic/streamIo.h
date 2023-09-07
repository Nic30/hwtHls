#pragma once
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

namespace hwtHls {

extern const std::string StreamReadName;

llvm::CallInst* CreateStreamRead(llvm::IRBuilder<> *Builder, llvm::Value *ioArg,
		size_t chunkBitWidth, size_t returnBitWidth);
bool IsStreamRead(const llvm::CallInst *C);
bool IsStreamRead(const llvm::Function *F);
size_t streamReadGetOrigChunkBitWidth(const llvm::CallInst *C);

extern const std::string StreamReadStartOfFrameName;
llvm::CallInst* CreateStreamReadStartOfFrame(llvm::IRBuilder<> *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamReadStartOfFrame(const llvm::CallInst *C);
bool IsStreamReadStartOfFrame(const llvm::Function *F);

extern const std::string StreamReadEndOfFrameName;
llvm::CallInst* CreateStreamReadEndOfFrame(llvm::IRBuilder<> *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamReadEndOfFrame(const llvm::CallInst *C);
bool IsStreamReadEndOfFrame(const llvm::Function *F);

extern const std::string StreamWriteName;
llvm::CallInst* CreateStreamWrite(llvm::IRBuilder<> *Builder,
		llvm::Value *ioArg, llvm::Value *valueToWrite);
bool IsStreamWrite(const llvm::CallInst *C);
bool IsStreamWrite(const llvm::Function *F);
size_t streamWriteGetOrigChunkBitWidth(const llvm::CallInst *C);

extern const std::string StreamWriteStartOfFrameName;
llvm::CallInst* CreateStreamWriteStartOfFrame(llvm::IRBuilder<> *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamWriteStartOfFrame(const llvm::CallInst *C);
bool IsStreamWriteStartOfFrame(const llvm::Function *F);

extern const std::string StreamWriteEndOfFrameName;
llvm::CallInst* CreateStreamWriteEndOfFrame(llvm::IRBuilder<> *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamWriteEndOfFrame(const llvm::CallInst *C);
bool IsStreamWriteEndOfFrame(const llvm::Function *F);

bool IsStreamIo(const llvm::CallInst *C);
size_t streamIoGetOrigChunkBitWidth(const llvm::CallInst *I);

inline bool IsStreamIoStartOfFrame(const llvm::CallInst *I) {
	return IsStreamReadStartOfFrame(I) || IsStreamWriteStartOfFrame(I);
}
inline bool IsStreamIoEndOfFrame(const llvm::CallInst *I) {
	return IsStreamReadEndOfFrame(I) || IsStreamWriteEndOfFrame(I);
}

}
