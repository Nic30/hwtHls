#include <hwtHls/llvm/targets/intrinsic/StreamChannelWordValue.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/bitMath.h>

using namespace llvm;

namespace hwtHls {

StreamChannelWordValue::StreamChannelWordValue(
		const StreamChannelFormatInfo props, llvm::Value *data,
		llvm::Value *mask, llvm::Value *enable, llvm::Value *empty,
		llvm::Value *sof, llvm::Value *eof, llvm::Value *error) :
		props(props), data(data), mask(mask), enable(enable), empty(empty), sof(
				sof), eof(eof), error(error) {
	assert(data);
	assert(props.hasMask() == (mask != nullptr));
	assert(
			(props.byteEnableEncoding
					== ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY)
					== (enable != nullptr));
	assert(props.hasEmpty() == (empty != nullptr));
	assert(props.hasSoF() == (sof != nullptr));
	assert(props.hasEoF() == (eof != nullptr));
	assert(props.hasError() == (error != nullptr));

	assert(!data || data->getType()->getIntegerBitWidth() == props.dataWidth);
	assert(
			!empty
					|| empty->getType()->getIntegerBitWidth()
							== props.getWidthOfEmpty());
	assert(!sof || sof->getType()->getIntegerBitWidth() == 1);
	assert(!eof || eof->getType()->getIntegerBitWidth() == 1);
	assert(
			!error
					|| error->getType()->getIntegerBitWidth()
							== props.errorWidth);
}

StreamChannelWordValue StreamChannelWordValue::concat(
		llvm::IRBuilderBase &builder,
		llvm::ArrayRef<StreamChannelWordValue> lowerFirstMembers) {
	assert(lowerFirstMembers.size());
	llvm::SmallVector<llvm::Value*> data;
	llvm::SmallVector<llvm::Value*> mask; // mask is concatenated
	// enable from first part is used
	// empty from last part is used
	llvm::SmallVector<llvm::Value*> error; // error is or-ed
	// sof from first part is used
	llvm::SmallVector<llvm::Value*> eof; // eof is or-ed

	assert(!lowerFirstMembers.empty());
	const auto & props =  lowerFirstMembers[lowerFirstMembers.size() > 2 ? 1 : 0].props;
	for (auto &d : lowerFirstMembers) {
		bool isLast = &d == &lowerFirstMembers.back();
		bool isFirst = &d == &lowerFirstMembers.front();
		assert(isFirst || isLast || d.props == props);
		assert(d.data);
		data.push_back(d.data);
		assert(props.hasMask() == (d.mask != nullptr));
		if (!isLast)
			assert(props.hasEmpty() == (d.empty != nullptr));
		assert(props.hasSoF() == (d.sof != nullptr));
		assert(props.hasEoF() == (d.eof != nullptr));
		assert(props.hasError() == (d.error != nullptr));

		if (d.mask) {
			mask.push_back(d.mask);
		} else if (d.empty) {
			if (&d != &lowerFirstMembers.back()) {
				assert(
						isa<ConstantInt>(d.empty)
								&& cast<ConstantInt>(d.empty)->isZero());
			}
		}
		if (d.eof)
			eof.push_back(d.eof);
		if (d.error)
			error.push_back(d.error);
	}
	Value *_data = CreateBitConcat(&builder, data);
	Value *_mask = nullptr;
	if (!mask.empty()) {
		_mask = CreateBitConcat(&builder, mask);
	}
	auto &item0 = lowerFirstMembers[0];
	// :note: this expect that all words, except last, have always all bytes valid
	//        but the first and last word may be smaller than words in the middle
	Value *_empty = lowerFirstMembers.back().empty;
	auto newStreamProps = item0.props.resize(
			_data->getType()->getIntegerBitWidth());
	if (_empty) {
		_empty = builder.CreateZExt(_empty,
				builder.getIntNTy(newStreamProps.getWidthOfEmpty()));
	}
	Value *_eof = nullptr;
	if (eof.size()) {
		_eof = builder.CreateOr(eof);
	}
	Value *_error = nullptr;
	if (!error.empty()) {
		_error = CreateBitConcat(&builder, error);
	}
	if (newStreamProps.hasEmpty() && !_empty) {
		// because we concatenated multiple bytes together empty now can not be omitted
		_empty = builder.getIntN(newStreamProps.getWidthOfEmpty(), 0);
	}
	return {
		newStreamProps,
		_data,
		_mask,
		item0.enable,
		_empty,
		item0.sof,
		_eof,
		_error,
	};
}

llvm::Value* StreamChannelWordValue::computeEmptyForDataExtract(
		llvm::IRBuilderBase &builder, size_t byteWidth, llvm::Value *empty,
		size_t srcDataWidth, size_t srcDataBitOffset, size_t dstDataWidth,
		bool dstMayBeEmpty) {
	assert(srcDataBitOffset + dstDataWidth <= srcDataWidth);
	size_t bytesAfterThis = (srcDataWidth - (srcDataBitOffset + dstDataWidth))
			/ byteWidth;
	Type *srcEmptyTy = empty->getType();
	size_t dstBytes = dstDataWidth / byteWidth;
	// example:
	// src = 4 bytes, empty=2,  thus byte 3,4 is invalid
	// srcDataBitOffset=8, dstDataWidth=16 select bytes 2,3
	// empty = umin(dstBytes+bytesAfterThis, empty) = umin(2+1, 2) = 2 // this covers the case where bytes before select were empty
	// empty = umax(empty, bytesAfterThis) = umax(2, 1) = 2 // this covers the case where there were valid bytes after selected section
	// empty = empty - bytesAfterThis = 2 - 1 = 1 // apply offset to convert to new range

	// this covers the case where bytes before select were empty
	empty = builder.CreateIntrinsic(Intrinsic::umin, srcEmptyTy, {
			ConstantInt::get(srcEmptyTy, dstBytes + bytesAfterThis), empty });
	// this covers the case where there were valid bytes after selected section
	empty = builder.CreateIntrinsic(Intrinsic::umax, srcEmptyTy, { empty,
			ConstantInt::get(srcEmptyTy, bytesAfterThis) });
	// apply offset to convert to new range
	empty = builder.CreateSub(empty,
			ConstantInt::get(srcEmptyTy, bytesAfterThis), "", /*HasNUW*/true);
	size_t newWidthOfEmpty = StreamChannelFormatInfo::getWidthOfEmptyForData(
			dstDataWidth, byteWidth, dstMayBeEmpty);
	empty = builder.CreateTrunc(empty, builder.getIntNTy(newWidthOfEmpty));
	return empty;
}

llvm::Value* StreamChannelWordValue::computeEmptyForDataInsert(
		llvm::IRBuilderBase &builder, size_t byteWidth, llvm::Type &dstEmptyTy,
		llvm::Value &srcEmpty, size_t srcDataWidth, size_t srcDataBitOffset,
		size_t srcWidthToTake, size_t dstDataBitOffset, size_t dstDataWidth) {
	//auto emptyToSize = [](size_t empty, size_t totalSize) {
	//	return totalSize - empty;
	//};
	auto sizeToEmpty = [](size_t size, size_t totalSize) {
		return totalSize - size;
	};
	// empty is a number of unused bytes in word
	// word is composed of bytes, it may contain unused bytes at the end
	// In current situation we have a chunk of data, it may be larger, smaller or equal to word size.
	// This chunk of data comes with empty. This empty is specific to chunk.
	// Now we are storing part of this chunk to a word. And thus we must convert the empty of chunk to update of empty
	// for this current word.
	size_t bytesInCurrentWord = dstDataBitOffset / byteWidth;
	size_t bytesInWord = dstDataWidth / byteWidth;
	size_t bytesMissingInCurrentWord = bytesInWord - bytesInCurrentWord;
	assert(bytesMissingInCurrentWord > 0);
	assert(srcDataWidth % byteWidth == 0);
	size_t bytesInWrite = srcDataWidth / byteWidth;
	assert(srcWidthToTake % byteWidth == 0);
	size_t bytesToTake = srcWidthToTake / byteWidth;

	size_t bytesBeforeSelectedBytesInWrite = srcDataBitOffset / byteWidth;
	//size_t bytesAfterSelectedBytesInWrite = bytesInWrite - bytesToTake - bytesBeforeSelectedBytesInWrite;
	Type *srcEmptyTy = srcEmpty.getType();

	// assert that lower value of empty is greater or equal to a value which signalizes that all src data are invalid
	Value *empty = builder.CreateIntrinsic(Intrinsic::umin, srcEmptyTy,
			{ &srcEmpty, ConstantInt::get(srcEmptyTy,
					bytesBeforeSelectedBytesInWrite) });
	// assert that upper value of empty specifies less or equal bytes than it is empty in current word
	// select minumum from src empty and max empty specifying that all bytes are invalid
	Value *emptyMax = ConstantInt::get(srcEmptyTy,
			sizeToEmpty(bytesBeforeSelectedBytesInWrite + bytesToTake,
					bytesInWrite));
	empty = builder.CreateIntrinsic(Intrinsic::umax, srcEmptyTy, { empty,
			emptyMax });

	if (dstEmptyTy.getIntegerBitWidth() < srcEmptyTy->getIntegerBitWidth()) {
		empty = builder.CreateZExt(empty, &dstEmptyTy);
	}
	// convert empty to size
	// convert from empty of write to empty for current word
	//Value* sizeToAdd = builder.CreateSub(ConstantInt::get(empty->getType(), bytesInWrite), empty, "", /*HasNUW*/true);

	size_t emptyForEndInSrc = bytesInWord - (bytesInCurrentWord + bytesToTake);
	size_t emptyForEndInCur = bytesInWrite
			- (bytesBeforeSelectedBytesInWrite + bytesToTake);

	if (emptyForEndInSrc == emptyForEndInCur) {

	} else if (emptyForEndInSrc < emptyForEndInCur) {
		Value *off = ConstantInt::get(empty->getType(),
				emptyForEndInCur - emptyForEndInSrc);
		empty = builder.CreateAdd(empty, off, "", /*HasNUW*/true);
	} else {
		assert(emptyForEndInSrc > emptyForEndInCur);
		Value *off = ConstantInt::get(empty->getType(),
				emptyForEndInSrc - emptyForEndInCur);
		empty = builder.CreateSub(empty, off, "", /*HasNUW*/true);
	}
	empty = builder.CreateTrunc(empty, &dstEmptyTy);
	return empty;
}

StreamChannelWordValue StreamChannelWordValue::slice(
		llvm::IRBuilderBase &builder, size_t dataLowBitIndex, size_t bitsToTake,
		bool isGuaranteedToBeNotEoF, bool isGuarangeedToContainSomeData) const {
	assert(bitsToTake > 0);
	bool mayBeEmpty = isGuarangeedToContainSomeData ? props.supportZLP : true;
	auto newProps = props.resize(bitsToTake, mayBeEmpty);
	Value *_data = CreateBitRangeGetConst(&builder, data, dataLowBitIndex,
			bitsToTake);
	Value *_mask = nullptr;
	Value *_eof = eof;
	Value *_sof = sof;
	Value *_enable = enable;
	Value *_error = error;
	Value *_empty = newProps.hasEmpty() ? empty : nullptr;
	const size_t dataWidth = data->getType()->getIntegerBitWidth();
	const size_t byteWidth = props.byteWidth;
	if (dataLowBitIndex != 0) {
		if (sof) {
			_sof = ConstantInt::get(_sof->getType(), 0);
		}
	}
	Value *readIsFollowedByMoreData = nullptr;
	bool endsOnEndOfThisWord = dataLowBitIndex + bitsToTake
			== dataWidth;
	if (isGuaranteedToBeNotEoF) {
		if (_enable) {
			_enable = ConstantInt::get(_enable->getType(), 1);
		}
		if (props.hasMask()) {
			_mask = ConstantInt::getAllOnesValue(
					builder.getIntNTy(bitsToTake / byteWidth));
		}
		if (_empty) {
			_empty = builder.getIntN(newProps.getWidthOfEmpty(), 0);
		}
		if (_eof) {
			_eof = ConstantInt::get(_eof->getType(), 0);
		}
		if (_error) {
			_error = ConstantInt::get(_error->getType(), 0);
		}
	} else {
		switch (props.byteEnableEncoding) {
		case ByteEnableEncoding::BEE_NONE: {
			if (!endsOnEndOfThisWord && _eof) {
				// never last
				_eof = ConstantInt::getFalse(builder.getContext());
			}
			break;
		}
		case ByteEnableEncoding::BEE_MASK: {
			assert(dataWidth % byteWidth == 0);
			// resolve eof, if this is not last read in read sequence we have to check also mask of next byte
			// to verify this is really the end and not just some middle byte in last word
			// nextMaskBit
			if (!endsOnEndOfThisWord) {
				if (props.hasEoF() || props.hasError())
					readIsFollowedByMoreData = CreateBitRangeGetConst(&builder,
							mask, (dataLowBitIndex + bitsToTake) / byteWidth, 1);
			}
			if (props.hasMask()) {
				_mask = CreateBitRangeGetConst(&builder, mask,
						dataLowBitIndex / byteWidth, bitsToTake / byteWidth);
			}
			break;
		}
		case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
			if (props.hasEmpty()) {
				size_t maxValueOfEmptyToHaveAllRBytesStillOccupied = (dataWidth
						- (dataLowBitIndex + bitsToTake)) / byteWidth;
				auto emptyT = empty->getType();
				if (!endsOnEndOfThisWord) {
					if (props.hasEoF() || props.hasError())
						readIsFollowedByMoreData =
								builder.CreateICmpULT(empty,
										ConstantInt::get(emptyT,
												maxValueOfEmptyToHaveAllRBytesStillOccupied));
				}
				if (newProps.hasEmpty()) {
					_empty = computeEmptyForDataExtract(builder, byteWidth, empty,
							props.dataWidth, dataLowBitIndex, bitsToTake,
							mayBeEmpty);
				}
			}
			break;
		}
		default:
			llvm_unreachable("Unknown value for ByteEnableEncoding");
		}
	}

