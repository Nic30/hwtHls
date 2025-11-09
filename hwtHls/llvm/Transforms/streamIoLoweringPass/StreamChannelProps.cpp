#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

#include <algorithm>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>

using namespace llvm;

namespace hwtHls {

const std::string StreamChannelProps::METADATA_NAME_TMP_VAR_DATA_OFFSET =
		"hwtHls.io.protocol.stream.tmpVar.dataOffset";

StreamChannelProps::StreamChannelProps(const StreamChannelFormatInfo &scfi,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas) :
		StreamChannelFormatInfo(scfi), GeneratedAllocas(GeneratedAllocas) {
	dataVar = nullptr;
	dataMaskVar = nullptr;
	dataEnableVar = nullptr;
	dataEmptyVar = nullptr;
	dataSoFVar = nullptr;
	dataEoFVar = nullptr;
	dataErrorVar = nullptr;
	dataOffsetVar = nullptr;
	wDataPendingVar = nullptr;
}

void StreamChannelProps::setOffsetVar(llvm::IRBuilderBase &builder,
		size_t val) const {
	builder.CreateStore(
			ConstantInt::get(
					dyn_cast<IntegerType>(dataOffsetVar->getAllocatedType()),
					val), dataOffsetVar);
}

llvm::Value* StreamChannelProps::deparseNativeWord(
		llvm::IRBuilderBase &builder) const {
	llvm::SmallVector<AllocaInst*, 6> partVars;
	switch (byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
	case ByteEnableEncoding::BEE_MASK: {
		// Axi4Stream (data, strb?, err?, sof?, eof?)
		partVars =
				{ dataVar, dataMaskVar, dataErrorVar, dataSoFVar, dataEoFVar };
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		// Axi4StreamSegmented (data[n], (enable?, sof?, eof?, err?, empty)[n])
		partVars = { dataVar, dataEnableVar, dataSoFVar, dataEoFVar,
				dataErrorVar, dataEmptyVar };
		break;
	}
	default:
		break;
	}
	llvm::SmallVector<Value*, 6> parts;
	for (auto *v : partVars) {
		if (v != nullptr) { // dataMaskVar can be nullptr
			Value *_v = getVarValue(builder, v);
			if (v == dataEmptyVar) {
				auto emptyT = IntegerType::get(builder.getContext(),  getWidthOfEmpty());
				_v = builder.CreateTrunc(_v, emptyT);
			}
			parts.push_back(_v);
		}
	}
	return CreateBitConcat(&builder, parts);
}

void StreamChannelProps::setVarU64(llvm::IRBuilderBase &builder,
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

void StreamChannelProps::setDataMaskOrEmptyConst(llvm::IRBuilderBase &builder,
		size_t dataBitOffset, size_t dataBitsToTake) const {
	switch (byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
		break;
	case ByteEnableEncoding::BEE_MASK: {
		if (dataMaskVar) {
			auto *T = dataMaskVar->getAllocatedType();
			auto val = APInt::getBitsSet(T->getIntegerBitWidth(),
					dataBitOffset / byteWidth,
					(dataBitOffset + dataBitsToTake) / byteWidth);
			auto *CI = ConstantInt::get(T, val);
			_setDataMask(builder, dataBitOffset != 0, CI);
		}
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		if (dataEmptyVar) {
			auto newEmptyVal = (dataWidth - (dataBitOffset + dataBitsToTake))
					/ byteWidth;
			auto *emptyTy = dataEmptyVar->getAllocatedType();
			assert(
					newEmptyVal <= (1ul << emptyTy->getIntegerBitWidth()) - 1ul
							&& "newEmptyVal fits in number of bits for dataEmptyVar");
			builder.CreateStore(ConstantInt::get(emptyTy, newEmptyVal),
					dataEmptyVar, /*isVolatile*/false);
		}
		if (dataEnableVar) {
			bool isInitialSet = dataBitOffset == 0 && dataBitsToTake == 0;
			setVarU64(builder, !isInitialSet, dataEnableVar);
		}
		break;
	}
	default:
		llvm_unreachable("Invalid value for ByteEnableEncoding");
	}
}

Value* zeroPad(llvm::IRBuilderBase &builder, size_t bitsOnMsbSide, Value *V,
		size_t bitsOnLsbSide) {
	SmallVector<Value*, 3> concatMembers;
	if (bitsOnLsbSide)
		concatMembers.push_back(builder.getIntN(bitsOnLsbSide, 0));
	concatMembers.push_back(V);
	if (bitsOnMsbSide)
		concatMembers.push_back(builder.getIntN(bitsOnMsbSide, 0));
	return CreateBitConcat(&builder, concatMembers);
}

void StreamChannelProps::setDataMaskOrEmpty(llvm::IRBuilderBase &builder,
		size_t widthOfWrite, size_t srcDataBitOffset, size_t dstDataBitOffset,
		size_t dataBitsToTake, llvm::Value *maskOrEmptyForWholeChunk) const {
	if (maskOrEmptyForWholeChunk == nullptr) {
		setDataMaskOrEmptyConst(builder, dstDataBitOffset, dataBitsToTake);
	} else {
		switch (byteEnableEncoding) {
		case ByteEnableEncoding::BEE_NONE:
			break;
		case ByteEnableEncoding::BEE_MASK: {
			if (dataMaskVar) {
				Value *newMask = CreateBitRangeGetConst(&builder,
						maskOrEmptyForWholeChunk, srcDataBitOffset / byteWidth,
						dataBitsToTake / byteWidth);
				size_t lsbPadWidth = dstDataBitOffset / byteWidth;
				size_t msbPadWidth =
						(dataVar->getAllocatedType()->getIntegerBitWidth()
								/ byteWidth
								- newMask->getType()->getIntegerBitWidth()
								- lsbPadWidth);
				newMask = zeroPad(builder, msbPadWidth, newMask, lsbPadWidth);
				_setDataMask(builder, lsbPadWidth != 0 || msbPadWidth != 0,
						newMask);
			}
			break;
		}
		case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
			if (dataEnableVar)
				builder.CreateStore(builder.getTrue(), dataEnableVar, /*isVolatile*/
				false);
			if (dataEmptyVar) {
				Value *empty =
						StreamChannelWordValue::computeEmptyForDataInsert(
								builder, byteWidth,
								*dataEmptyVar->getAllocatedType(),
								*maskOrEmptyForWholeChunk, widthOfWrite,
								srcDataBitOffset, dataBitsToTake,
								dstDataBitOffset, dataWidth);
				builder.CreateStore(empty, dataEmptyVar, /*isVolatile*/false);
			}
			break;
		}
		default:
			llvm_unreachable("Invalid value for ByteEnableEncoding");
		}
	}
}

void StreamChannelProps::_setDataMask(llvm::IRBuilderBase &builder,
		bool orWithCurrent, Value *newMaskValue) const {
	assert(hasMask());
	Value *V = newMaskValue;
	if (orWithCurrent) {
		auto prev = builder.CreateLoad(dataMaskVar->getAllocatedType(),
				dataMaskVar, /*isVolatile*/false);
		V = builder.CreateOr(prev, newMaskValue);
	}
	builder.CreateStore(V, dataMaskVar, /*isVolatile*/false);
}
void StreamChannelProps::setData(llvm::IRBuilderBase &builder, llvm::Value *val,
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

void StreamChannelProps::setAllData(llvm::IRBuilderBase &builder,
		llvm::Instruction *nativeWord) const {
	builder.SetInsertPoint(nativeWord->getParent(),
			nativeWord->getNextNode()->getIterator());
	auto data = StreamChannelWordValue::parseNativeWord(*this, builder,
			nativeWord);
	setAllData(builder, data);
}

void _setAllData_setVarConditionally(IRBuilderBase &Builder, bool mustSet,
		Value *inValue, AllocaInst *tmpVar) {
	if (mustSet) {
		assert(inValue);
		assert(tmpVar);
		assert(
				inValue->getType()->getIntegerBitWidth()
						== tmpVar->getAllocatedType()->getIntegerBitWidth());
		Builder.CreateStore(inValue, tmpVar, /*isVolatile*/false);
	} else {
		assert(!inValue);
		assert(!tmpVar);
	}
}
void StreamChannelProps::setAllData(llvm::IRBuilderBase &builder,
		StreamChannelWordValue data) const {
	assert(
			data.data->getType()->getIntegerBitWidth()
					== dataVar->getAllocatedType()->getIntegerBitWidth());
	builder.CreateStore(data.data, dataVar, /*isVolatile*/false);
	switch (byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE: {
		assert(!data.mask);
		assert(!data.enable);
		assert(!data.empty);
		break;
	}
	case ByteEnableEncoding::BEE_MASK: {
		assert(!data.enable);
		assert(!data.empty);
		_setAllData_setVarConditionally(builder, hasMask(), data.mask,
				dataMaskVar);
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		assert(!data.mask);
		if (hasEnable())
			_setAllData_setVarConditionally(builder, true, data.enable,
					dataEnableVar);
		if (hasEmpty())
			_setAllData_setVarConditionally(builder, hasEmpty(),
					builder.CreateZExt(data.empty,
							dataEmptyVar->getAllocatedType()), dataEmptyVar);
		break;
	}
	default:
		llvm_unreachable("NotImplemented");
	}
	_setAllData_setVarConditionally(builder, hasSoF(), data.sof, dataSoFVar);
	_setAllData_setVarConditionally(builder, hasEoF(), data.eof, dataEoFVar);
	_setAllData_setVarConditionally(builder, hasError(), data.error,
			dataErrorVar);
}

llvm::LoadInst* StreamChannelProps::getVarValue(llvm::IRBuilderBase &builder,
		llvm::AllocaInst *var) const {
	const char *Name = nullptr;
	if (var == dataVar) {
		Name = ".data";
	} else if (var == dataMaskVar) {
		Name = ".mask";
	} else if (var == dataEmptyVar) {
		Name = ".empty";
	} else if (var == dataSoFVar) {
		Name = ".sof";
	} else if (var == dataEoFVar) {
		Name = ".eof";
	} else if (var == dataOffsetVar) {
		Name = ".offset";
	} else if (var == dataErrorVar) {
		Name = ".error";
	} else if (var == wDataPendingVar) {
		Name = ".wDataPending";
	}
	Twine _Name = Name ? ioArg->getName() + Name : "";
	return builder.CreateLoad(var->getAllocatedType(), var, /*isVolatile*/false,
			_Name);
}

StreamChannelWordValue StreamChannelProps::getAllData(
		llvm::IRBuilderBase &builder) const {

	auto _data = getVarValue(builder, dataVar);
	Value *_mask = nullptr;
	if (hasMask())
		_mask = getVarValue(builder, dataMaskVar);

	Value *_sof = nullptr;
	if (hasSoF())
		_sof = getVarValue(builder, dataSoFVar);

	auto _eof = getVarValue(builder, dataEoFVar);
	Value *_error = nullptr;
	if (errorWidth)
		_error = getVarValue(builder, dataErrorVar);

	Value *_enable = nullptr;
	if (hasEnable())
		_enable = builder.getTrue();

	Value *_empty = nullptr;
	if (hasEmpty()) {
		_empty = getVarValue(builder, dataEmptyVar);
		if (!supportZLP) {
			_empty = builder.CreateTrunc(_empty,
					builder.getIntNTy(getWidthOfEmpty()));
		}
	}
	return {*this, _data, _mask, _enable, _empty, _sof, _eof, _error};
}

llvm::AllocaInst* StreamChannelProps::_getOrCreateTmpVar(
		llvm::IRBuilderBase &Builder, llvm::Type *Ty, const Twine &Name,
		const std::string &mdName, bool findOnly) {
	auto &BB = ioArg->getParent()->getEntryBlock();
	for (auto &I : BB) {
		if (auto AI = dyn_cast<AllocaInst>(&I)) {
			auto md = AI->getMetadata(mdName);
			if (md) {
				auto mdTuple = dyn_cast<MDTuple>(md);
				if (mdTuple && mdTuple->getNumOperands() == 1) {
					ConstantInt *ArgIndexMD = mdconst::extract_or_null<
							ConstantInt>(md->getOperand(0));
					assert(ArgIndexMD);
					if (ioArg->getArgNo() == ArgIndexMD->getZExtValue())
						return AI;
				}
			}
		}
	}
	if (findOnly)
		return nullptr;

	assert(
			Builder.GetInsertBlock() == &BB
					&& "Tmp allocas should be created only in entry block");
	auto res = Builder.CreateAlloca(Ty, nullptr, Name);
	auto &C = Builder.getContext();
	auto md = ValueAsMetadata::getConstant(
			ConstantInt::getSigned(IntegerType::getInt32Ty(C),
					ioArg->getArgNo()));
	res->setMetadata(mdName, MDTuple::get(C, { md, }));
	return res;
}

llvm::AllocaInst* StreamChannelProps::_getOrCreateTmpVarDataOffset(
		llvm::IRBuilderBase *Builder, bool findOnly) {
	if (dataOffsetVar)
		return dataOffsetVar;
	IntegerType *offT = IntegerType::getIntNTy(ioArg->getContext(),
			log2ceil(dataWidth));
	dataOffsetVar = _getOrCreateTmpVar(*Builder, offT,
			ioArg->getName() + "DataOffset", METADATA_NAME_TMP_VAR_DATA_OFFSET,
			findOnly);
	return dataOffsetVar;
}

void StreamChannelProps::createCommonVars(llvm::IRBuilderBase &builder) {
	auto &C = builder.getContext();
	assert(dataVar == nullptr);
	IntegerType *dataT = IntegerType::getIntNTy(C, dataWidth);
	dataVar = builder.CreateAlloca(dataT, nullptr, ioArg->getName() + "Data");
	GeneratedAllocas.push_back(dataVar);
	switch (byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
		break;
	case ByteEnableEncoding::BEE_MASK: {
		if (hasMask()) {
			assert(dataWidth % byteWidth == 0);
			assert(dataMaskVar == nullptr);
			IntegerType *maskT = IntegerType::getIntNTy(C,
					dataWidth / byteWidth);
			dataMaskVar = builder.CreateAlloca(maskT, nullptr,
					ioArg->getName() + "DataMask");
			GeneratedAllocas.push_back(dataMaskVar);
		}
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		if (hasEnable()) {
			dataEnableVar = builder.CreateAlloca(IntegerType::getInt1Ty(C),
					nullptr, ioArg->getName() + "DataEmpty");
			GeneratedAllocas.push_back(dataEnableVar);
		}
		if (hasEmpty()) {
			assert(dataMaskVar == nullptr);
			// force supportZLP because it is necessary to store size value to empty during initialization of writes
			IntegerType *emptyT = IntegerType::getIntNTy(C,
					getWidthOfEmptyForData(dataWidth, byteWidth, true));
			dataEmptyVar = builder.CreateAlloca(emptyT, nullptr,
					ioArg->getName() + "DataEmpty");
			GeneratedAllocas.push_back(dataEmptyVar);
		}
		break;
	}
	}
	assert(dataSoFVar == nullptr);
	if (hasSoF()) {
		dataSoFVar = builder.CreateAlloca(IntegerType::getInt1Ty(C), nullptr,
				ioArg->getName() + "DataSoF");
		GeneratedAllocas.push_back(dataSoFVar);
	}
	assert(dataEoFVar == nullptr);
	if (hasEoF()) {
		dataEoFVar = builder.CreateAlloca(IntegerType::getInt1Ty(C), nullptr,
				ioArg->getName() + "DataEoF");
		GeneratedAllocas.push_back(dataEoFVar);
	}
	assert(dataErrorVar == nullptr);
	if (hasError()) {
		dataErrorVar = builder.CreateAlloca(IntegerType::get(C, errorWidth),
				nullptr, ioArg->getName() + "DataError");
		GeneratedAllocas.push_back(dataErrorVar);
	}

	if (!dataOffsetVar)
		dataOffsetVar = _getOrCreateTmpVarDataOffset(&builder);
	if (std::find(GeneratedAllocas.begin(), GeneratedAllocas.end(),
			dataOffsetVar) == GeneratedAllocas.end())
		GeneratedAllocas.push_back(dataOffsetVar);
}

void StreamChannelProps::commonVarsInitialize(
		llvm::IRBuilderBase &Builder) const {
	if (wDataPendingVar)
		setVarU64(Builder, 0, wDataPendingVar);
	switch (byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
		break;
	case ByteEnableEncoding::BEE_MASK: {
		if (hasMask()) {
			// must be initialized to 0 otherwise we will not be able to resolve in data from prev. iteration is valid or not
			Builder.CreateStore(
					ConstantInt::get(dataMaskVar->getAllocatedType(), 0),
					dataMaskVar);
		}
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		if (hasEnable()) {
			Builder.CreateStore(Builder.getInt1(0), dataEnableVar);
		}
		if (hasEmpty()) {
			// must be initialized to all 1s otherwise we will not be able to resolve in data from prev. iteration is valid or not
			Builder.CreateStore(
					ConstantInt::getAllOnesValue(
							dataEmptyVar->getAllocatedType()), dataEmptyVar);
		}
	}
	}
	Builder.CreateStore(PoisonValue::get(dataVar->getAllocatedType()), dataVar);
	if (hasSoF())
		Builder.CreateStore(Builder.getInt1(0), dataSoFVar);
	if (hasEoF())
		Builder.CreateStore(Builder.getInt1(0), dataEoFVar);
	if (hasError())
		Builder.CreateStore(Builder.getIntN(errorWidth, 0), dataErrorVar);

}

void StreamChannelProps::createWDataPendingVar(llvm::IRBuilderBase &builder) {
	auto &C = builder.getContext();

	assert(wDataPendingVar == nullptr);
	wDataPendingVar = builder.CreateAlloca(IntegerType::getInt1Ty(C), nullptr,
			ioArg->getName() + "DataPending");
	GeneratedAllocas.push_back(wDataPendingVar);
}

StreamChannelProps findStreamIoPropsInMetadata(const Function &F, Value *ioArg,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas) {
	auto srcArg = dyn_cast<Argument>(ioArg);
	assert(srcArg);
	auto _md = HwtHlsIoMetadata_get(F, srcArg->getArgNo());
	if (!_md.has_value())
		throw std::runtime_error(
				"Can not find HwtHlsIoMetadata metadata on function");
	if (!StreamChannelProps::ioMetadataHasStreamMetadata(_md.value()))
		throw std::runtime_error(
				"Can not find hwtHls.io.protocol.stream metadata on function");

	auto *md = _md.value().ioProtocolMd;

	auto props = StreamChannelFormatInfo::parseMetadata(*srcArg,
			_md.value().isOut(), md);
	return StreamChannelProps(props, GeneratedAllocas);
}

void StreamChannelProps::findStreamAccessInstructions() {
	_getOrCreateTmpVarDataOffset(nullptr, true);
	for (auto U : ioArg->users()) {
		if (auto *CI = dyn_cast<llvm::CallInst>(U)) {
			if (IsStreamWrite(CI) || IsStreamWriteStartOfFrame(CI)
					|| IsStreamWriteEndOfFrame(CI)) {
				auto ioArg = streamWriteGetIoArg(CI);
				assert(ioArg == ioArg);
			}
			if (IsStreamRead(CI) || IsStreamReadStartOfFrame(CI)
					|| IsStreamReadEndOfFrame(CI)) {
				auto ioArg = streamReadGetIoArg(CI);
				assert(ioArg == ioArg);
			}
			ios.insert(CI);
		}
	}
}

std::vector<StreamChannelProps> getStreamIoProps(llvm::Function &F,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas) {
	std::vector<StreamChannelProps> streamProps;
	auto ioMds = HwtHlsIoMetadata_get(F);
	auto srcArg = F.arg_begin();
	for (auto &ioMd : ioMds) {
		if (StreamChannelFormatInfo::ioMetadataHasStreamMetadata(ioMd)) {
			auto sfprops = StreamChannelFormatInfo::parseMetadata(*srcArg,
					ioMd.isOut(), ioMd.ioProtocolMd);
			auto sprops = StreamChannelProps(sfprops, GeneratedAllocas);
			sprops.findStreamAccessInstructions();
			streamProps.push_back(sprops);
		}
		++srcArg;
	}
	return streamProps;
}

}
