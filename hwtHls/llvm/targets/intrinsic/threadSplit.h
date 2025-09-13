#pragma once
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

namespace llvm {
class LoopInfo;
class DomTreeUpdater;
}

namespace hwtHls {

extern const std::string ThreadSplitBeginName;
llvm::CallInst* CreateThreadSplitBegin(llvm::IRBuilderBase &Builder,
		const std::string &name, llvm::MDNode *md);

extern const std::string ThreadSplitEndName;
llvm::CallInst* CreateThreadSplitEnd(llvm::IRBuilderBase &Builder,
		const std::string &name, llvm::MDNode *md);

bool IsThreadSplitBeginInst(const llvm::Instruction *I);
bool IsThreadSplitBegin(const llvm::CallInst *C);
bool IsThreadSplitBegin(const llvm::Function *F);
bool IsThreadSplitEnd(const llvm::CallInst *C);
bool IsThreadSplitEnd(const llvm::Function *F);

// get name of section from function name
std::string ThreadSplitBeginGetName(const llvm::Function *F);

class ThreadSplitSectionMetadata {
public:
	std::string name;
	bool aggregateInputs;
	bool beginMayBeAsync;
	bool aggregateOutputs;
	bool endMayBeAsync;
	size_t inputBufferCapacity;
	size_t outputBufferCapacity;

	ThreadSplitSectionMetadata() :
			aggregateInputs(false), beginMayBeAsync(false), aggregateOutputs(
					false), endMayBeAsync(false), inputBufferCapacity(0), outputBufferCapacity(
					1) {
	}
	ThreadSplitSectionMetadata(std::string name, bool aggregateInputs,
			bool beginMayBeAsync, bool aggregateOutputs, bool endMayBeAsync,
			size_t inputBufferCapacity, size_t outputBufferCapacity) :
			name(name), aggregateInputs(aggregateInputs), beginMayBeAsync(
					beginMayBeAsync), aggregateOutputs(aggregateOutputs), endMayBeAsync(
					endMayBeAsync), inputBufferCapacity(inputBufferCapacity), outputBufferCapacity(
					outputBufferCapacity) {
	}
	static const std::string METADATA_NAME;
	llvm::MDNode* toMetadata(llvm::LLVMContext &Ctx) const;
	static ThreadSplitSectionMetadata fromMetadata(llvm::MDNode &MD);
};
/*
 * :attention: currently supports section with a single entrypoint an potentially multiple exit points
 *
 * :param firstThreadSplit: the first threadSplit intrinsic of this section which was found
 * :param Blocks: blocks to extract, the first one is only entrypoint, the last one is only exit point
 * */
ThreadSplitSectionMetadata ThreadSplitGetSeparatedSection(
		llvm::DomTreeUpdater &DTU, llvm::LoopInfo &LI,
		llvm::CallInst &firstThreadSplit,
		llvm::SmallVector<llvm::BasicBlock*> &Blocks);

}
