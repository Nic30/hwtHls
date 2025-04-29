#pragma once
#include <vector>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>

#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelWordValue.h>

namespace hwtHls {


class StreamChannelProps: public StreamChannelFormatInfo {
public:
	llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas;
	llvm::SetVector<llvm::CallInst*> ios; // all instructions which are using this stream interface
	llvm::AllocaInst *dataVar; // variable to store data word to be send
	llvm::AllocaInst *dataMaskVar; // "variable" for mask for current data word (if bit is 1 the corresponding byte is valid)
	llvm::AllocaInst *dataEnableVar; // "variable" for enable flag which signalize that word may hold valid data
	llvm::AllocaInst *dataEmptyVar; // "variable" for empty for current data word (number of unused bytes at the end of the word)
	// :note: for enable, empty and mask see :class:`ByteEnableEncoding`
	llvm::AllocaInst *dataSoFVar; // "variable" for current word Start-of-Frame flag
	llvm::AllocaInst *dataEoFVar; // "variable" for current word End-of-Frame flag
	llvm::AllocaInst *dataErrorVar; // "variable" for value of error from bus
	llvm::AllocaInst *dataOffsetVar; // "variable" which specifies writer position in current word
	llvm::AllocaInst *wDataPendingVar; // "variable" for flag which is 1 if dataVar contains data,
	// which are waiting to be send

	StreamChannelProps(const StreamChannelProps &p) = default;
	StreamChannelProps(const StreamChannelFormatInfo &scfi,
			llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas);

	void setOffsetVar(llvm::IRBuilderBase &builder, size_t val) const;

	llvm::Value* deparseNativeWord(llvm::IRBuilderBase &builder) const;
	static void setVarU64(llvm::IRBuilderBase &builder,
			std::optional<uint64_t> val, llvm::AllocaInst *var);
	/*
	 Set bits in mask vector to specified value and all bits after that to 0

	 :param dataBitOffset: number of bits in this word before part set in this function
	 :param bitsToTake: how many bits are written in this word
	 */
	void setDataMaskOrEmptyConst(llvm::IRBuilderBase &Builder,
			size_t dataBitOffset, size_t dataBitsToTakeS) const;
	/*
	 * :param widthOfWrite: number of bits in of src chunk data in total
	 * :param srcDataBitsOffset: the bit index of current data start in source value in bits
	 * :param dataBitOffset: bit index where this data is placed in current word data
	 * :param dataBitsToTake: number of bits to insert from src chunk to current word
	 * :param maskOrEmptyForWholeChunk: mask or empty for original ADT write which is sliced according to
	 * 	dataBitOffset and dataBitsToTake (mask or empty is selected based on byteEnableEncoding of a stream)
     * */
	void setDataMaskOrEmpty(llvm::IRBuilderBase &Builder, size_t widthOfWrite,
			size_t srcDataBitsOffset, size_t dataBitOffset,
			size_t dataBitsToTake, llvm::Value *maskOrEmptyForWholeChunk) const;
	void _setDataMask(llvm::IRBuilderBase &Builder, bool orWithCurrent,
			llvm::Value *newMaskValue) const;

	void setData(llvm::IRBuilderBase &Builder, llvm::Value *val,
			size_t offset) const;

	void setAllData(llvm::IRBuilderBase &Builder,
			llvm::Instruction *nativeWord) const;
	void setAllData(llvm::IRBuilderBase &Builder,
			StreamChannelWordValue data) const;
	llvm::LoadInst* getVarValue(llvm::IRBuilderBase &Builder,
			llvm::AllocaInst *var) const;
	StreamChannelWordValue getAllData(llvm::IRBuilderBase &Builder) const;
	void createCommonVars(llvm::IRBuilderBase &Builder);
	void createWDataPendingVar(llvm::IRBuilderBase &Builder);
};

// :param GeneratedAllocas: a vector of generated alloca instructions which is used in StreamChannelProps constructor
//                          it is not modified in this function
// :param ioFilter: an argument pointer which can be set to collect StreamChannelProps only for selected IO
std::vector<StreamChannelProps> getStreamIoProps(llvm::Function &F,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas,
		llvm::Argument *ioFilter = nullptr);

StreamChannelProps findStreamIoPropsInMetadata(const llvm::Function &F,
		llvm::Value *IOArg,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas);

}