	if (readIsFollowedByMoreData) {
		// set eof and error only if this is last part of the data
		if (eof) {
			_eof = builder.CreateAnd(eof,
					builder.CreateNot(readIsFollowedByMoreData));
		}
		if (error) {
			_error = builder.CreateSelect(readIsFollowedByMoreData,
					ConstantInt::get(error->getType(), 0), error);
		}
	}

	assert(newProps.hasEmpty() == (_empty != nullptr));
	return {newProps, _data, _mask, enable, _empty, _sof, _eof, _error};
}

llvm::Instruction* StreamChannelWordValue::flatten(llvm::IRBuilderBase &builder,
		llvm::Value *wordHasAdditionalData) const {

	auto _eof = eof;
	auto _error = error;
	if (wordHasAdditionalData) {
		// is last if this word is last and there is nothing in this word after this chunk
		if (eof) {
			_eof = builder.CreateAnd(eof,
					builder.CreateNot(wordHasAdditionalData));
		} else {
			assert(props.hasEoF());
		}

		if (error) {
			_error = builder.CreateSelect(wordHasAdditionalData,
					ConstantInt::get(error->getType(), 0), error);
		} else {
			assert(!props.hasError());
		}
	}

	SmallVector<Value*, 8> res;
	res.push_back(data);
	switch (props.byteEnableEncoding) {
	// Axi4Stream (data, strb?, err?, sof?, eof?)
	case ByteEnableEncoding::BEE_MASK:
		res.push_back(mask);
		__attribute__ ((fallthrough));
	case ByteEnableEncoding::BEE_NONE:
		if (props.hasError())
			res.push_back(error);
		if (props.hasSoF())
			res.push_back(sof);
		if (props.hasEoF())
			res.push_back(_eof);
		break;
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		// :note: this function produces result only for a single segment
		// Axi4StreamSegmented (data[n], (enable, sof?, eof?, err?, empty)[n])
		res.push_back(enable);
		if (props.hasSoF())
			res.push_back(sof);
		if (props.hasEoF())
			res.push_back(_eof);
		if (props.hasError())
			res.push_back(_error);
		if (props.hasEmpty()) {
			res.push_back(empty);
		}
		break;
	}
	default:
		llvm_unreachable("Invalid value for byte enable encoding of a stream");
	}
	return dyn_cast<llvm::Instruction>(CreateBitConcat(&builder, res));
}

