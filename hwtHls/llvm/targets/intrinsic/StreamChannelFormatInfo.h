#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>

namespace hwtHls {

enum ByteEnableEncoding {
	BEE_NONE, // no signal of byte validity bytes are assumed to be always valid
	BEE_MASK, // last word may have suffix bytes invalidated if mask bits are not set
	BEE_ENABLE_PLUS_EMPTY, // there is a enable flag which specifies that word holds some part of frame
// if this is the last word empty holds a number of bytes unused in this word.
};

enum FramingSignalizationEconding {
	FRAMING_NONE, // framing is not signalized by any dedicated bit
	FRAMING_EOF, // End of Frame bit is present
	FRAMING_SOF_EOF, // eof + Start of Frame
};
// :note: for locations of bits in words are derived from HwIO classes from hwtLib:
// * Axi4Stream (data, strb/keep?, err?, sof?, eof?)
// * Axi4StreamSegmented (data[n], (enable?, sof?, eof?, err?, empty)[n])
// * mask can have 0 suffix only in last word, else it must be all 1
// * data begins at data bit 0, segment 0, data is on lsb bits of bus word
class StreamChannelFormatInfo {
public:
	static inline size_t FramingSignalizationEconding_getWidth(
			FramingSignalizationEconding v);

protected:
	StreamChannelFormatInfo(llvm::Argument &ioArg) :
			ioArg(&ioArg), isOutput(false), dataWidth(0), byteWidth(0), byteEnableEncoding(
					ByteEnableEncoding::BEE_NONE), supportZLP(false), framingEncoding(
					FramingSignalizationEconding::FRAMING_NONE), errorWidth(0), segmentCnt(
					0), segmentTy(nullptr), wordTy(nullptr) {
	}
	void initWordTySegmentTy();

public:
	static StreamChannelFormatInfo parseMetadata(llvm::Argument &ioArg,
			bool isOutput, llvm::MDTuple *streamIoMd);
	static std::optional<StreamChannelFormatInfo> findOptionalInMetadata(
			llvm::Argument &ioArg);
	static StreamChannelFormatInfo findInMetadata(llvm::Argument &ioArg);
	static std::vector<StreamChannelFormatInfo> parseAllMetadata(
			llvm::Function &F);
	StreamChannelFormatInfo resize(size_t newDataWidth,
			std::optional<bool> newSupportZLP = { },
			std::optional<ByteEnableEncoding> newByteEnableEncoding = { }) const;

	// argument on top function which is used to access the interface
	llvm::Argument *ioArg;
	// true if channel is output, false if it is input
	bool isOutput;
	// bit width of data signal of the stream interface (not the same thing as ioArg width, it contains other signals concatenated)
	size_t dataWidth;
	// number of bits addressed by one bit of mask
	size_t byteWidth;
	ByteEnableEncoding byteEnableEncoding;
	// true if interface supports Zero Length Packets
	bool supportZLP;
	FramingSignalizationEconding framingEncoding;
	// number of bits for signal holding error value, error signal bits are valid only in last word
	// of the frame and meaning is usually application specific
	size_t errorWidth;

	// number of segments in this interfaces, if >1 the wires of interface are physically divided
	// into multiple segments each represented by a single nativeWordTy. This division allows
	// for transfer of multiple packets in single beat. This also solves throughput degradation for
	// wide buses and misalligned packets sizes but it comes at the cost of increased circuit complexity.
	size_t segmentCnt;

	// the load and store to a pointer representing this stream is segmentCnt*nativeSegmentTy = wordTy
	llvm::IntegerType *segmentTy;
	// word used for native communication using this stream, it is composed of segmentTy in a way described
	// in doc of this class :class:`StreamChannelFormatInfo`
	llvm::IntegerType *wordTy;

	static const std::string METADATA_NAME;

	// get number of bus words required to transfer "width" number of bits with specified offset
	size_t _getBusWordCntForChunk(size_t offset, size_t width) const;

	// This function computes total number of bits returned by read which includes data bits and other values like eof/sof flags mask, etc.
	// :param readDataWidth: number of bits of data which this read reads
	// :param mayBeEmpty: if true the read return data is allowed to contain no data,
	//   this makes difference when there is pow2 bytes in word and byte enable encoding uses "empty" which must
	//   now have +1 bits to accommodate value representing that all bytes of word are empty
	size_t getReadReturnWidth(size_t readDataWidth, bool mayBeEmpty) const;

