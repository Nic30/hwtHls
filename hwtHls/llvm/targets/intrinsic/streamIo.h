#pragma once
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

namespace hwtHls {

extern const std::string StreamTmpAllocaTmpSetterPlaceholder;
// create a call of function which will acts a placeholder setter to prevent removal of the alloca
// while its driving logic was not constructed yet
llvm::CallInst* CreateStreamTmpAllocaTmpSetterPlaceholder(llvm::IRBuilderBase *Builder,
		llvm::AllocaInst *tmpAlloca);
bool IsStreamTmpAllocaTmpSetterPlaceholder(const llvm::CallInst *C);
bool IsStreamTmpAllocaTmpSetterPlaceholder(const llvm::Function *F);


extern const std::string StreamReadName;

llvm::CallInst* CreateStreamRead(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArg, size_t chunkBitWidth, size_t returnBitWidth,
		bool isReliable);
bool IsStreamRead(const llvm::CallInst *C);
bool IsStreamRead(const llvm::Function *F);
// get number of bits of data which this instruction actually read from stream,
// the type of instruction may contain additional things like mask/eof
size_t streamReadGetOrigChunkBitWidth(const llvm::CallInst *C);
// :returns: true if EoF is an EoF of specified read instruction
bool streamReadGetIsReliable(const llvm::CallInst *C);
// :deprecated: use StreamChannelFormatInfo::streamReadGetEoF
// bool IsStreamReadEoF(const llvm::CallInst *read, llvm::Value *EoF);

extern const std::string StreamReadStartOfFrameName;
llvm::CallInst* CreateStreamReadStartOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamReadStartOfFrame(const llvm::CallInst *C);
bool IsStreamReadStartOfFrame(const llvm::Function *F);

extern const std::string StreamReadEndOfFrameName;
llvm::CallInst* CreateStreamReadEndOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamReadEndOfFrame(const llvm::CallInst *C);
bool IsStreamReadEndOfFrame(const llvm::Function *F);

extern const std::string StreamWriteName;
extern const std::string StreamWriteMaskedName;
// The writeMask must be all ones if this is not first or last word
// in first word it may have 0 prefix, in last word it may have 0 suffix
// :note: The masked variant of StreamWrite exists to make compilation faster as it is more easy to work with the mask
//    than searching for chained writes in a complex CFG.
llvm::CallInst* CreateStreamWrite(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArg, llvm::Value *valueToWrite,
		llvm::Value *writeMaskOrEmpty = nullptr, llvm::Value *isSoF = nullptr,
		llvm::Value *isEoF = nullptr);
bool IsStreamWrite(const llvm::CallInst *C);
bool IsStreamWrite(const llvm::Function *F);
bool IsStreamWriteMasked(const llvm::CallInst *C);
bool IsStreamWriteMasked(const llvm::Function *F);

size_t streamWriteGetOrigChunkBitWidth(const llvm::CallInst *C);
llvm::Value* streamWriteGetIoArg(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteData(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteMaskOrEmpty(const llvm::CallInst *C);
//llvm::Value* streamWriteGetWriteError(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteSoF(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteEoF(const llvm::CallInst *C);

extern const std::string StreamWriteStartOfFrameName;
llvm::CallInst* CreateStreamWriteStartOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamWriteStartOfFrame(const llvm::CallInst *C);
bool IsStreamWriteStartOfFrame(const llvm::Function *F);

extern const std::string StreamWriteEndOfFrameName;
llvm::CallInst* CreateStreamWriteEndOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamWriteEndOfFrame(const llvm::CallInst *C);
bool IsStreamWriteEndOfFrame(const llvm::Function *F);

inline bool IsStreamIoStartOfFrame(const llvm::CallInst *I) {
	return IsStreamReadStartOfFrame(I) || IsStreamWriteStartOfFrame(I);
}
inline bool IsStreamIoEndOfFrame(const llvm::CallInst *I) {
	return IsStreamReadEndOfFrame(I) || IsStreamWriteEndOfFrame(I);
}
// :returns: true if the function is hwtHls.stream intrinsic
bool IsStreamIo(const llvm::CallInst *C);
size_t streamIoGetOrigChunkBitWidth(const llvm::CallInst *I);

}
