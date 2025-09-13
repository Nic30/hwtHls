#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

#include <llvm/ADT/StringExtras.h>

#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

inline static void setArgNames(Function &F, ArrayRef<const char*> argNames) {
	size_t argI = 0;
	for (auto name : argNames) {
		assert(argI < F.arg_size());
		F.getArg(0)->setName(name);
	}
}

const std::string StreamTmpAllocaTmpSetterPlaceholder = "hwtHls.streamTmpAllocaTmpSetterPlaceholder";
// create a call of function which will acts a placeholder setter to prevent removal of the alloca
// while its driving logic was not constructed yet
llvm::CallInst* CreateStreamTmpAllocaTmpSetterPlaceholder(
		llvm::IRBuilderBase *Builder, llvm::AllocaInst *tmpAlloca) {
	Value *Ops[] = { tmpAlloca };
	Type *ResT = Builder->getVoidTy();
	Type *TysForName[] = { Ops[0]->getType() };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	auto name = Intrinsic_getName(StreamTmpAllocaTmpSetterPlaceholder,
			TysForName);
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(name, ResT, Ops[0]->getType()).getCallee());
	setArgNames(*TheFn, { "ioArgPtr", "chunkBitWidth", "isReliable" });
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->onlyAccessesInaccessibleMemOrArgMem();
	return CI;
}

bool IsStreamTmpAllocaTmpSetterPlaceholder(const llvm::CallInst *C) {
	return IsStreamTmpAllocaTmpSetterPlaceholder(C->getCalledFunction());
}
bool IsStreamTmpAllocaTmpSetterPlaceholder(const llvm::Function *F) {
	if (F->arg_size() != 1) // alloca
		return false;
	return F->getName().str().rfind(StreamTmpAllocaTmpSetterPlaceholder + ".", 0) == 0;
}

const std::string StreamReadName = "hwtHls.streamRead";
CallInst* CreateStreamRead(IRBuilderBase *Builder, Value *ioArgPtr,
		size_t chunkBitWidth, size_t returnBitWidth, bool isReliable) {
	assert(ioArgPtr->getType()->isPointerTy());
	if (chunkBitWidth > returnBitWidth) {
		throw std::runtime_error(
				"CreateStreamRead must have chunkBitWidth <= returnBitWidth");
	}

	Value *Ops[] = { ioArgPtr, Builder->getInt64(chunkBitWidth),
			Builder->getInt1(isReliable) };
	Type *ResT = Builder->getIntNTy(returnBitWidth);
	Type *TysForName[] = { Ops[0]->getType(), Ops[1]->getType(), Ops[2]->getType(), ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							Intrinsic_getName(StreamReadName, TysForName), ResT,
							Ops[0]->getType(), Ops[1]->getType(),
							Ops[2]->getType()).getCallee());
	setArgNames(*TheFn, { "ioArgPtr", "chunkBitWidth", "isReliable" });
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setOnlyAccessesArgMemory();
	return CI;
}

bool IsStreamRead(const llvm::CallInst *C) {
	return IsStreamRead(C->getCalledFunction());
}
bool IsStreamRead(const llvm::Function *F) {
	if (F->arg_size() != 3) // src, chunkBitWidth, isReliable
		return false;
	return F->getName().str().rfind(StreamReadName + ".", 0) == 0;
}
size_t streamReadGetOrigChunkBitWidth(const CallInst *I) {
	auto _chunkBitWidth = I->getArgOperand(1);
	auto chunkBitWidth = dyn_cast<ConstantInt>(_chunkBitWidth);
	assert(
			chunkBitWidth
					&& "Second arg of streamRead must always be const int");
	return chunkBitWidth->getZExtValue();
}
bool streamReadGetIsReliable(const llvm::CallInst *I) {
	auto _isReliable = I->getArgOperand(2);
	auto isReliable = dyn_cast<ConstantInt>(_isReliable);
	assert(isReliable && "arg[2] of streamRead must always be const int");
	return isReliable->getZExtValue();
}

