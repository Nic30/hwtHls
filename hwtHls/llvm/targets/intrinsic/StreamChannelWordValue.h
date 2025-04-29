#pragma once

#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>

namespace hwtHls {

/*
 * A structure representing segment or word value for stream IO
 * */
class StreamChannelWordValue {
public:
	StreamChannelFormatInfo props;
	llvm::Value *data;
	llvm::Value *mask; // :attention: only mask or empty encoding of the validity of bytes is allowed (or none)
	llvm::Value *enable; // enable for enable+empty signaling, :see: ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY
	llvm::Value *empty; // :attention: empty is not used if segment dataWidth == byteWidth
	llvm::Value *sof; // sof, eof are optional
	llvm::Value *eof;
	llvm::Value *error; // error is optional

	StreamChannelWordValue(const StreamChannelFormatInfo props,
			llvm::Value *data, llvm::Value *mask, llvm::Value *enable,
			llvm::Value *empty, llvm::Value *sof, llvm::Value *eof,
			llvm::Value *error);

	/*
	 * :attention: This expects that all words except the last one are fully occupied.
	 * */
	static StreamChannelWordValue concat(llvm::IRBuilderBase &builder,
			llvm::ArrayRef<StreamChannelWordValue> lowerFirstMembers);

	/* This function computes a new value for "empty" (number of unused bytes in word)
	 * for extracted slice of data from src.
	 *
	 * :param byteWidth: number of bits in byte, used to translate data width to units of "empty"
	 * :param empty: "empty" for src word
	 * :param srcDataWidth: total number of bits in src word
	 * :param srcDataBitOffset: number of bits in src before extracted section
	 * :param dstDataWidth: number of bits to extract
	 * */
	static llvm::Value* computeEmptyForDataExtract(llvm::IRBuilderBase &builder,
			size_t byteWidth, llvm::Value *empty, size_t srcDataWidth,
			size_t srcDataBitOffset, size_t dstDataWidth, bool dstMayBeEmpty);
	/*
	 * This function computes new value of "empty" (number of unused bytes in word) after
	 * up to dstDataWidth bits were copied from src to dst.
	 * :attention: This expect that the data in dst ends exactly on dstDataBitOffset.
	 * 	Underflows are not checked.
	 *
	 * :param byteWidth: number of bits in byte, used to translate data width to units of "empty"
	 * :param dstEmptyTy: data type representing dst "empty"
	 * :param srcDataWidth: total number of bits of src
	 * :param srcDataBitOffset: number of bits before selected section of src to copy
	 * :param srcWidthToTake: number of bits to copy from src to dst
	 * :param dstDataBitOffset: number of bits before section where copied data should be placed in dst
	 * :param dstDataWidth: total number of bits of dst
	 * :param srcEmpty: number of unused bytes in src value (for whole src, without srcDataBitOffset applied)
	 * */
	static llvm::Value* computeEmptyForDataInsert(llvm::IRBuilderBase &builder,
			size_t byteWidth, llvm::Type &dstEmptyTy, llvm::Value &srcEmpty,
			size_t srcDataWidth, size_t srcDataBitOffset, size_t srcWidthToTake,
			size_t dstDataBitOffset, size_t dstDataWidth);

	StreamChannelWordValue slice(llvm::IRBuilderBase &builder,
			size_t dataLowBitIndex, size_t bitsToTake,
			bool isGuaranteedToBeNotEoF,
			bool isGuarangeedToContainSomeData) const;
	// concatenate all values to for a value for a segment of a bus word
	// :param wordHasAdditionalData: an optional llvm::Value * for flag. If true there is a successor
	//  data and eof flag is cleared.
	llvm::Instruction* flatten(llvm::IRBuilderBase &builder,
			llvm::Value *wordHasAdditionalData) const;

	static StreamChannelWordValue parseNativeWord(
			const StreamChannelFormatInfo &props, llvm::IRBuilderBase &Builder,
			llvm::Instruction *nativeWord);
	llvm::Value* deparseNativeWord(llvm::IRBuilderBase &builder) const;

};

}
