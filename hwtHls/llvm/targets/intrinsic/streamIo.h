#pragma once
/*
 * HwtHls streamio intrinsics are used for stream communication over frame/packet oriented interfaces
 * like AXI4stream or AvalonST they represent high level access to stream io which needs to be lowered before conversion
 * to hardware.
 * */

#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

extern const std::string StreamTmpAllocaTmpSetterPlaceholder;
// create a call of function which will acts a placeholder setter to prevent removal of the AllocaInst
// while its driving logic was not constructed yet
llvm::CallInst* CreateStreamTmpAllocaTmpSetterPlaceholder(
		llvm::IRBuilderBase *Builder, llvm::AllocaInst *tmpAlloca);
bool IsStreamTmpAllocaTmpSetterPlaceholder(const llvm::CallInst *C);
bool IsStreamTmpAllocaTmpSetterPlaceholder(const llvm::Function *F);

extern const std::string StreamReadName;
extern const std::string StreamReadUnreliableName;
extern const std::string StreamReadAligningName;

/* Creates one of:
 *  * @hwtHls.streamRead.*(ioArgPtr, chunkBitWidth)
 *     always returns data which is assumed present and valid on stream (byte enable signaling (empty/mask) ignored),
 *     read return does not have byte enable signals
 *  * @hwtHls.streamRead.unreliable.*(ioArgPtr, chunkBitWidth)
 *     may return less data if stream end prematurely or if it contains holes (if using mask),
 *     returned value contains all concatenated captured data and byte enable signaling
 *  * @hwtHls.streamRead.aligning.*(ioArgPtr, chunkBitWidth, endAlignas)
 *     variant of @hwtHls.streamRead.unreliable which reads until specified position in word or specified max read bit count
 *     for example endAlignas=0 will result in read of up to chunkBitWidth until the end of the word
 *     if the read fsm is at the end of the word already this returns no valid bytes
 *     :attention: endAlignas is in bits unit
 *     :attention: must have isReliable=false by definition
 */
llvm::CallInst* CreateStreamRead(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArg, size_t chunkBitWidth, size_t returnBitWidth,
		bool isReliable, std::optional<size_t> endAlignas = std::nullopt);
bool IsStreamRead(const llvm::CallInst *C);
bool IsStreamRead(const llvm::Function *F);

llvm::Value* streamReadGetIoArg(const llvm::CallInst *C);
// get number of bits of data which this instruction actually read from stream,
// the type of instruction may contain additional things like mask/eof
size_t streamReadGetOrigChunkBitWidth(const llvm::CallInst *C);
// :see: doc for :func:`StreamReadBehaviorType`
enum class StreamReadBehaviorType {
	RELIABLE, UNRELIABLE, ALIGNING,
};
// :returns: true if EoF is an EoF of specified read instruction
StreamReadBehaviorType streamReadGetBehavior(const llvm::CallInst *C);
// :deprecated: use StreamChannelFormatInfo::streamReadGetEoF
// bool IsStreamReadEoF(const llvm::CallInst *read, llvm::Value *EoF);

extern const std::string StreamReadStartOfFrameName;
llvm::CallInst* CreateStreamReadStartOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamReadStartOfFrame(const llvm::CallInst *C);
bool IsStreamReadStartOfFrame(const llvm::Function *F);

extern const std::string StreamReadEndOfFrameName;
llvm::CallInst* CreateStreamReadEndOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamReadEndOfFrame(const llvm::CallInst *C);
bool IsStreamReadEndOfFrame(const llvm::Function *F);

extern const std::string StreamWriteName;
extern const std::string StreamWriteMaskedName;
extern const std::string StreamWritePackingName;

/*
 *  Create one of:
 *  * hwtHls.streamWrite.*(ioArgPtr, valueToWrite, isSoF, isEoF, errorVal)
 *      all bytes written bytes are valid (there is no mask/empty)
 *  * hwtHls.streamWrite.masked.*(ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF, errorVal)
 *      all bytes of data are part of the output stream (including invalidated bytes, number of written bytes is constant),
 *	    next data will be appended after it
 *  * hwtHls.streamWrite.packing.*(ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF, errorVal)
 *  	only valid bytes from written data are passed to the output stream (invalid bytes are discarded)
 *      :attention: the written valid bytes in written data must be packed left (valid bytes must begin at index 0)
 *         this option just specifies behavior for followup writes not the word itself.
 *
 * The writeMask must be all ones if this is not first or last word
 * in first word it may have 0 prefix, in last word it may have 0 suffix
 * :note: The masked variant of StreamWrite exists to make compilation faster as it is more easy to work with the mask
 *    than searching for chained writes in a complex CFG.
 */
llvm::CallInst* CreateStreamWrite(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArg, llvm::Value *valueToWrite,
		llvm::Value *writeMaskOrEmpty = nullptr, llvm::Value *isSoF = nullptr,
		llvm::Value *isEoF = nullptr, llvm::Value *errorVal = nullptr,
		bool isPacking = false);
bool IsStreamWrite(const llvm::CallInst *C);
bool IsStreamWrite(const llvm::Function *F);
// :see: doc for :func:`CreateStreamWrite`
enum class StreamWriteBehaviorType {
	ALLVALID, MASKED, PACKING,
};
StreamWriteBehaviorType streamWriteGetBehavior(const llvm::CallInst *C);
size_t streamWriteGetOrigChunkBitWidth(const llvm::CallInst *C);
llvm::Value* streamWriteGetIoArg(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteData(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteMaskOrEmpty(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteSoF(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteEoF(const llvm::CallInst *C);
llvm::Value* streamWriteGetWriteError(const llvm::CallInst *C);

extern const std::string StreamWriteStartOfFrameName;
llvm::CallInst* CreateStreamWriteStartOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamWriteStartOfFrame(const llvm::CallInst *C);
bool IsStreamWriteStartOfFrame(const llvm::Function *F);

extern const std::string StreamWriteEndOfFrameName;
llvm::CallInst* CreateStreamWriteEndOfFrame(llvm::IRBuilderBase *Builder,
		llvm::Value *ioArgPtr);
bool IsStreamWriteEndOfFrame(const llvm::CallInst *C);
bool IsStreamWriteEndOfFrame(const llvm::Function *F);

inline bool IsStreamIoStartOfFrame(const llvm::CallInst *I) {
	return IsStreamReadStartOfFrame(I) || IsStreamWriteStartOfFrame(I);
}
inline bool IsStreamIoEndOfFrame(const llvm::CallInst *I) {
	return IsStreamReadEndOfFrame(I) || IsStreamWriteEndOfFrame(I);
}
// :returns: true if the function is hwtHls.stream intrinsic
bool IsStreamIo(const llvm::CallInst *C);
// :returns: number of bits of data only for stream.read/write (excluding non data bits like mask, eof, ...)
size_t streamIoGetOrigChunkBitWidth(const llvm::CallInst *I);

}