StreamChannelWordValue StreamChannelWordValue::parseNativeWord(
		const StreamChannelFormatInfo &props, llvm::IRBuilderBase &Builder,
		llvm::Instruction *nativeWord) {
	//Builder.SetInsertPoint(nativeWord->getParent(),
	//		nativeWord->getNextNode()->getIterator());
	Instruction *data = dyn_cast<Instruction>(
			CreateBitRangeGetConst(&Builder, nativeWord, 0, props.dataWidth,
					nativeWord->getName() + ".data"));
	assert(data);

	// sof, eof and error are optional
	Value *dataSoF = nullptr;
	if (props.hasSoF())
		dataSoF = CreateBitRangeGetConst(&Builder, nativeWord,
				props.getOffsetOfSoF(), 1, nativeWord->getName() + ".sof");
	Value *dataEoF = nullptr;
	if (props.hasEoF())
		dataEoF = CreateBitRangeGetConst(&Builder, nativeWord,
				props.getOffsetOfEoF(), 1, nativeWord->getName() + ".eof");
	Instruction *dataMask = nullptr;
	llvm::Value *enable = nullptr;
	llvm::Value *empty = nullptr;
	switch (props.byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
		break;
	case ByteEnableEncoding::BEE_MASK: {
		dataMask = dyn_cast<Instruction>(
				CreateBitRangeGetConst(&Builder, nativeWord,
						props.getOffsetOfMask(),
						props.dataWidth / props.byteWidth,
						nativeWord->getName() + ".mask"));
		assert(dataMask);
		props.CreateAssumptionForMask(Builder, nativeWord, dataMask, dataEoF);
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		enable = dyn_cast<Instruction>(
				CreateBitRangeGetConst(&Builder, nativeWord,
						props.getOffsetOfEnable(), 1,
						nativeWord->getName() + ".empty"));
		if (props.hasEmpty()) {
			size_t widthOfEmpty = props.getWidthOfEmpty();
			assert(widthOfEmpty > 0);
			empty = dyn_cast<Instruction>(
					CreateBitRangeGetConst(&Builder, nativeWord,
							props.getOffsetOfEmpty(), widthOfEmpty));
			props.CreateAssumptionForEmpty(Builder, nativeWord, enable, empty,
					dataEoF);
		}
		break;
	}
	default:
		llvm_unreachable("Invalid value for ByteEnableEncoding");
	}

	llvm::Value *error = nullptr;
	if (props.hasError())
		error = CreateBitRangeGetConst(&Builder, nativeWord,
				props.getOffsetOfError(), props.errorWidth,
				nativeWord->getName() + ".error");
	return {props, data, dataMask, enable, empty, dataSoF, dataEoF, error};
}

}
