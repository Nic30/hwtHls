#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoInstrCollector.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/bitMath.h>
#include <algorithm>

using namespace llvm;
namespace hwtHls {

StreamChannelProps::StreamChannelProps(
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas,
		llvm::Argument *ioArg) :
		GeneratedAllocas(GeneratedAllocas), ioArg(ioArg), nativeWordTy(nullptr), dataWidth(
				0), hasMask(false), isOutput(false) {
	dataVar = nullptr;
	dataMaskVar = nullptr;
	dataLastVar = nullptr;
	dataOffsetVar = nullptr;
	wDataPendingVar = nullptr;
}

StreamChannelWordValue StreamChannelWordValue::concat(
		llvm::IRBuilder<> &builder,
		llvm::ArrayRef<StreamChannelWordValue> lowerFirstMembers) {
	llvm::SmallVector<llvm::Value*> data;
	llvm::SmallVector<llvm::Value*> mask;
	llvm::SmallVector<llvm::Value*> last;

	bool allMasksNull = false;
	for (auto &d : lowerFirstMembers) {
		data.push_back(d.data);
		if (d.mask == nullptr) {
			assert(allMasksNull || mask.size() == 0);
			allMasksNull = true;
		} else {
			assert(!allMasksNull);
		}
		mask.push_back(d.mask);
		last.push_back(d.last);
	}
	Value *_data = CreateBitConcat(&builder, data);
	Value *_mask = nullptr;
	if (!allMasksNull) {
		_mask = CreateBitConcat(&builder, mask);
		assert(_mask);
	}

	return {
		_data,
		_mask,
		builder.CreateOr(last)
	};
}

StreamChannelWordValue StreamChannelWordValue::slice(llvm::IRBuilder<> &builder,
		size_t dataLowBitIndex, size_t bitsToTake) const {
	assert(bitsToTake > 0);
	llvm::Instruction *_data = dyn_cast<Instruction>(
			CreateBitRangeGetConst(&builder, data, dataLowBitIndex,
					bitsToTake));
	assert(_data);
	llvm::Instruction *_dataMask = nullptr;
	Value *_last = last;
	size_t DATA_WIDTH = data->getType()->getIntegerBitWidth();
	if (mask) {
		assert(dataLowBitIndex % 8 == 0);
		assert(bitsToTake % 8 == 0);
		_dataMask = dyn_cast<Instruction>(
				CreateBitRangeGetConst(&builder, mask, dataLowBitIndex / 8,
						bitsToTake / 8));
		assert(_dataMask);
		if (dataLowBitIndex + bitsToTake != DATA_WIDTH) {
			size_t nextMaskBitIndex = (dataLowBitIndex + bitsToTake) / 8;
			auto *nextMaskBit = CreateBitRangeGetConst(&builder, mask,
					nextMaskBitIndex, 1);
			_last = builder.CreateAnd(last, builder.CreateNot(nextMaskBit));
		}
	} else {
		if ((dataLowBitIndex + bitsToTake) != DATA_WIDTH) {
			// never last
			_last = ConstantInt::getFalse(builder.getContext());
		}
	}
	return {_data, _dataMask, _last};
}

llvm::Instruction* StreamChannelWordValue::flatten(
		llvm::IRBuilder<> &builder) const {
	if (mask) {
		return dyn_cast<llvm::Instruction>(CreateBitConcat(&builder, { data,
				mask, last }));
	} else {
		return dyn_cast<llvm::Instruction>(CreateBitConcat(&builder, { data,
				last }));
	}
}

void StreamChannelProps::setOffsetVar(llvm::IRBuilder<> &builder,
		size_t val) const {
	builder.CreateStore(
			ConstantInt::get(
					dyn_cast<IntegerType>(dataOffsetVar->getAllocatedType()),
					val), dataOffsetVar);
}

StreamChannelWordValue StreamChannelProps::parseNativeWord(
		llvm::IRBuilder<> &builder, llvm::Instruction *nativeWord) const {
	builder.SetInsertPoint(nativeWord->getParent(),
			BasicBlock::iterator(nativeWord->getNextNode()));
	Instruction *data = dyn_cast<Instruction>(
			CreateBitRangeGetConst(&builder, nativeWord, 0, dataWidth));
	assert(data);
	size_t off = dataWidth;
	Instruction *dataMask = nullptr;
	if (hasMask) {
		dataMask = dyn_cast<Instruction>(
				CreateBitRangeGetConst(&builder, nativeWord, off,
						dataWidth / 8));
		assert(dataMask);
		off += dataWidth / 8;
	}
	Value *dataLast = CreateBitRangeGetConst(&builder, nativeWord, off, 1);
	return {data, dataMask, dataLast};
}

llvm::Value* StreamChannelProps::deparseNativeWord(
		llvm::IRBuilder<> &builder) const {
	llvm::SmallVector<Value*, 3> parts;
	for (auto *v : { dataVar, dataMaskVar, dataLastVar }) {
		if (v != nullptr) { // dataMaskVar can be nullptr
			auto *_v = getVarValue(builder, v);
			parts.push_back(_v);
		}
	}
	return CreateBitConcat(&builder, parts);
}

void StreamChannelProps::setVarU64(llvm::IRBuilder<> &builder,
		std::optional<uint64_t> val, llvm::AllocaInst *var) {
	auto *Ty = dyn_cast<IntegerType>(var->getAllocatedType());
	Value *V;
	if (val.has_value()) {
		V = ConstantInt::get(Ty, val.value());
	} else {
		V = UndefValue::get(Ty);
	}
	builder.CreateStore(V, var, /*isVolatile*/false);
}

void StreamChannelProps::setDataMaskConst(llvm::IRBuilder<> &builder,
		size_t dataBitOffset, size_t dataBitsToTake) const {
	if (hasMask) {
		auto *T = dataMaskVar->getAllocatedType();
		auto val = APInt::getBitsSet(T->getIntegerBitWidth(), dataBitOffset / 8,
				(dataBitOffset + dataBitsToTake) / 8);
		auto *CI = ConstantInt::get(T, val);
		Value *V = CI;
		if (dataBitOffset != 0) {
			auto prev = builder.CreateLoad(T, dataMaskVar, /*isVolatile*/false);
			V = builder.CreateOr(prev, CI);
		}
		builder.CreateStore(V, dataMaskVar, /*isVolatile*/false);
	}
}

void StreamChannelProps::setData(llvm::IRBuilder<> &builder, llvm::Value *val,
		size_t offset) const {
	size_t w = val->getType()->getIntegerBitWidth();
	assert(w > 0);
	if (offset == 0 && w == dataWidth) {
		builder.CreateStore(val, dataVar, /*isVolatile*/false);
	} else {
		auto *cur = getVarValue(builder, dataVar);
		SmallVector<Value*, 3> parts;
		if (offset > 0) {
			parts.push_back(CreateBitRangeGetConst(&builder, cur, 0ul, offset));
		}
		parts.push_back(val);
		if (offset + w != dataWidth) {
			parts.push_back(
					CreateBitRangeGetConst(&builder, cur, offset + w,
							dataWidth - (offset + w)));
		}
		auto *newVal = CreateBitConcat(&builder, parts);
		builder.CreateStore(newVal, dataVar, /*isVolatile*/false);
	}
}

void StreamChannelProps::setAllData(llvm::IRBuilder<> &builder,
		llvm::Instruction *nativeWord) const {
	auto data = parseNativeWord(builder, nativeWord);
	setAllData(builder, data);
}
void StreamChannelProps::setAllData(llvm::IRBuilder<> &builder,
		StreamChannelWordValue data) const {
	assert(
			data.data->getType()->getIntegerBitWidth()
					== dataVar->getAllocatedType()->getIntegerBitWidth());
	builder.CreateStore(data.data, dataVar, /*isVolatile*/false);
	if (hasMask) {
		assert(
				data.mask->getType()->getIntegerBitWidth()
						== dataMaskVar->getAllocatedType()->getIntegerBitWidth());
		builder.CreateStore(data.mask, dataMaskVar, /*isVolatile*/false);
	}

	assert(
			data.last->getType()->getIntegerBitWidth()
					== dataLastVar->getAllocatedType()->getIntegerBitWidth());
	builder.CreateStore(data.last, dataLastVar, /*isVolatile*/false);
}

llvm::LoadInst* StreamChannelProps::getVarValue(llvm::IRBuilder<> &builder,
		llvm::AllocaInst *var) const {
	const char * Name = nullptr;;
	if (var == dataVar) {
		Name = ".data";
	} else if (var == dataMaskVar) {
		Name = ".dataMask";
	} else if (var == dataLastVar) {
		Name = ".last";
	} else if (var == dataOffsetVar) {
		Name = ".offset";
	} else if (var == wDataPendingVar) {
		Name = ".wDataPending";
	}
	return builder.CreateLoad(var->getAllocatedType(), var, /*isVolatile*/false,
			Name ?  ioArg->getName() + Name : "");
}

StreamChannelWordValue StreamChannelProps::getAllData(
		llvm::IRBuilder<> &builder) const {
	return {getVarValue(builder, dataVar),
		hasMask ? getVarValue(builder, dataMaskVar) : nullptr,
		getVarValue(builder, dataLastVar)};
}

size_t StreamChannelProps::_getBusWordCntForChunk(size_t offset,
		size_t width) const {
	return div_ceil(width + offset, dataWidth);
}

std::pair<size_t, size_t> StreamChannelProps::_resolveMinMaxWordCount(
		std::vector<size_t> possibleOffsets, size_t chunkWidth) const {
	std::optional<size_t> minWordCnt;
	std::optional<size_t> maxWordCnt;
	// add read for every word which will be used in this read of frame fragment
	for (auto off : possibleOffsets) {
		size_t wCnt = _getBusWordCntForChunk(off, chunkWidth);

		if (minWordCnt.has_value()) {
			minWordCnt = std::min(wCnt, minWordCnt.value());
		} else {
			minWordCnt = wCnt;
		}
		if (maxWordCnt.has_value()) {
			maxWordCnt = std::max(wCnt, maxWordCnt.value());
		} else {
			maxWordCnt = wCnt;
		}
	}
	return {minWordCnt.value(), maxWordCnt.value()};
}
void StreamChannelProps::createCommonVars(llvm::IRBuilder<> &builder) {
	auto &C = builder.getContext();

	assert(dataVar == nullptr);
	IntegerType *dataT = IntegerType::getIntNTy(C, dataWidth);
	dataVar = builder.CreateAlloca(dataT, nullptr, ioArg->getName() + "Data");
	GeneratedAllocas.push_back(dataVar);

	if (hasMask) {
		assert(dataWidth % 8 == 0);
		assert(dataMaskVar == nullptr);
		IntegerType *maskT = IntegerType::getIntNTy(C, dataWidth / 8);
		dataMaskVar = builder.CreateAlloca(maskT, nullptr,
				ioArg->getName() + "DataMask");
		GeneratedAllocas.push_back(dataMaskVar);
	}
	assert(dataLastVar == nullptr);
	dataLastVar = builder.CreateAlloca(IntegerType::getInt1Ty(C), nullptr,
			ioArg->getName() + "DataLast");
	GeneratedAllocas.push_back(dataLastVar);

	assert(dataOffsetVar == nullptr);
	IntegerType *offT = IntegerType::getIntNTy(C, log2ceil(dataWidth));
	dataOffsetVar = builder.CreateAlloca(offT, nullptr,
			ioArg->getName() + "DataOffset");
	GeneratedAllocas.push_back(dataOffsetVar);
}

void StreamChannelProps::createWDataPendingVar(llvm::IRBuilder<> &builder) {
	auto &C = builder.getContext();

	assert(wDataPendingVar == nullptr);
	wDataPendingVar = builder.CreateAlloca(IntegerType::getInt1Ty(C), nullptr,
			ioArg->getName() + "DataPending");
	GeneratedAllocas.push_back(wDataPendingVar);

}

size_t MDTuple_getOperandAsU64(const MDTuple *metaTuple, size_t opI) {
	auto CM = dyn_cast<ConstantAsMetadata>(metaTuple->getOperand(opI));
	assert(CM);
	auto C = dyn_cast<ConstantInt>(CM->getValue());
	assert(C);
	return C->getZExtValue();
}

std::vector<StreamChannelProps> getStreamIoProps(llvm::Function &F,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas,
		llvm::Argument *ioFilter) {
	std::vector<StreamChannelProps> streamProps;
	for (auto &BB : F) {
		for (auto &I : BB) {
			if (auto *CI = dyn_cast<llvm::CallInst>(&I)) {

				bool isWrite = IsStreamWrite(CI)
						|| IsStreamWriteStartOfFrame(CI)
						|| IsStreamWriteEndOfFrame(CI);
				if (isWrite || IsStreamRead(CI) || IsStreamReadStartOfFrame(CI)
						|| IsStreamReadEndOfFrame(CI)) {
					auto src = CI->getArgOperand(0);
					if (ioFilter && src != ioFilter)
						continue;
					auto cur = std::find_if(streamProps.begin(),
							streamProps.end(),
							[src](const StreamChannelProps &p) {
								return p.ioArg == src;
							});
					if (cur == streamProps.end()) {
						// if there was not record for this argument yet, construct it from function metadata
						auto *md = F.getMetadata("hwtHls.streamIo");
						auto srcArg = dyn_cast<Argument>(src);
						assert(srcArg);
						size_t argI = srcArg->getArgNo();
						bool metaForThisIoFound = false;
						for (auto &_metaTuple : md->operands()) {
							auto metaTuple = dyn_cast<MDTuple>(
									_metaTuple.get());
							assert(metaTuple);
							if (argI == MDTuple_getOperandAsU64(metaTuple, 0)) {
								StreamChannelProps props(GeneratedAllocas,
										srcArg);
								props.dataWidth = MDTuple_getOperandAsU64(
										metaTuple, 1);
								props.isOutput = isWrite;
								props.hasMask = MDTuple_getOperandAsU64(
										metaTuple, 2);
								props.nativeWordTy = IntegerType::getIntNTy(
										F.getContext(),
										props.dataWidth
												+ (props.hasMask ?
														props.dataWidth / 8 : 0)
												+ 1);
								props.ios.insert(CI);
								streamProps.push_back(props);
								metaForThisIoFound = true;
								break;
							}
						}
						assert(metaForThisIoFound);
					} else {
						assert(cur->isOutput == isWrite);
						cur->ios.insert(CI);
					}
				}
			}
		}
	}
	if (ioFilter)
		assert(
				streamProps.size() == 1
						&& "Can not find any stream IO instruction for specified stream. If ioFilter was set properties should be found only for this single IO");
	return streamProps;
}

}