	// query functions for specific stream features of stream
	bool hasSoF() const;	// has Start-of-Frame signal
	bool hasEoF() const; // has End-of-Frame signal
	bool hasEnable() const; // has segment enable signal
	bool hasEmpty() const; // has empty to signalize number of unused bytes in last word
	bool hasMask() const; // has mask to signalize valid bytes in last word
	bool hasError() const; // returns true if channel supports signaling of the error

	size_t getOffsetOfData() const;
	size_t getOffsetOfError() const;
	size_t getOffsetOfSoF() const;
	size_t getOffsetOfEoF() const;
	size_t getOffsetOfEmpty() const;
	size_t getOffsetOfMask() const;
	size_t getOffsetOfEnable() const;
	size_t getWidthOfEmpty() const;
	static size_t getWidthOfEmptyForData(size_t dataWidth, size_t byteWidth,
			bool supportZLP);
	size_t getWidthOfMask() const;
	size_t getWidthOfMaskForData(size_t dataWidth) const;
	size_t getWidthOfFramingEncoding() const;
	size_t getWidthOfBusWord() const;

	std::pair<size_t, size_t> _resolveMinMaxSegmentCount(
			const std::vector<size_t> &possibleOffsets,
			size_t chunkWidth) const;

	void CreateAssumptionForControl(llvm::IRBuilderBase &Builder,
			llvm::Value *segmentVal);
	// :note: mask, eof are optional are extracted from segment value if not provided
	void CreateAssumptionForMask(llvm::IRBuilderBase &Builder,
			llvm::Value *segmentValue, llvm::Value *mask,
			llvm::Value *eof) const;
	// :note: enable, empty, eof are optional are extracted from segment value if not provided
	void CreateAssumptionForEmpty(llvm::IRBuilderBase &Builder,
			llvm::Value *segmentValue, llvm::Value *empty,
			llvm::Value *eof) const;

	llvm::Value* streamReadGetSoF(llvm::IRBuilderBase &Builder,
			llvm::CallInst *r) const;
	llvm::Value* streamReadGetEoF(llvm::IRBuilderBase &Builder,
			llvm::CallInst *r) const;
	llvm::Value* streamReadGetData(llvm::IRBuilderBase &Builder,
			llvm::CallInst *r) const;
	llvm::Value* streamReadGetMask(llvm::IRBuilderBase &Builder,
			llvm::CallInst *r) const;
	llvm::Value* streamReadGetEmpty(llvm::IRBuilderBase &Builder,
			llvm::CallInst *r) const;
	llvm::Value* streamReadGetEnable(llvm::IRBuilderBase &Builder,
			llvm::CallInst *r) const;

	llvm::Value* streamReadFindSoF(llvm::CallInst *r) const;
	llvm::Value* streamReadFindEoF(llvm::CallInst *r) const;
	llvm::Value* streamReadFindData(llvm::CallInst *r) const;
	llvm::Value* streamReadFindMask(llvm::CallInst *r) const;
	llvm::Value* streamReadFindEmpty(llvm::CallInst *r) const;

	bool isStreamReadEoF(const llvm::CallInst *read, llvm::Value *EoF) const;
	bool isStreamReadEnableOfSegment(const llvm::LoadInst *segmentLd,
			llvm::Value *segmentEn) const;
	llvm::Value* streamReadGetError(llvm::IRBuilderBase &Builder,
			llvm::CallInst *r) const;
	llvm::Value* CreateExtractSegmentValue(llvm::IRBuilderBase &Builder,
			llvm::Value *allSegmentValue, size_t segmentIndex) const;

	static bool ioMetadataHasStreamMetadata(HwtHlsIoMetadata &md);

	bool operator==(const StreamChannelFormatInfo &other) const {
		return ioArg == other.ioArg &&                       //
				isOutput == other.isOutput &&                    //
				dataWidth == other.dataWidth &&                  //
				byteWidth == other.byteWidth &&                  //
				byteEnableEncoding == other.byteEnableEncoding &&            //
				supportZLP == other.supportZLP &&                //
				framingEncoding == other.framingEncoding &&      //
				errorWidth == other.errorWidth &&                //
				segmentCnt == other.segmentCnt;                  //
	}
};

}
