#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

#include <llvm/IR/Constants.h>
#include <llvm/ADT/StringExtras.h>
#include <llvm/IR/Module.h>

#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
using namespace llvm;

namespace hwtHls {

inline static void setArgNames(Function &F, ArrayRef<const char*> argNames) {
	size_t argI = 0;
	for (auto name : argNames) {
		assert(argI < F.arg_size());
		F.getArg(argI)->setName(name);
		argI++;
	}
}
const std::string StreamReadName = "hwtHls.streamRead";
const std::string StreamReadUnreliableName = StreamReadName + ".unreliable";
const std::string StreamReadAligningName = StreamReadName + "aligning";
const std::string StreamReadStartOfFrameName = "hwtHls.streamReadStartOfFrame";
const std::string StreamReadEndOfFrameName = "hwtHls.streamReadEndOfFrame";
const std::string StreamTmpAllocaTmpSetterPlaceholder =
		"hwtHls.streamTmpAllocaTmpSetterPlaceholder";
const std::string StreamWriteName = "hwtHls.streamWrite";
const std::string StreamWriteMaskedName = StreamWriteName + ".masked";
const std::string StreamWritePackingName = StreamWriteName + ".packing";
const std::string StreamWriteStartOfFrameName = "hwtHls.streamWriteStartOfFrame";
const std::string StreamWriteEndOfFrameName = "hwtHls.streamWriteEndOfFrame";
const std::string StreamRealignName = "hwtHls.streamRealign";

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
	setArgNames(*TheFn, { "ioArgPtr" });
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
	return F->getName().str().rfind(StreamTmpAllocaTmpSetterPlaceholder + ".",
			0) == 0;
}
CallInst* CreateStreamRead(IRBuilderBase *Builder, Value *ioArgPtr,
		size_t chunkBitWidth, size_t returnBitWidth, bool isReliable,
		std::optional<size_t> endAlignas) {
	assert(ioArgPtr->getType()->isPointerTy());
	if (chunkBitWidth > returnBitWidth) {
		// :note: returnBitWidth is chunkBitWidth + width of control bits like empty/mask/eof ... it can be computed by StreamChannelFormatInfo::getReadReturnWidth
		throw std::runtime_error(
				"CreateStreamRead must have chunkBitWidth <= returnBitWidth");
	}
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	CallInst *CI;
	if (endAlignas.has_value()) {
		if (isReliable) {
			throw std::runtime_error(
					"CreateStreamRead endAlignas option specifies where read should end premature thus isReliable must equal False");
		}
		Value *Ops[] = { ioArgPtr,                //
				Builder->getInt64(chunkBitWidth), //
				Builder->getInt64(endAlignas.value()), };
		Type *ResT = Builder->getIntNTy(returnBitWidth);
		Type *TysForName[] = { Ops[0]->getType(), //
				Ops[1]->getType(), //
				Ops[2]->getType(), //
				ResT };
		auto name = Intrinsic_getName(StreamReadAligningName, TysForName);
		Function *TheFn = cast<Function>(M->getOrInsertFunction(name, ResT,   //
				Ops[0]->getType(), //
				Ops[1]->getType(), //
				Ops[2]->getType()  //
				).getCallee());
		setArgNames(*TheFn, { "ioArgPtr", "chunkBitWidth", "endAlignas" });
		AddDefaultFunctionAttributes(*TheFn);
		CI = Builder->CreateCall(TheFn, Ops);
	} else {
		Value *Ops[] = { ioArgPtr,                //
				Builder->getInt64(chunkBitWidth) //
				};
		Type *ResT = Builder->getIntNTy(returnBitWidth);
		Type *TysForName[] = { Ops[0]->getType(), //
				Ops[1]->getType(), //
				ResT };
		auto name = Intrinsic_getName(
				isReliable ? StreamReadName : StreamReadUnreliableName,
				TysForName);
		Function *TheFn = cast<Function>(M->getOrInsertFunction(name, ResT,   //
				Ops[0]->getType(), //
				Ops[1]->getType() //
				).getCallee());
		setArgNames(*TheFn, { "ioArgPtr", "chunkBitWidth" });
		AddDefaultFunctionAttributes(*TheFn);
		CI = Builder->CreateCall(TheFn, Ops);
	}
	CI->setOnlyAccessesArgMemory();
	return CI;
}
bool IsStreamRead(const llvm::CallInst *C) {
	return IsStreamRead(C->getCalledFunction());
}
bool IsStreamRead(const llvm::Function *F) {
	if (F->arg_size() != 2 && F->arg_size() != 3) // src, chunkBitWidth, [endAlignas]
		return false;
	return F->getName().str().rfind(StreamReadName + ".", 0) == 0;
}

llvm::Value* streamReadGetIoArg(const llvm::CallInst *C) {
	return C->getArgOperand(0);
}
size_t streamReadGetOrigChunkBitWidth(const CallInst *I) {
	auto _chunkBitWidth = I->getArgOperand(1);
	auto chunkBitWidth = dyn_cast<ConstantInt>(_chunkBitWidth);
	assert(
			chunkBitWidth
					&& "Second arg of streamRead must always be const int");
	return chunkBitWidth->getZExtValue();
}

