#pragma once

#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/ADT/SetVector.h>

#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>

#include <hwtHls/llvm/llvmSrc/CodeExtractor.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractorIoArgUtils.h>

namespace hwtHls {

// Similar functionality as llvm::CodeExtractor
// but it does not replace code with call but it uses channel
// communication to pass arguments and to assert synchronization.
// :note: This transformation should be applied after every other optimization.
//        Because channel communication makes inter-procedural analysis significantly harder.
// * Extracted section is replaced with volatile load/store to a newly generated IO function arguments
//   * Hierarchy of thread channel communication is always flat (inter-thread connections are done on top level)
//   * Info about about how channels are connected is stored in metadata of module.
// * Extracted section become infinite loop which reads inputs and write outputs.
//   * if begin may be asynchronous and there is no input the extracted thread immediately starts execution
//     and is stalled only by backpressure.
//   * if end may be asynchronous and there are no outputs (this implies also a single exit point)
//     the parent thread does not wait for anything from extracted thread and continues immediately after extracted section.
//   * if begin/end may not be asynchronous but it is, dummy 1b channel is added to assert synchronization.
class HwtHlsCodeExtractor: public hwtHls::CodeExtractor {
public:
	bool AggregateInputs;
	bool AggregateOutputs;
	bool beginMayBeAsync;
	bool endMayBeAsync;
	unsigned inputBufferCapacity;
	unsigned outputBufferCapacity;
	// :see: CodeExtractor::CodeExtractor
	HwtHlsCodeExtractor(llvm::ArrayRef<llvm::BasicBlock*> BBs,      //
			llvm::DominatorTree *DT = nullptr,          //
			bool beginMayBeAsync = false,               //
			bool AggregateInputs = false,               //
			bool endMayBeAsync = false,                 //
			bool AggregateOutputs = false,              //
			unsigned inputBufferCapacity = 0,           //
			unsigned outputBufferCapacity = 0,          //
			llvm::BlockFrequencyInfo *BFI = nullptr,    //
			llvm::BranchProbabilityInfo *BPI = nullptr, //
			llvm::AssumptionCache *AC = nullptr,        //
			llvm::BasicBlock *AllocationBlock = nullptr,        //
			std::string Suffix = "");
	void findInputsOutputs(ValueSet &Inputs, ValueSet &Outputs,
			const ValueSet &Allocas) const;

	std::string _getNewFunctionName(Function &oldFunction, BasicBlock &header);
	BlockFrequency _calculateNewEntryFreq(BasicBlock *header);
	void _discardIncompatibleAssumes();
	llvm::SmallPtrSet<llvm::BasicBlock*, 1> _collectExitBlocks(
			llvm::SmallPtrSet<llvm::BasicBlock*, 1> &ExitBlocks,
			llvm::DenseMap<llvm::BasicBlock*, llvm::BlockFrequency> &ExitWeights,
			llvm::SetVector<BasicBlock*> &ExitingBlocks);
	std::pair<Function*, SmallVector<HwtHlsIoMetadata>> constructFunction(
			const ValueSet &inputs, const ValueSet &outputs,
			llvm::BasicBlock *header, llvm::BasicBlock *newRootNode,
			llvm::BasicBlock *newHeader,
			const llvm::SetVector<BasicBlock*> &ExitingBlocks,
			llvm::Function *oldFunction,
			SmallVector<ArgToAddToParentFn> &argsToAddToParentFn,
			llvm::Module *M);
	void _constructFunction_UpdateInputUsesToUseNewArgs(
			llvm::IRBuilder<> &Builder, llvm::Function *newFunction,
			const ValueSet &inputs, const ValueSet &StructInValues,
			llvm::Type *AggregatedInTy,
			llvm::Function::arg_iterator ScalarArgIt,
			llvm::Function::arg_iterator AggregatedInArgIt);
	void _constructFunction_UpdateOutputUsesToUseNewArgs(
			llvm::IRBuilder<> &Builder, llvm::Function *newFunction,
			const ValueSet &outputs, const ValueSet &StructOutValues,
			llvm::Type *AggregatedOutTy,
			const llvm::SetVector<BasicBlock*> &ExitingBlocks,
			llvm::Function::arg_iterator ScalarOutArgIt,
			llvm::Function::arg_iterator AggregatedOutArgIt);
	void _constructFunction_AssignNamesToNewArgs(llvm::Function *newFunction,
			const std::vector<llvm::Type*> &ParamTy, const ValueSet &inputs,
			const ValueSet &outputs, const ValueSet &StructInValues,
			const ValueSet &StructOutValues, llvm::Type *AggregatedInTy,
			llvm::Type *AggregatedOutTy);
	void _updateNewEntryFreq(BlockFrequency EntryFreq, Function *newFunction,
			BasicBlock *codeReplacer);
	void _tryToFindOriginalCodeLocOfInitialBranch(llvm::Function *oldFunction,
			llvm::Instruction *BranchI);
	ValueSet _sinkAndHoistCodeFromRegion(
			const hwtHls::CodeExtractorAnalysisCache &CEAC, ValueSet &inputs,
			ValueSet &outputs, llvm::BasicBlock *newFuncRoot);
	void _updateBlocksForPhisInEntryAndExit(llvm::BasicBlock *header,
			llvm::BasicBlock *newFuncRoot,
			llvm::SmallPtrSet<llvm::BasicBlock*, 1> &ExitBlocks,
			llvm::BasicBlock *codeReplacer);
	void _useVolatileForAccessToArgAllocas(llvm::CallInst &TheCall) const;
	//void _handleNewArgumentsOfOldAndNewFn(Function &oldFunction,
	//		Function &newFunction, ValueSet &inputs, ValueSet &outputs,
	//		SmallVector<ArgToAddToParentFn> &argsToAddToParentFn);

	CallInst* emitCallAndSwitchStatement(llvm::Function *newFunction,
			llvm::BasicBlock *codeReplacer, ValueSet &inputs, ValueSet &outputs,
			llvm::SetVector<BasicBlock*> &ExitingBlocks,
			llvm::MutableArrayRef<HwtHlsIoMetadata> newFnHwtHlsIoMD,
			llvm::MutableArrayRef<ArgToAddToParentFn> argsToAddToParentFn);
	void _addVariablesToAssertBeginAndEndSyncIfNecessary(IRBuilder<> &Builder,
			Function *oldFunction, BasicBlock *header,
			BasicBlock *codeReplacerBB, ValueSet &inputs, ValueSet &outputs);
	/// Perform the extraction, returning the new function and providing an
	/// interface to see what was categorized as inputs and outputs.
	///
	/// \param CEAC - Cache to speed up operations for the CodeExtractor when
	/// hoisting, and extracting lifetime values and assumes.
	/// \param Inputs [out] - filled with  values marked as inputs to the
	/// newly outlined function.
	/// \param Outputs [out] - filled with values marked as outputs to the
	/// newly outlined function.
	llvm::Function* extractCodeRegion(
			const hwtHls::CodeExtractorAnalysisCache &CEAC,
			bool extractedIsInLoop, ValueSet &Inputs, ValueSet &Outputs,
			SmallVector<ArgToAddToParentFn> &argsToAddToParentFn);
	void _finalDebugChecks(llvm::Function *oldFunction,
			llvm::Function *newFunction);
};

}