const std::string StreamReadStartOfFrameName = "hwtHls.streamReadStartOfFrame";
template<const std::string &NAME>
CallInst* CreateStreamMarker(IRBuilderBase *Builder, Value *ioArgPtr) {
	assert(ioArgPtr->getType()->isPointerTy());
	Value *Ops[] = { ioArgPtr };
	Type *ResT = Builder->getVoidTy();
	Type *TysForName[] = { Ops[0]->getType() };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(Intrinsic_getName(NAME, TysForName), ResT,
					Ops[0]->getType()).getCallee());
	setArgNames(*TheFn, { "ioArgPtr" });
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setOnlyAccessesArgMemory();
	return CI;
}
CallInst* CreateStreamReadStartOfFrame(IRBuilderBase *Builder,
		Value *ioArgPtr) {
	return CreateStreamMarker<StreamReadStartOfFrameName>(Builder, ioArgPtr);
}

bool IsStreamReadStartOfFrame(const llvm::CallInst *C) {
	return IsStreamReadStartOfFrame(C->getCalledFunction());
}
bool IsStreamReadStartOfFrame(const llvm::Function *F) {
	return F->getName().str().rfind(StreamReadStartOfFrameName + ".", 0) == 0;
}

const std::string StreamReadEndOfFrameName = "hwtHls.streamReadEndOfFrame";
CallInst* CreateStreamReadEndOfFrame(IRBuilderBase *Builder, Value *ioArgPtr) {
	return CreateStreamMarker<StreamReadEndOfFrameName>(Builder, ioArgPtr);
}
bool IsStreamReadEndOfFrame(const llvm::CallInst *C) {
	return IsStreamReadEndOfFrame(C->getCalledFunction());
}
bool IsStreamReadEndOfFrame(const llvm::Function *F) {
	return F->getName().str().rfind(StreamReadEndOfFrameName + ".", 0) == 0;
}

const std::string StreamWriteName = "hwtHls.streamWrite";
const std::string StreamWriteMaskedName = StreamWriteName + ".masked";

// basic CreateStreamWrite without mask
CallInst* CreateStreamWriteNoMask(IRBuilderBase *Builder, Value *ioArgPtr,
		llvm::Value *valueToWrite, llvm::Value *isSoF, llvm::Value *isEoF) {
	if (!isSoF) {
		isSoF = Builder->getInt1(0);
	}
	if (!isEoF) {
		isEoF = Builder->getInt1(0);
	}
	assert(ioArgPtr->getType()->isPointerTy());
	Value *Ops[] = { ioArgPtr, valueToWrite, isSoF, isEoF };
	Type *ResT = Builder->getVoidTy();
	Type *TysForName[] = { Ops[0]->getType(), Ops[1]->getType(),
			Ops[2]->getType(), Ops[3]->getType() };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(StreamWriteName, TysForName), ResT,
					Ops[0]->getType(), Ops[1]->getType(), Ops[2]->getType(),
					Ops[3]->getType()).getCallee());
	setArgNames(*TheFn, { "ioArgPtr", "valueToWrite", "isSoF", "isEoF" });
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setOnlyAccessesArgMemory();
	return CI;
}
// CreateStreamWrite with mask
CallInst* CreateStreamWrite(IRBuilderBase *Builder, Value *ioArgPtr,
		llvm::Value *valueToWrite, llvm::Value *writeMaskOrEmpty,
		llvm::Value *isSoF, llvm::Value *isEoF) {
	if (!writeMaskOrEmpty) {
		return CreateStreamWriteNoMask(Builder, ioArgPtr, valueToWrite, isSoF,
				isEoF);
	}
	if (!isSoF) {
		isSoF = Builder->getInt1(0);
	}
	if (!isEoF) {
		isEoF = Builder->getInt1(0);
	}
	assert(ioArgPtr->getType()->isPointerTy());
	Value *Ops[] = { ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF };
	Type *ResT = Builder->getVoidTy();
	Type *TysForName[] = { Ops[0]->getType(), Ops[1]->getType(),
			Ops[2]->getType(), Ops[3]->getType(), Ops[4]->getType() };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(StreamWriteMaskedName, TysForName), ResT,
					Ops[0]->getType(), Ops[1]->getType(), Ops[2]->getType(),
					Ops[3]->getType(), Ops[4]->getType()).getCallee());
	setArgNames(*TheFn, { "ioArgPtr", "valueToWrite", "writeMaskOrEmpty",
			"isSoF", "isEoF" });
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setOnlyAccessesArgMemory();
	return CI;
}
size_t streamWriteGetOrigChunkBitWidth(const CallInst *I) {
	return I->getArgOperand(1)->getType()->getIntegerBitWidth();
}
llvm::Value* streamWriteGetIoArg(const llvm::CallInst *C) {
	return C->getArgOperand(0); // ioArgPtr, valueToWrite, [writeMaskOrEmpty], isSoF, isEoF
}
llvm::Value* streamWriteGetWriteData(const llvm::CallInst *C) {
	return C->getArgOperand(1); // ioArgPtr, valueToWrite, [writeMaskOrEmpty], isSoF, isEoF
}

