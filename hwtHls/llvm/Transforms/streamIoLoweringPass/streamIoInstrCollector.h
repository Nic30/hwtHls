#pragma once
#include <vector>
#include <cstdlib>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

struct StreamChannelWordValue {
	llvm::Value *data;
	llvm::Value *mask;
	llvm::Value *last;

	static StreamChannelWordValue concat(llvm::IRBuilder<> &builder,
			llvm::ArrayRef<StreamChannelWordValue> lowerFirstMembers);
	StreamChannelWordValue slice(llvm::IRBuilder<> &builder,
			size_t dataLowBitIndex, size_t bitsToTake) const;
	llvm::Instruction* flatten(llvm::IRBuilder<> &builder) const;
};

class StreamChannelProps {
public:
	llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas;
	llvm::Argument *ioArg; // argument on top function which is used to access the interface
	llvm::IntegerType *nativeWordTy;
	size_t dataWidth; // bit width of data signal of the stream interface (not the same thing as ioArg width, it contains other signals concatenated)
	bool hasMask; // if true the interface has data mask which is part of the data returned by reads
	bool isOutput; // true if channel is output, false if it is input
	llvm::SetVector<llvm::CallInst*> ios; // all instructions which are using this stream interface
	llvm::AllocaInst *dataVar;
	llvm::AllocaInst *dataMaskVar;
	llvm::AllocaInst *dataLastVar;
	llvm::AllocaInst *dataOffsetVar;
	llvm::AllocaInst *wDataPendingVar;
	StreamChannelProps(const StreamChannelProps & p) = default;
	StreamChannelProps(llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas,
			llvm::Argument *ioArg);

	void setOffsetVar(llvm::IRBuilder<> &builder, size_t val) const;
	StreamChannelWordValue parseNativeWord(llvm::IRBuilder<> &builder,
			llvm::Instruction *nativeWord) const;
	llvm::Value* deparseNativeWord(llvm::IRBuilder<> &builder) const;
	static void setVarU64(llvm::IRBuilder<> &builder, std::optional<uint64_t> val,
			llvm::AllocaInst *var);
	/*
	 Set bits in mask vector to specified value and all bits after that to 0

	 :param dataBitOffset: number of bits in this word before part set in this function
	 :param bitsToTake: how many bits are written in this word
	 */
	void setDataMaskConst(llvm::IRBuilder<> &builder, size_t dataBitOffset,
			size_t dataBitsToTakeS) const;
	void setData(llvm::IRBuilder<> &builder, llvm::Value *val,
			size_t offset) const;

	void setAllData(llvm::IRBuilder<> &builder, llvm::Instruction *nativeWord) const;
	void setAllData(llvm::IRBuilder<> &builder,
			StreamChannelWordValue data) const;
	llvm::LoadInst* getVarValue(llvm::IRBuilder<> &builder,
			llvm::AllocaInst *var) const;
	StreamChannelWordValue getAllData(llvm::IRBuilder<> &builder) const;
	// get number of bus words required to transfer "width" number of bits with specified offset
	size_t _getBusWordCntForChunk(size_t offset, size_t width) const;
	std::pair<size_t, size_t> _resolveMinMaxWordCount(
			std::vector<size_t> possibleOffsets, size_t chunkWidth) const;
	void createCommonVars(llvm::IRBuilder<> &builder);
	void createWDataPendingVar(llvm::IRBuilder<> &builder);
};

// :param GeneratedAllocas: a vector of generated alloca instructions which is used in StreamChannelProps constructor
//                          it is not modified in this function
// :param ioFilter: an argument pointer which can be set to collect StreamChannelProps only for selected IO
std::vector<StreamChannelProps> getStreamIoProps(llvm::Function &F,
		llvm::SmallVector<llvm::AllocaInst*> &GeneratedAllocas, llvm::Argument *ioFilter=nullptr);
}
