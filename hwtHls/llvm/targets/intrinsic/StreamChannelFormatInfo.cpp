#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>

#include <stdexcept>
#include <llvm/IR/Constants.h>
#include <llvm/IR/PatternMatch.h>

#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>
#include <hwtHls/llvm/targets/intrinsic/PatternMatch.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>
#include <hwtHls/llvm/intrinsic/metadataWithBitrange.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>

using namespace llvm;
using namespace llvm::PatternMatch;
using namespace hwtHls::PatternMatch;

namespace hwtHls {

static size_t MDTuple_getOperandAsU64(const MDTuple *metaTuple, size_t opI) {
	auto CM = dyn_cast<ConstantAsMetadata>(metaTuple->getOperand(opI));
	assert(CM);
	auto C = dyn_cast<ConstantInt>(CM->getValue());
	assert(C);
	return C->getZExtValue();
}

static StringRef MDTuple_getOperandAsStr(const MDTuple *metaTuple, size_t opI) {
	auto CM = dyn_cast<MDString>(metaTuple->getOperand(opI));
	assert(CM);
	return CM->getString();
}

size_t StreamChannelFormatInfo::FramingSignalizationEconding_getWidth(
		FramingSignalizationEconding v) {
	switch (v) {
	case FramingSignalizationEconding::FRAMING_NONE:
		return 0;
	case FramingSignalizationEconding::FRAMING_EOF:
		return 1;
	case FramingSignalizationEconding::FRAMING_SOF_EOF:
		return 2;
	default:
		llvm_unreachable("invalid value of FramingSignalizationEconding");
	}
}

size_t StreamChannelFormatInfo::_getBusWordCntForChunk(size_t offset,
		size_t width) const {
	return div_ceil(width + offset, dataWidth);
}

size_t StreamChannelFormatInfo::getReadReturnWidth(size_t readDataWidth, bool isRealiable) const {
	assert(!isOutput);
	switch (byteEnableEncoding) {
	// Axi4Stream (data, strb?, err?, sof?, eof?)
	case ByteEnableEncoding::BEE_NONE:
		break;
	case ByteEnableEncoding::BEE_MASK:
		readDataWidth += getWidthOfMaskForData(readDataWidth);
		break;
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY:
		// Axi4StreamSegmented (data[n], (enable, sof?, eof?, err?, empty)[n])
		return readDataWidth += /*enable*/1
				+ getWidthOfEmptyForData(readDataWidth, byteWidth, supportZLP);
	default:
		llvm_unreachable("Invalid value for byte enable encoding of a stream");
	}
	readDataWidth += errorWidth + getWidthOfFramingEncoding();
	return readDataWidth;
}

bool StreamChannelFormatInfo::hasSoF() const {
	return framingEncoding == FramingSignalizationEconding::FRAMING_SOF_EOF;
}

bool StreamChannelFormatInfo::hasEoF() const {
	return framingEncoding == FramingSignalizationEconding::FRAMING_SOF_EOF
			|| framingEncoding == FramingSignalizationEconding::FRAMING_EOF;
}

bool StreamChannelFormatInfo::hasEnable() const {
	return byteEnableEncoding == ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY;
}

bool StreamChannelFormatInfo::hasEmpty() const {
	return byteEnableEncoding == ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY
			&& dataWidth != byteWidth;
}

bool StreamChannelFormatInfo::hasMask() const {
	return byteEnableEncoding == ByteEnableEncoding::BEE_MASK;
}

bool StreamChannelFormatInfo::hasError() const {
	return errorWidth > 0;
}

size_t StreamChannelFormatInfo::getOffsetOfError() const {
	switch (byteEnableEncoding) {
	// Axi4Stream (data, strb?, err?, sof?, eof?)
	case ByteEnableEncoding::BEE_NONE:
		return dataWidth;
	case ByteEnableEncoding::BEE_MASK:
		return dataWidth + getWidthOfMask();
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY:
		// Axi4StreamSegmented (data[n], (enable, sof?, eof?, err?, empty)[n])
		return dataWidth + /*enable*/1 + getWidthOfFramingEncoding();
	default:
		llvm_unreachable("Invalid value for byte enable encoding of a stream");
	}
}

size_t StreamChannelFormatInfo::getOffsetOfSoF() const {
	assert(framingEncoding == FramingSignalizationEconding::FRAMING_SOF_EOF);
	return getOffsetOfEoF() - 1;
}

size_t StreamChannelFormatInfo::getOffsetOfEoF() const {
	assert(
			framingEncoding == FramingSignalizationEconding::FRAMING_EOF
					|| framingEncoding
							== FramingSignalizationEconding::FRAMING_SOF_EOF);
	switch (byteEnableEncoding) {
	// Axi4Stream (data, strb?, err?, sof?, eof?)
	case ByteEnableEncoding::BEE_NONE:
	case ByteEnableEncoding::BEE_MASK:
		return getOffsetOfError() + errorWidth;
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY:
		// Axi4StreamSegmented (data[n], (enable, sof?, eof?, err?, empty)[n])
		return dataWidth + /*enable*/1 + (hasSoF() ? 1 : 0);
	default:
		llvm_unreachable("Invalid value for byte enable encoding of a stream");
	}
}

size_t StreamChannelFormatInfo::getOffsetOfMask() const {
	return dataWidth;
}

size_t StreamChannelFormatInfo::getOffsetOfEnable() const {
	return dataWidth;
}

size_t StreamChannelFormatInfo::getOffsetOfEmpty() const {
	assert(byteEnableEncoding == ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY);
	return getOffsetOfError() + errorWidth;
}

size_t StreamChannelFormatInfo::getWidthOfEmpty() const {
	assert(hasEmpty());
	assert(byteEnableEncoding == ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY);
	return getWidthOfEmptyForData(dataWidth, byteWidth, supportZLP);
}


size_t StreamChannelFormatInfo::getWidthOfEmptyForData(size_t dataWidth,
		size_t byteWidth, bool supportZLP) {
	assert(dataWidth % byteWidth == 0);
	return log2ceil(dataWidth / byteWidth + (supportZLP ? 1 : 0));
}

size_t StreamChannelFormatInfo::getWidthOfMask() const {
	assert(byteEnableEncoding == ByteEnableEncoding::BEE_MASK);
	return dataWidth / byteWidth;
}

size_t StreamChannelFormatInfo::getWidthOfMaskForData(size_t dataWidth) const {
	assert(byteEnableEncoding == ByteEnableEncoding::BEE_MASK);
	assert(dataWidth > 0);
	assert(dataWidth % byteWidth == 0);
	return dataWidth / byteWidth;
}

size_t StreamChannelFormatInfo::getWidthOfFramingEncoding() const {
	return FramingSignalizationEconding_getWidth(framingEncoding);
}

size_t StreamChannelFormatInfo::getWidthOfBusWord() const {
	switch (byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
	case ByteEnableEncoding::BEE_MASK:
		// Axi4Stream (data, strb?, err?, sof?, eof?)
		return segmentCnt
				* (getOffsetOfError() + errorWidth
						+ getWidthOfFramingEncoding());
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY:
		// Axi4StreamSegmented (data[n], (enable, sof?, eof?, err?, empty?)[n])
		return segmentCnt
				* (dataWidth + /*enable*/1 + getWidthOfFramingEncoding()
						+ errorWidth + getWidthOfEmpty());
	default:
		llvm_unreachable("Invalid value for byte enable encoding of a stream");
	}
}

std::pair<size_t, size_t> StreamChannelFormatInfo::_resolveMinMaxSegmentCount(
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

void StreamChannelFormatInfo::CreateAssumptionForControl(
		llvm::IRBuilderBase &Builder, llvm::Value *segmentVal) {
	if (hasMask()) {
		CreateAssumptionForMask(Builder, segmentVal, nullptr, nullptr);
	} else if (hasEmpty()) {
		CreateAssumptionForEmpty(Builder, segmentVal, nullptr, nullptr);
	}
}

void StreamChannelFormatInfo::CreateAssumptionForMask(
		llvm::IRBuilderBase &Builder, llvm::Value *segmentValue,
		llvm::Value *mask, llvm::Value *eof) const {
	assert(hasMask());
	// Create an assumption to notify that if the mask bit is 1
	// the previous mask bit was also 1,
	// This is to allow interference of implications over mask bits.
	size_t maskOffset = getOffsetOfMask();
	size_t maskWidth = getWidthOfMask();
	Value *maskBit0 = CreateBitRangeGetConst(&Builder, segmentValue,
			getOffsetOfMask(), 1);
	Value *prevBit = maskBit0;
	if (!eof)
		eof = CreateBitRangeGetConst(&Builder, segmentValue, getOffsetOfEoF(),
				1);
	// * all mask bits 1 if not last
	// * previous mask bit 1 if this mask bit is 1
	for (size_t maskBitI = 1; maskBitI < maskWidth; ++maskBitI) {
		Value *thisBit = CreateBitRangeGetConst(&Builder, segmentValue,
				maskOffset + maskBitI, 1);
		// this bit=1 implies that prev bit=1
		Builder.CreateAssumption(
				Builder.CreateICmpULE(thisBit, prevBit, "prevMaskBit1Impl"));
		if (maskBitI > 1) {
			// this bit=1 implies that mask[0]=1
			auto a = Builder.CreateAssumption(
					Builder.CreateICmpULE(thisBit, maskBit0,
							"prevMaskBit1Impl"));
			setMetadataSideeffectAllowHoist(*a);
		}

		// [todo] after llvm-19 use this:
		// Value *prevMaskBits = CreateBitRangeGetConst(&Builder,
		// 		segmentValue, offset, maskBitI);
		//Value *maskAllPrev1 = Builder.CreateICmpEQ(prevMaskBits,
		//		ConstantInt::getAllOnesValue(prevMaskBits->getType()));
		//Builder.CreateAssumption(
		//		Builder.CreateICmpULE(thisBit, maskAllPrev1,
		//				"prevMaskBitAll1Impl"));

		// eof=0 implies that this bit=1 (maskBit==0 only if eof=1)
		// :attention: llvm-19+
		auto a = Builder.CreateAssumption(
				Builder.CreateOr(eof, thisBit, "NonEoFImplMaskBit1"));
		setMetadataSideeffectAllowHoist(*a);
		prevBit = thisBit;
	}
	if (!mask)
		mask = CreateBitRangeGetConst(&Builder, segmentValue, maskOffset,
				maskWidth);
	if (auto maskI = dyn_cast<Instruction>(mask)) {
		auto maskMdKing = Builder.getContext().getMDKindID(HwtHlsInstCombinePass::metadataName_expr_maskContinuosFromLsb);
		MetadataBitRanges::BitRanges bitR;
		MetadataBitRanges::setAndPropagateBiDir(*maskI, maskMdKing, bitR);
	}
	Value *maskAll1 = Builder.CreateICmpEQ(mask,
			ConstantInt::getAllOnesValue(mask->getType()));
	// eof=0 implies that all mask bits are 1(not eof implies that all bytes are valid because
	// there can not be a hole inside of packet which is not aligned to a word boundary)
	auto a = Builder.CreateAssumption(
			Builder.CreateOr(eof, maskAll1, "NonEoFImplMaskAll1"));
	setMetadataSideeffectAllowHoist(*a);
}

void StreamChannelFormatInfo::CreateAssumptionForEmpty(
		llvm::IRBuilderBase &Builder, Value *segmentValue, Value *empty,
		Value *eof) const {
	assert(byteEnableEncoding == ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY);
	if (hasEmpty()) {
		size_t bytesPerSegment = dataWidth / byteWidth;
		if (!empty)
			empty = CreateBitRangeGetConst(&Builder, segmentValue,
					getOffsetOfEmpty(), getWidthOfEmpty());

		if (!supportZLP) {
			if (!isPow2(bytesPerSegment)) {
				auto a = Builder.CreateAssumption(
						Builder.CreateICmpULT(empty,
								ConstantInt::get(empty->getType(),
										bytesPerSegment - 1)));
				setMetadataSideeffectAllowHoist(*a);
			}
		} else {
			if (!isPow2(bytesPerSegment)) {
				auto a = Builder.CreateAssumption(
						Builder.CreateICmpULT(empty,
								ConstantInt::get(empty->getType(),
										bytesPerSegment)));
				setMetadataSideeffectAllowHoist(*a);
			}
		}
		if (hasEoF()) {
			if (!eof)
				eof = CreateBitRangeGetConst(&Builder, segmentValue,
						getOffsetOfEoF(), 1);
			// eof=0 implies that empty==0 (not eof implies that all bytes are valid because
			// there can not be a hole inside of packet which is not aligned to a word boundary)
			auto a = Builder.CreateAssumption(
					Builder.CreateOr(eof,
							Builder.CreateICmpEQ(empty,
									ConstantInt::get(empty->getType(), 0)),
							"NonEoFImplEmptyEq0"));
			setMetadataSideeffectAllowHoist(*a);
		}
	}
}

llvm::Value* StreamChannelFormatInfo::streamReadGetEoF(
		llvm::IRBuilderBase &Builder, llvm::CallInst *r) const {
	assert(hasEoF());
	auto dw = streamReadGetOrigChunkBitWidth(r);
	auto scfi = resize(dw);
	return CreateBitRangeGetConst(&Builder, r, scfi.getOffsetOfEoF(), 1);
}

llvm::Value* StreamChannelFormatInfo::streamReadGetError(
		llvm::IRBuilderBase &Builder, llvm::CallInst *r) const {
	auto dw = streamReadGetOrigChunkBitWidth(r);
	auto scfi = resize(dw);
	return CreateBitRangeGetConst(&Builder, r, scfi.getOffsetOfError(), 1); // msb
}
bool StreamChannelFormatInfo::isStreamReadEoF(const llvm::CallInst *read,
		llvm::Value *EoF) const {
	if (!hasEoF())
		return false;
	if (EoF->getType()->getIntegerBitWidth() != 1) {
		return false;
	}
	auto scfi = resize(streamReadGetOrigChunkBitWidth(read));
	return match(EoF,
			m_BitrangeGetSpecificConst(m_Specific(read), scfi.getOffsetOfEoF(),
					1));
}

void StreamChannelFormatInfo::initWordTySegmentTy() {
	size_t nativeWordSize = dataWidth;
	switch (byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
		break;
	case ByteEnableEncoding::BEE_MASK:
		// Axi4Stream (data, strb?, err?, sof?, eof?)
		nativeWordSize += getWidthOfMask();
		break;
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY:
		// Axi4StreamSegmented (data[n], (enable, sof?, eof?, err?, empty)[n])
		nativeWordSize += /*enable*/1 + (hasEmpty() ? getWidthOfEmpty(): 0);
		break;
	default:
		llvm_unreachable(
				"hwtHls.streamIo: Invalid value for byte enable encoding of a stream");
	}
	nativeWordSize += getWidthOfFramingEncoding() + errorWidth;

	segmentTy = IntegerType::getIntNTy(ioArg->getContext(), nativeWordSize);
	wordTy = IntegerType::getIntNTy(ioArg->getContext(),
			segmentCnt * nativeWordSize);
}

StreamChannelFormatInfo StreamChannelFormatInfo::parseMetadata(
		llvm::Argument &ioArg, llvm::MDTuple *streamIoMd) {
	StreamChannelFormatInfo props(ioArg);
	assert(MDTuple_getOperandAsU64(streamIoMd, 0) == ioArg.getArgNo());
	if (streamIoMd->getNumOperands() != 9)
		throw std::runtime_error("hwtHls.streamIo: expects tuple with 9 items");
	props.isOutput = MDTuple_getOperandAsU64(streamIoMd, 1);
	props.dataWidth = MDTuple_getOperandAsU64(streamIoMd, 2);
	props.byteWidth = MDTuple_getOperandAsU64(streamIoMd, 3);
	if (props.dataWidth <= 0) {
		throw std::runtime_error(
				"hwtHls.streamIo: DataWidth of a stream must be > 0");
	}
	if (props.dataWidth % props.byteWidth != 0) {
		throw std::runtime_error(
				"hwtHls.streamIo: DataWidth must by divisible by byteWidth of a stream "
						+ std::to_string(props.dataWidth) + " byteWidth:"
						+ std::to_string(props.byteWidth));
	}
	auto beEnc = MDTuple_getOperandAsStr(streamIoMd, 4);
	if (beEnc == "mask") {
		props.byteEnableEncoding = ByteEnableEncoding::BEE_MASK;
	} else if (beEnc == "enable+empty") {
		props.byteEnableEncoding = ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY;
	} else if (beEnc == "none") {
		props.byteEnableEncoding = ByteEnableEncoding::BEE_NONE;
	} else {
		throw std::runtime_error(
				("hwtHls.streamIo: Invalid value for byte enable encoding of a stream: "
						+ beEnc).str());
	}
	props.supportZLP = MDTuple_getOperandAsU64(streamIoMd, 5);
	auto framingEnc = MDTuple_getOperandAsStr(streamIoMd, 6);
	if (framingEnc == "sof+eof") {
		props.framingEncoding = FramingSignalizationEconding::FRAMING_SOF_EOF;
	} else if (framingEnc == "eof") {
		props.framingEncoding = FramingSignalizationEconding::FRAMING_EOF;
	} else if (framingEnc == "none") {
		props.framingEncoding = FramingSignalizationEconding::FRAMING_NONE;
	} else {
		throw std::runtime_error(
				("Invalid value for framing encoding of a stream: " + framingEnc).str());
	}

	props.errorWidth = MDTuple_getOperandAsU64(streamIoMd, 7);
	props.segmentCnt = MDTuple_getOperandAsU64(streamIoMd, 8);
	props.initWordTySegmentTy();
	return props;
}

std::optional<StreamChannelFormatInfo> StreamChannelFormatInfo::findOptionalInMetadata(
		llvm::MDNode &hwtHls_streamIoMD, llvm::Argument &ioArg) {
	for (auto &_metaTuple : hwtHls_streamIoMD.operands()) {
		auto metaTuple = dyn_cast<MDTuple>(_metaTuple.get());
		assert(metaTuple);
		auto argI = MDTuple_getOperandAsU64(metaTuple, 0);
		if (argI == ioArg.getArgNo()) {
			auto props = StreamChannelFormatInfo::parseMetadata(ioArg,
					metaTuple);
			return props;
		}
	}
	return {};
}

StreamChannelFormatInfo StreamChannelFormatInfo::findInMetadata(
		llvm::Argument &ioArg) {
	auto &F = *ioArg.getParent();
	auto *md = F.getMetadata("hwtHls.streamIo");
	if (!md) {
		throw std::runtime_error(
				"function is missing hwtHls.streamIo metadata");
	}
	auto found = findOptionalInMetadata(*md, ioArg);
	if (found.has_value()) {
		return found.value();
	} else {
		throw std::runtime_error(
				"hwtHls.streamIo is missing is missing record for ioArg");
	}
}

std::vector<StreamChannelFormatInfo> StreamChannelFormatInfo::parseAllMetadata(
		llvm::Function &F) {
	std::vector<StreamChannelFormatInfo> res;
	auto *md = F.getMetadata("hwtHls.streamIo");
	if (!md) {
		return res;
	}
	for (auto &_metaTuple : md->operands()) {
		auto metaTuple = dyn_cast<MDTuple>(_metaTuple.get());
		assert(metaTuple);
		auto argI = MDTuple_getOperandAsU64(metaTuple, 0);
		if (argI >= F.arg_size())
			throw std::runtime_error(
					"hwtHls.streamIo metadata specifies the argument which is not present on function");
		auto &srcArg = *(F.arg_begin() + argI);
		auto props = StreamChannelFormatInfo::parseMetadata(srcArg, metaTuple);
		res.push_back(props);
	}
	return res;
}

StreamChannelFormatInfo StreamChannelFormatInfo::resize(
		size_t newDataWidth, std::optional<bool> newSupportZLP) const {
	StreamChannelFormatInfo res = *this;
	res.dataWidth = newDataWidth;
	if (newSupportZLP.has_value())
		res.supportZLP = newSupportZLP.value();
	res.initWordTySegmentTy();
	return res;
}

}
