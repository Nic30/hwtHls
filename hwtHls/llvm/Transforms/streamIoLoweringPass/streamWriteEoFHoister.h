#pragma once
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoInstrCollector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>

namespace llvm {
class DominatorTree;
class PostDominatorTree;
class DependenceInfo;
}

namespace hwtHls {

class StreamWriteEoFHoister {
public:
	struct StreamEoFReachInfo {
		bool mayBeEof;
		bool mayBeNotEof;

		StreamEoFReachInfo() :
				mayBeEof(false), mayBeNotEof(false)
		{
		}
	};

	const StreamChannelProps &streamProps;
	StreamIoDetector &cfg;
	// key is block and flag which is true if the record is for block from beginning
	// this may be false only for a block where original start write pseudo instruction was
	// for this block we must start from the position of the original write
	// and then we may then re-discover this block from the beginning
	// :note: AllInfos is always build new for every write
	std::map<std::pair<llvm::BasicBlock*, bool>,
			std::unique_ptr<StreamEoFReachInfo>> AllInfos;

	llvm::DominatorTree &DT;
	const llvm::PostDominatorTree &PDT;
	llvm::DependenceInfo &DI;

	StreamWriteEoFHoister(const StreamChannelProps &streamProps,
			StreamIoDetector &cfg, llvm::DominatorTree &DT,
			const llvm::PostDominatorTree &PDT, llvm::DependenceInfo &DI);
	void prepareLastExpressionForWrites();
protected:
	/*
	 :returns: True if the EOF (HlsStmWriteEndOfFrame) is only successor, False if EOF is not a successor, None if EOF is not only successor.
	 */
	//std::optional<bool> _isLastWrite(
	//		const StreamIoDetector::HlsReadOrWrite *instr);
	//llvm::Value* _tryToGetConditionToEnableEoF(
	//		/*Union[HlsStmWriteStartOfFrame, HlsStmWriteAxiStream]*/const StreamIoDetector::HlsReadOrWrite *curWrite);
	std::pair<llvm::Value*, std::optional<bool>> prepareEoFCondition(
			llvm::IRBuilder<> &Builder, llvm::Instruction *MovePos,
			llvm::BasicBlock *curBlock);

	/*
	 * :return: tuple isEoFCond, isEoFValue (value is valid only if isEoFCond==nullptr)
	 * */
	std::pair<llvm::Value*, bool> _prepareEoFCondition(
			llvm::IRBuilder<> &Builder, llvm::Instruction *MovePos,
			llvm::BasicBlock *curBlock, bool fromBlockBeginning);
	/**
	 * In the first phase of the search for EoF trigger we have to just analyze following blocks
	 * and search for EoF pseudo instructions. This is done by this function.
	 * :param allInfos: a map used to resolve record for a block and for the deallocation
	 *
	 * :note: returns nullptr if the block ends with UnreachableInst
	 * */
	StreamEoFReachInfo* _tryToGetConditionToEnableEoFProbe(
			llvm::BasicBlock &curBlock, llvm::BasicBlock::iterator blockIt);
};

}
