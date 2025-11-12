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
	llvm::Value *sof; // start of frame, :note: sof, eof are optional
	llvm::Value *eof; // end of frame
	llvm::Value *error; // error is optional

	StreamChannelWordValue(const StreamChannelFormatInfo props,
			llvm::Value *data, llvm::Value *mask, llvm::Value *enable,
			llvm::Value *empty, llvm::Value *sof, llvm::Value *eof,
			llvm::Value *error);
	std::array<llvm::Value*, 7> asArray();
	void setFromArray(const std::array<llvm::Value*, 7> & arr);

	/*
	 * :attention: This expects that all words except the last one are fully occupied.
	 * :param resultIsReliable: check hwthls.streamRead isReliable (if true any byte enable signaling is omitted as it is assumed that data will be always present)
	 * */
	static StreamChannelWordValue concat(llvm::IRBuilderBase &builder,
			llvm::ArrayRef<StreamChannelWordValue> lowerFirstMembers, bool resultIsReliable=false);

	// In cases where the word does not have any variable encoding byte enable (mask/empty/...)
	// because it is guaranteed that the data will be present but the IO itself has some byte enable
	// it is required to add all enable value. This is done by this function.
	void populateWithDummyMaskOrEmptyIfNecessary(llvm::IRBuilderBase &Builder);

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

	/*
	 * :param isGuarangeedToContainSomeData: if the data is guaranteed to not contain EoF it is also guaranteed
	 *      to have all bytes valid, thus empty/mask can be omitted
	 * */
	StreamChannelWordValue slice(llvm::IRBuilderBase &builder,
			size_t dataLowBitIndex, size_t bitsToTake,
			bool isGuaranteedToBeNotEoF,
			bool isGuarangeedToContainSomeData) const;
	// concatenate all values to for a value for a segment of a bus word
	// :param lastWordHasAdditionalData: an optional llvm::Value * for flag. If true there is a successor
	//  	data in last bus word and eof flag is cleared for this chunk.
	llvm::Instruction* flatten(llvm::IRBuilderBase &builder,
			llvm::Value *lastWordHasAdditionalData) const;

	void stripByteEnableEncoding();

	static StreamChannelWordValue parseNativeWord(
			const StreamChannelFormatInfo &props, llvm::IRBuilderBase &Builder,
			llvm::Instruction *nativeWord);


	llvm::Value * CreateMaskToEmpty(llvm::IRBuilderBase &builder, llvm::Value * mask) const;
	llvm::Value * CreateEmptyToMask(llvm::IRBuilderBase &builder, llvm::Value * empty) const;
};

}
