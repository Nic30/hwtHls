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

/**
 * Similar functionality as llvm::CodeExtractor
 * but it does not replace code with call but it uses channel
 * communication to pass arguments and to assert synchronization.
 * :note: This transformation should be applied after every other optimization.
 *        Because channel communication makes inter-procedural analysis significantly harder.
 * * Extracted section is replaced with volatile load/store to a newly generated IO function arguments
 *   * Hierarchy of thread channel communication is always flat (inter-thread connections are done on top level)
 *   * Info about about how channels are connected is stored in metadata of module.
 * * Extracted section become infinite loop which reads inputs and write outputs.
 *   * if begin may be asynchronous and there is no input the extracted thread immediately starts execution
 *     and is stalled only by backpressure.
 *   * if end may be asynchronous and there are no outputs (this implies also a single exit point)
 *     the parent thread does not wait for anything from extracted thread and continues immediately after extracted section.
 *   * if begin/end may not be asynchronous but it is, dummy 1b channel is added to assert synchronization.
 *
 *  Simplified call graph (version for llvm-18):
 *   * extractCodeRegion
 *     * _calculateNewEntryFreq
 *     * _discardIncompatibleAssumes
 *     * _collectExitBlocks
 *     * severSplitPHINodesOfEntry
 *     * severSplitPHINodesOfExits
 *     * create codeReplacerBB, newFuncRootBB
 *     * _tryToFindOriginalCodeLocOfInitialBranch
 *     * constructFunction
 *       * resolve types of in/out
 *       * Function::Create
 *       * _constructFunction_UpdateInputUsesToUseNewArgs
 *       * _constructFunction_UpdateOutputUsesToUseNewArgs
 *     * emitCallAndSwitchStatement
 *       * alloca for in/out
 *       * store to inputs
 *       * CallInst::Create
 *       * load from outputs
 *       * switch for return in oldFunction
 *       * return
 *     * moveCodeToFunction
 *     * _updateBlocksForPhisInEntryAndExit
 *
 *  Simplified call graph (version for llvm-21):
 *   * extractCodeRegion
 *      * normalizeCFGForExtraction
 *        * splitReturnBlocks
 *        * severSplitPHINodesOfEntry
 *        * computeExtractedFuncRetVals
 *        * severSplitPHINodesOfExits
 *      * findInputsOutputs
 *      * constructFunctionDeclaration // after this all tmp allocas and metadata are prepared
 *      * emitFunctionBody // after this all loads/stores/extract/concat in newFunction are prepared
 *        * sinking, in loads,
 *        * moveCodeToFunction
 *        * use newFunction inputs in newFunction body,  return
 *        * update header phis, out stores,
 *      * emitReplacerCall // after this all loads/stores/extract/concat in oldFunction are prepared
 *        * allocas for in/out
 *        * switch for return in oldFunction
 *      * insertReplacerCall // after this the newly created CallInst is removed
 *        * replace uses of out, header, and extracted functions
 */
class HwtHlsCodeExtractor: public hwtHls::llvmSrc::CodeExtractor {
public:
	bool AggregateInputs;
	bool AggregateOutputs;
	bool beginMayBeAsync;
	bool endMayBeAsync;
	unsigned inputBufferCapacity;
	unsigned outputBufferCapacity;
	ValueSet ExcludeArgsFromAggregate;
	bool extractedIsInLoop;
	llvm::SmallVector<HwtHlsIoMetadata> newFnHwtHlsIoMD;
	llvm::SmallVector<ArgToAddToParentFn> &argsToAddToParentFn;
	size_t newParentArgIndexOffseet; // F.args_size() + argsToAddToParentFn.size() at begin
	llvm::FreezeInst *beginSyncFreeze;
	llvm::FreezeInst *endSyncFreeze;
	llvm::FreezeInst *returnValFreeze;
	// arg values which will be concatenated together to create 1 arg
	llvm::SetVector<llvm::Value*> StructInValues;
	llvm::SetVector<llvm::Value*> StructOutValues;

	// :see: CodeExtractor::CodeExtractor
	HwtHlsCodeExtractor(llvm::ArrayRef<llvm::BasicBlock*> BBs, //
			llvm::SmallVector<ArgToAddToParentFn> &argsToAddToParentFn,      //
			bool extractedIsInLoop,                     //
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
	std::string _getNewFunctionName(llvm::Function &oldFunction,
			llvm::BasicBlock &header);
	llvm::Function* constructFunctionDeclaration(const ValueSet &inputs,
			const ValueSet &outputs, llvm::BlockFrequency EntryFreq,
			const llvm::Twine &Name, ValueSet &StructValues,
			llvm::StructType *&StructTy) override;
	void _emitFunctionBody_UpdateInputUsesToUseNewArgs(
			llvm::IRBuilder<> &Builder, llvm::Function *newFunction,
			const ValueSet &inputs, const ValueSet &StructInValues,
			llvm::SmallVectorImpl<llvm::Value*> &NewValues);
	void _emitFunctionBody_constructOutStores(
			llvm::IRBuilder<> &Builder, llvm::Function *newFunction, const ValueSet &outputs,
			const ValueSet &StructOutValues,
			llvm::Function::arg_iterator ScalarOutArgIt);
	void emitFunctionBody(const ValueSet &inputs,
			const ValueSet &outputs, const ValueSet &StructValues,
			llvm::Function *newFunction, llvm::StructType *StructArgTy,
			llvm::BasicBlock *header, const ValueSet &SinkingCands,
			llvm::SmallVectorImpl<llvm::Value*> &NewValues) override;

	llvm::CallInst *emitReplacerCall(
	    const ValueSet &inputs, const ValueSet &outputs,
	    const ValueSet &StructValues, llvm::Function *newFunction,
		llvm::StructType *StructArgTy, llvm::Function *oldFunction, llvm::BasicBlock *ReplIP,
		llvm::BlockFrequency EntryFreq, llvm::ArrayRef<llvm::Value *> LifetimesStart,
	    std::vector<llvm::Value *> &Reloads) override;

	void _discardAggragationIfJustOneInOrOut(const ValueSet &inputs,
			const ValueSet &outputs);

	void _constructFunctionDeclaration_AssignNamesToNewArgs(
			llvm::Function *newFunction,
			const std::vector<llvm::Type*> &ParamTy, const ValueSet &inputs,
			const ValueSet &outputs, const ValueSet &StructInValues,
			const ValueSet &StructOutValues, llvm::Type *AggregatedInTy,
			llvm::Type *AggregatedOutTy);

	// in the case that the extracted does not have any inputs and sync of
	// begin is required add dummy 1b variable to assert the synchronization with the parent
	// and similarly for the end and outputs
	llvm::Type* _addVariablesToAssertBeginAndEndSyncIfNecessary(
			ValueSet &inputs, ValueSet &outputs, llvm::Type *RetTy);

	void insertReplacerCall(
	    llvm::Function *oldFunction, llvm::BasicBlock *header, llvm::BasicBlock *codeReplacer,
	    const ValueSet &outputs, llvm::ArrayRef<llvm::Value *> Reloads,
	    const llvm::DenseMap<llvm::BasicBlock *, llvm::BlockFrequency> &ExitWeights) override;
	void wrapExtractedInInfLoop(llvm::Function *newFunction);
	void deleteCallInst(llvm::Function *newFunction);

	using hwtHls::llvmSrc::CodeExtractor::extractCodeRegion;
	void deleteTmpValues();
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
			const llvm::CodeExtractorAnalysisCache &CEAC,
			ValueSet &Inputs, ValueSet &Outputs) override;
};

}