StreamReadBehaviorType streamReadGetBehavior(const llvm::CallInst *I) {
	auto F = I->getCalledFunction();
	auto name = F->getName().str();
	if (name.rfind(StreamReadUnreliableName, 0) == 0) {
		return StreamReadBehaviorType::UNRELIABLE;
	} else if (name.rfind(StreamReadAligningName, 0) == 0) {
		return StreamReadBehaviorType::ALIGNING;
	} else {
		assert(name.rfind(StreamReadName, 0) == 0);
		return StreamReadBehaviorType::RELIABLE;
	}
}

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

CallInst* CreateStreamReadEndOfFrame(IRBuilderBase *Builder, Value *ioArgPtr) {
	return CreateStreamMarker<StreamReadEndOfFrameName>(Builder, ioArgPtr);
}
bool IsStreamReadEndOfFrame(const llvm::CallInst *C) {
	return IsStreamReadEndOfFrame(C->getCalledFunction());
}
bool IsStreamReadEndOfFrame(const llvm::Function *F) {
	return F->getName().str().rfind(StreamReadEndOfFrameName + ".", 0) == 0;
}

// CreateStreamWrite with optional mask, error argument
CallInst* CreateStreamWrite(IRBuilderBase *Builder, Value *ioArgPtr,
		llvm::Value *valueToWrite, llvm::Value *writeMaskOrEmpty,
		llvm::Value *isSoF, llvm::Value *isEoF, llvm::Value *errorVal,
		bool isPacking) {
	assert(ioArgPtr->getType()->isPointerTy());
	if (!isSoF) {
		isSoF = Builder->getInt1(0);
	}
	if (!isEoF) {
		isEoF = Builder->getInt1(0);
	}
	if (!errorVal)
		errorVal = ConstantPointerNull::get(Builder->getPtrTy(0));

#define __CreateStreamWrite_OPSTYPES4 \
	            Ops[0]->getType(),\
	            Ops[1]->getType(),\
	            Ops[2]->getType(),\
	            Ops[3]->getType(),\
	            Ops[4]->getType() \

	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	CallInst *CI;
	// switch between variants of StreamWrite based on presence of writeMaskOrEmpty/errorVal
	if (writeMaskOrEmpty) {
		Value *Ops[] = { ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF,
				errorVal };
		Type *ResT = Builder->getVoidTy();
		Type *TysForName[] = { __CreateStreamWrite_OPSTYPES4, //
		Ops[5]->getType()};
		auto fnName = Intrinsic_getName(
				isPacking ? StreamWritePackingName : StreamWriteMaskedName,
				TysForName);
		Function *TheFn = cast<Function>(M->getOrInsertFunction(fnName, ResT, //
				__CreateStreamWrite_OPSTYPES4, //
		Ops[5]->getType()//
		).getCallee());
		setArgNames(*TheFn, { "ioArgPtr", "valueToWrite", "writeMaskOrEmpty",
				"isSoF", "isEoF", "errorVal" });
		AddDefaultFunctionAttributes(*TheFn);
		CI = Builder->CreateCall(TheFn, Ops);
	} else {
		if (isPacking) {
			throw std::runtime_error(
					"CreateStreamWrite: if isPacking==True, writeMaskOrEmpty must be provided");
		}
		Value *Ops[] = { ioArgPtr, valueToWrite, isSoF, isEoF, errorVal };
		Type *ResT = Builder->getVoidTy();
		Type *TysForName[] = { __CreateStreamWrite_OPSTYPES4};
		auto fnName = Intrinsic_getName(StreamWriteName, TysForName);
		Function *TheFn = cast<Function>(M->getOrInsertFunction(fnName, ResT, //
				__CreateStreamWrite_OPSTYPES4).getCallee());
		setArgNames(*TheFn, { "ioArgPtr", "valueToWrite", "isSoF", "isEoF",
				"errorVal" });
		AddDefaultFunctionAttributes(*TheFn);
		CI = Builder->CreateCall(TheFn, Ops);

	}
#undef __CreateStreamWrite_OPSTYPES4
	CI->setOnlyAccessesArgMemory();
	return CI;
}

