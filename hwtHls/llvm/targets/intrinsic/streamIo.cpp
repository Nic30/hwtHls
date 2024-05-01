#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <llvm/ADT/StringExtras.h>

using namespace llvm;

namespace hwtHls {

const std::string StreamReadName = "hwtHls.streamRead";
CallInst* CreateStreamRead(IRBuilder<> *Builder, Value *ioArgPtr,
		size_t chunkBitWidth, size_t returnBitWidth) {
	assert(ioArgPtr->getType()->isPointerTy());
	if (chunkBitWidth > returnBitWidth) {
		throw std::runtime_error(
				"CreateStreamRead must have chunkBitWidth <= returnBitWidth");
	}

	Value *Ops[] = { ioArgPtr, Builder->getInt64(chunkBitWidth) };
	Type *ResT = Builder->getIntNTy(returnBitWidth);
	Type *TysForName[] = { Ops[0]->getType(), Ops[1]->getType(), ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(StreamReadName, TysForName), ResT,
					Ops[0]->getType(), Ops[1]->getType()).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setOnlyAccessesArgMemory();
	return CI;
}

bool IsStreamRead(const llvm::CallInst *C) {
	return IsStreamRead(C->getCalledFunction());
}
bool IsStreamRead(const llvm::Function *F) {
	return F->getName().str().rfind(StreamReadName + ".", 0) == 0;
}
size_t streamReadGetOrigChunkBitWidth(const CallInst *I) {
	auto _chunkBitWidth = I->getArgOperand(1);
	auto chunkBitWidth = dyn_cast<ConstantInt>(_chunkBitWidth);
	assert(
			chunkBitWidth
					&& "Second arg of streamRead must always be const int");
	return chunkBitWidth->getSExtValue();
}


const std::string StreamReadStartOfFrameName = "hwtHls.streamReadStartOfFrame";
template<const std::string &NAME>
CallInst* CreateStreamMarker(IRBuilder<> *Builder, Value *ioArgPtr) {
	assert(ioArgPtr->getType()->isPointerTy());
	Value *Ops[] = { ioArgPtr };
	Type *ResT = Builder->getVoidTy();
	Type *TysForName[] = { Ops[0]->getType(), ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(Intrinsic_getName(NAME, TysForName), ResT,
					Ops[0]->getType()).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setOnlyAccessesArgMemory();
	return CI;
}
CallInst* CreateStreamReadStartOfFrame(IRBuilder<> *Builder, Value *ioArgPtr) {
	return CreateStreamMarker<StreamReadStartOfFrameName>(Builder, ioArgPtr);
}

bool IsStreamReadStartOfFrame(const llvm::CallInst *C) {
	return IsStreamReadStartOfFrame(C->getCalledFunction());
}
bool IsStreamReadStartOfFrame(const llvm::Function *F) {
	return F->getName().str().rfind(StreamReadStartOfFrameName + ".", 0) == 0;
}

const std::string StreamReadEndOfFrameName = "hwtHls.streamReadEndOfFrame";
CallInst* CreateStreamReadEndOfFrame(IRBuilder<> *Builder, Value *ioArgPtr) {
	return CreateStreamMarker<StreamReadEndOfFrameName>(Builder, ioArgPtr);
}
bool IsStreamReadEndOfFrame(const llvm::CallInst *C) {
	return IsStreamReadEndOfFrame(C->getCalledFunction());
}
bool IsStreamReadEndOfFrame(const llvm::Function *F) {
	return F->getName().str().rfind(StreamReadEndOfFrameName + ".", 0) == 0;
}

const std::string StreamWriteName = "hwtHls.streamWrite";
CallInst* CreateStreamWrite(IRBuilder<> *Builder, Value *ioArgPtr,
		llvm::Value *valueToWrite) {
	assert(ioArgPtr->getType()->isPointerTy());
	Value *Ops[] = { ioArgPtr, valueToWrite };
	Type *ResT = Builder->getVoidTy();
	Type *TysForName[] = { Ops[0]->getType(), Ops[1]->getType(), ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(StreamWriteName, TysForName), ResT,
					Ops[0]->getType(), Ops[1]->getType()).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setOnlyAccessesArgMemory();
	return CI;
}
size_t streamWriteGetOrigChunkBitWidth(const CallInst *I) {
	return I->getArgOperand(1)->getType()->getIntegerBitWidth();
}
bool IsStreamWrite(const llvm::CallInst *C) {
	return IsStreamWrite(C->getCalledFunction());
}
bool IsStreamWrite(const llvm::Function *F) {
	return F->getName().str().rfind(StreamWriteName + ".", 0) == 0;
}

const std::string StreamWriteStartOfFrameName = "hwtHls.streamWriteStartOfFrame";
CallInst* CreateStreamWriteStartOfFrame(IRBuilder<> *Builder, Value *ioArgPtr) {
	return CreateStreamMarker<StreamWriteStartOfFrameName>(Builder, ioArgPtr);
}

bool IsStreamWriteStartOfFrame(const llvm::CallInst *C) {
	return IsStreamWriteStartOfFrame(C->getCalledFunction());
}
bool IsStreamWriteStartOfFrame(const llvm::Function *F) {
	return F->getName().str().rfind(StreamWriteStartOfFrameName + ".", 0) == 0;
}

const std::string StreamWriteEndOfFrameName = "hwtHls.streamWriteEndOfFrame";
CallInst* CreateStreamWriteEndOfFrame(IRBuilder<> *Builder, Value *ioArgPtr) {
	return CreateStreamMarker<StreamWriteEndOfFrameName>(Builder, ioArgPtr);
}
bool IsStreamWriteEndOfFrame(const llvm::CallInst *C) {
	return IsStreamWriteEndOfFrame(C->getCalledFunction());
}
bool IsStreamWriteEndOfFrame(const llvm::Function *F) {
	return F->getName().str().rfind(StreamWriteEndOfFrameName + ".", 0) == 0;
}


bool IsStreamIo(const llvm::CallInst *C) {
	auto * F = C->getCalledFunction();
	return F->getName().str().rfind("hwtHls.stream") == 0;
}
size_t streamIoGetOrigChunkBitWidth(const llvm::CallInst *I) {
	if (IsStreamRead(I)) {
		return streamReadGetOrigChunkBitWidth(I);
	} else if (IsStreamWrite(I)) {
		return streamWriteGetOrigChunkBitWidth(I);
	} else {
		assert(IsStreamIoStartOfFrame(I) || IsStreamIoEndOfFrame(I));
		return 0;
	}
}

}