llvm::Value* streamWriteGetWriteMaskOrEmpty(const llvm::CallInst *C) {
	if (IsStreamWriteMasked(C))
		return C->getArgOperand(2); // ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF
	return nullptr;
}
llvm::Value* streamWriteGetWriteSoF(const llvm::CallInst *C) {
	if (IsStreamWriteMasked(C))
		return C->getArgOperand(3); // ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF
	return C->getArgOperand(2); // ioArgPtr, valueToWrite, isSoF, isEoF;
}
llvm::Value* streamWriteGetWriteEoF(const llvm::CallInst *C) {
	if (IsStreamWriteMasked(C))
		return C->getArgOperand(4); // ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF
	return C->getArgOperand(3); // ioArgPtr, valueToWrite, isSoF, isEoF;
}

bool IsStreamWrite(const llvm::CallInst *C) {
	return IsStreamWrite(C->getCalledFunction());
}
bool IsStreamWrite(const llvm::Function *F) {
	assert(F && "Function may null if definition is missing in IR");
	if (F->arg_size() != 4 && F->arg_size() != 5) // ioArgPtr, valueToWrite, [writeMaskOrEmpty], isSoF, isEoF
		return false;
	return F->getName().str().rfind(StreamWriteName + ".", 0) == 0;
}
bool IsStreamWriteMasked(const llvm::CallInst *C) {
	return IsStreamWriteMasked(C->getCalledFunction());
}
bool IsStreamWriteMasked(const llvm::Function *F) {
	assert(F && "Function may null if definition is missing in IR");
	if (F->arg_size() != 5) // ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF
		return false;
	return F->getName().str().rfind(StreamWriteMaskedName + ".", 0) == 0;
}

const std::string StreamWriteStartOfFrameName = "hwtHls.streamWriteStartOfFrame";
CallInst* CreateStreamWriteStartOfFrame(IRBuilderBase *Builder,
		Value *ioArgPtr) {
	return CreateStreamMarker<StreamWriteStartOfFrameName>(Builder, ioArgPtr);
}

bool IsStreamWriteStartOfFrame(const llvm::CallInst *C) {
	return IsStreamWriteStartOfFrame(C->getCalledFunction());
}
bool IsStreamWriteStartOfFrame(const llvm::Function *F) {
	assert(F && "Function may null if definition is missing in IR");
	return F->getName().str().rfind(StreamWriteStartOfFrameName + ".", 0) == 0;
}

const std::string StreamWriteEndOfFrameName = "hwtHls.streamWriteEndOfFrame";
CallInst* CreateStreamWriteEndOfFrame(IRBuilderBase *Builder, Value *ioArgPtr) {
	return CreateStreamMarker<StreamWriteEndOfFrameName>(Builder, ioArgPtr);
}
bool IsStreamWriteEndOfFrame(const llvm::CallInst *C) {
	return IsStreamWriteEndOfFrame(C->getCalledFunction());
}
bool IsStreamWriteEndOfFrame(const llvm::Function *F) {
	assert(F && "Function may null if definition is missing in IR");
	return F->getName().str().rfind(StreamWriteEndOfFrameName + ".", 0) == 0;
}

bool IsStreamIo(const llvm::CallInst *C) {
	auto *F = C->getCalledFunction();
	assert(F && "Function may null if definition is missing in IR");
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