StreamWriteBehaviorType streamWriteGetBehavior(const llvm::CallInst *C) {
	switch (C->arg_size()) {
	case 5:
		// ioArgPtr, valueToWrite, isSoF, isEoF, errorVal
		return StreamWriteBehaviorType::ALLVALID;
	case 6: {
		auto F = C->getCalledFunction();
		auto name = F->getName().str();
		if (name.rfind(StreamWriteMaskedName + ".", 0) == 0) {
			return StreamWriteBehaviorType::MASKED;
		} else if (name.rfind(StreamWritePackingName + ".", 0) == 0) {
			return StreamWriteBehaviorType::PACKING;
		} else {
			llvm_unreachable(
					"streamWriteGetBehavior unrecognized StreamWriteBehaviorType");
		}
	}
	default:
		llvm_unreachable(
				"streamWriteGetBehavior wrong number of call arguments");
	}

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
	// ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF, errorVal
	if (C->arg_size() == 6)
		return C->getArgOperand(2); // ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF
	else {
		assert(C->arg_size() == 5);
		// ioArgPtr, valueToWrite, isSoF, isEoF, errorVal
		return nullptr;
	}
}
llvm::Value* streamWriteGetWriteSoF(const llvm::CallInst *C) {
	// ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF, errorVal
	// ioArgPtr, valueToWrite, isSoF, isEoF, errorVal
	return C->getArgOperand(C->arg_size() - 2 - 1);
}
llvm::Value* streamWriteGetWriteEoF(const llvm::CallInst *C) {
	// ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF, errorVal
	// ioArgPtr, valueToWrite, isSoF, isEoF, errorVal
	return C->getArgOperand(C->arg_size() - 1 - 1);
}
llvm::Value* streamWriteGetWriteError(const llvm::CallInst *C) {
	// ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF, errorVal
	// ioArgPtr, valueToWrite, isSoF, isEoF, errorVal
	auto err = C->getArgOperand(C->arg_size() - 1);
	if (err->getType()->isPointerTy()) {
		assert(isa<ConstantPointerNull>(err));
		return nullptr;
	} else {
		return err;
	}
}
bool IsStreamWrite(const llvm::CallInst *C) {
	return IsStreamWrite(C->getCalledFunction());
}
bool IsStreamWrite(const llvm::Function *F) {
	assert(F && "Function may null if definition is missing in IR");
	if (F->arg_size() != 5 && F->arg_size() != 6) // ioArgPtr, valueToWrite, [writeMaskOrEmpty], isSoF, isEoF, errorVal
		return false;
	return F->getName().str().rfind(StreamWriteName + ".", 0) == 0;
}

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

// :param inAlignAs: specifies where the stream should be cut to perform realigning. 0 means current location
//                   other values means the bit position in the bus word
// :param outAlighnAs: specifies the number of bits in the first word of an output steam
//                     which are unused, if unset the value is picked automatically as the lowest value of offset from input
llvm::CallInst *CreateStreamRealign(llvm::IRBuilderBase *Builder,
									llvm::Value *ioArgPtr,
									std::optional<size_t> inAlignAs,
									std::optional<size_t> outAlignAs) {
	assert(ioArgPtr->getType()->isPointerTy());
	if (!inAlignAs.has_value())
		inAlignAs = -1;
	if (!outAlignAs.has_value())
		outAlignAs = -1;

	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	CallInst *CI;
	Value *Ops[] = {
		ioArgPtr,							  //
		Builder->getInt64(inAlignAs.value()), //
		Builder->getInt64(outAlignAs.value()),
	};
	Type *ResT = Builder->getVoidTy();
	Type *TysForName[] = {Ops[0]->getType(), //
						  Ops[1]->getType(), //
						  Ops[2]->getType(), //
						  ResT};
	auto name = Intrinsic_getName(StreamReadAligningName, TysForName);
	Function *TheFn =
		cast<Function>(M->getOrInsertFunction(name, ResT,		 //
											  Ops[0]->getType(), //
											  Ops[1]->getType(), //
											  Ops[2]->getType()	 //
											  )
						   .getCallee());
	setArgNames(*TheFn, {"ioArgPtr", "inAlignAs", "outAlighnAs"});
	AddDefaultFunctionAttributes(*TheFn);
	CI = Builder->CreateCall(TheFn, Ops);

	CI->setOnlyAccessesArgMemory();
	return CI;
}
bool IsStreamRealign(const llvm::CallInst *C) {
	auto *F = C->getCalledFunction();
	assert(F && "Function may null if definition is missing in IR");
	return IsStreamRealign(C->getCalledFunction());
}
bool IsStreamRealign(const llvm::Function *F) {
	return F->getName().str().rfind(StreamRealignName) == 0;
}
StreamRealignOptions StreamRealignGetOptions(const llvm::CallInst *C) {
	StreamRealignOptions res;
	res.ioArgPtr = C->getArgOperand(0);
	
	auto _inAlignAs = dyn_cast<ConstantInt>(C->getArgOperand(1));
	assert(_inAlignAs && "inAlignAs argument is expected to be a integer constant");
	auto _outAlignAs = dyn_cast<ConstantInt>(C->getArgOperand(2));
	assert(_outAlignAs && "outAlignAs argument is expected to be a integer constant");
	auto inAlignAs = _inAlignAs->getSExtValue();
	if (inAlignAs < 0) {
		res.inAlignAs = {};
	} else {
		res.inAlignAs = inAlignAs;
	}

	auto outAlignAs = _outAlignAs->getSExtValue();
	if (outAlignAs < 0) {
		res.outAlignAs = {};
	} else {
		res.outAlignAs = outAlignAs;
	}

	return res;
}

}
