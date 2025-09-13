#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/BlockFrequencyInfo.h>
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/functionMutating.h>

using namespace llvm;
using ProfileCount = Function::ProfileCount;

#define DEBUG_TYPE "hwtHls::ThreadExtractor"

namespace hwtHls {

// :see: CodeExtractor::CodeExtractor
HwtHlsCodeExtractor::HwtHlsCodeExtractor(llvm::ArrayRef<llvm::BasicBlock*> BBs, //
		llvm::DominatorTree *DT,          //
		bool beginMayBeAsync,             //
		bool AggregateInputs,             //
		bool endMayBeAsync,               //
		bool AggregateOutputs,            //
		unsigned inputBufferCapacity,     //
		unsigned outputBufferCapacity,    //
		llvm::BlockFrequencyInfo *BFI,    //
		llvm::BranchProbabilityInfo *BPI, //
		llvm::AssumptionCache *AC,        //
		llvm::BasicBlock *AllocationBlock,        //
		std::string Suffix) :
		hwtHls::CodeExtractor(BBs, DT, /*AggregateArgs*/
		AggregateInputs || AggregateOutputs, BFI, BPI, AC, AllowVarArgs, /*AllowAlloca*/
		true, AllocationBlock, Suffix, /*ArgsInZeroAddressSpace*/
		false), AggregateInputs(AggregateInputs), AggregateOutputs(
				AggregateOutputs), beginMayBeAsync(beginMayBeAsync), endMayBeAsync(
				endMayBeAsync), inputBufferCapacity(inputBufferCapacity), outputBufferCapacity(
				outputBufferCapacity) {
}
void HwtHlsCodeExtractor::findInputsOutputs(ValueSet &Inputs, ValueSet &Outputs,
		const ValueSet &Allocas) const {
	CodeExtractor::findInputsOutputs(Inputs, Outputs, Allocas);
}

std::string HwtHlsCodeExtractor::_getNewFunctionName(Function &oldFunction,
		BasicBlock &header) {
	std::string SuffixToUse =
			Suffix.empty() ?
					(header.getName().empty() ?
							"threadSplit" : header.getName().str()) :
					Suffix;
	return (oldFunction.getName() + "." + SuffixToUse).str();
}

/// constructFunction - make a function based on inputs and outputs, as follows:
/// f(in0, ..., inN, out0, ..., outN)
// :note: this expects all GEPs, Alloca, loops and private var to be sinked into extracted region
std::pair<Function*, SmallVector<HwtHlsIoMetadata>> HwtHlsCodeExtractor::constructFunction(
		const ValueSet &inputs, const ValueSet &outputs, BasicBlock *header,
		BasicBlock *newRootNode, BasicBlock *newHeader,
		const llvm::SetVector<BasicBlock*> &ExitingBlocks,
		Function *oldFunction,
		SmallVector<ArgToAddToParentFn> &argsToAddToParentFn, Module *M) {
	LLVM_DEBUG(dbgs() << "inputs: " << inputs.size() << "\n");
	LLVM_DEBUG(dbgs() << "outputs: " << outputs.size() << "\n");
	assert(argsToAddToParentFn.size() == 0);

	// This function returns unsigned, outputs will go back by reference.
	if (NumExitBlocks > 1) {
		llvm_unreachable("NotImplemented - add param to signalize exit block");
	}
	RetTy = Type::getVoidTy(header->getContext());

	std::vector<Type*> ParamTy; // types of parameters for new function
	std::vector<Type*> AggInParamTy; // types of input parameters which will be concatenated together
	std::vector<Type*> AggOutParamTy;
	ValueSet StructInValues;
	ValueSet StructOutValues;
	//const DataLayout &DL = M->getDataLayout();
	auto oldFnHwtHlsIoMD = HwtHlsIoMetadata_get(*oldFunction);
	SmallVector<HwtHlsIoMetadata> newFnHwtHlsIoMD;
	// pre-fill dummy metadata

	auto prefillMetadata = [&newFnHwtHlsIoMD, &argsToAddToParentFn,
			this](IODirection dirForNewFn,
			size_t width, AllocaInst *tmpAlloca) {
		auto isIn = dirForNewFn == IODirection::IO_DIR_IN;
		newFnHwtHlsIoMD.push_back(
				HwtHlsIoMetadata(dirForNewFn, 0, isIn ? width : 0,
						isIn ? 0 : width, true, nullptr, 0,
						isIn ? 0 : outputBufferCapacity, nullptr, nullptr,
						nullptr, nullptr, nullptr)); // connection should be initialized later in emitCallAndSwitchStatement()
		argsToAddToParentFn.push_back(
				{ tmpAlloca, HwtHlsIoMetadata(IODirection_reverse(dirForNewFn),
						0, isIn ? 0 : width, isIn ? width : 0, true, nullptr, 0,
						isIn ? inputBufferCapacity : 0, nullptr, nullptr,
						nullptr, nullptr, nullptr) }); // connection should be initialized later in emitCallAndSwitchStatement()

	};

	// Add the types of the input values to the function's argument list
	for (Value *value : inputs) {
		LLVM_DEBUG(dbgs() << "value used in func: " << *value << "\n");
		auto addrSpace = ParamTy.size();
		if (isa<Argument>(value) || isa<PointerType>(value->getType())) {
			// this will be just pointer representing HwIO of parent function
			// if there is no use left in parent function the argument will be removed from parent fn.
			// else it will be shared between parent and this function and interconnect will have
			// to be instantiated later
			if (auto a = dyn_cast<Argument>(value)) {
				newFnHwtHlsIoMD.push_back(oldFnHwtHlsIoMD[a->getArgNo()]);
			} else {
				auto tmpAlloca = dyn_cast<AllocaInst>(value);
				size_t width =
						tmpAlloca->getAllocatedType()->getIntegerBitWidth();
				assert(tmpAlloca);
				prefillMetadata(IODirection::IO_DIR_IN, width, tmpAlloca);
			}
			ParamTy.push_back(PointerType::get(value->getContext(), addrSpace));
		} else if (isa<GetElementPtrInst>(value)) {
			llvm_unreachable(
					"GetElementPtrInst should be already sinked into extracted region");
		} else if (AggregateInputs
				&& !ExcludeArgsFromAggregate.contains(value)) {
			// stack input type to input aggregated struct
			assert(!isa<PointerType>(value->getType()));
			AggInParamTy.push_back(value->getType());
			StructInValues.insert(value);
		} else {
			size_t width = value->getType()->getScalarSizeInBits();
			prefillMetadata(IODirection::IO_DIR_IN, width, nullptr);
			ParamTy.push_back(PointerType::get(value->getContext(), addrSpace));
		}
	}
	assert(
			(ParamTy.size() + AggInParamTy.size() == inputs.size())
					&& "Number of scalar and aggregate params does not match inputs, outputs");
	size_t AggregatedInArgIndex = ParamTy.size();
	IntegerType *AggregatedInTy = nullptr;
	// :note: arguments can be of IntegerType or PointerType, pointers represent
	//  channels and are excluded from aggregation
	if (AggregateInputs && !AggInParamTy.empty()) {
		size_t aggregatedWidth = 0;
		for (auto t : AggInParamTy)
			aggregatedWidth += t->getIntegerBitWidth();
		AggregatedInTy = IntegerType::get(M->getContext(), aggregatedWidth);
		auto addrSpace = ParamTy.size();
		ParamTy.push_back(PointerType::get(AggregatedInTy, addrSpace));
		prefillMetadata(IODirection::IO_DIR_IN, aggregatedWidth, nullptr);
	}

	// Add the types of the output values to the function's argument list.
	for (Value *output : outputs) {
		LLVM_DEBUG(dbgs() << "instr used in func: " << *output << "\n");
		auto addrSpace = ParamTy.size();
		assert(!isa<Argument>(output)); // output pointers are input value (because the address is the input)
		if (AggregateOutputs && !ExcludeArgsFromAggregate.contains(output)) {
			if (isa<PointerType>(output->getType())) {
				assert(isa<AllocaInst>(output));
				ParamTy.push_back(
						PointerType::get(output->getType(), addrSpace));
			} else {
				AggOutParamTy.push_back(output->getType());
				StructOutValues.insert(output);
			}
		} else {
			size_t width = output->getType()->getScalarSizeInBits();
			prefillMetadata(IODirection::IO_DIR_OUT, width, nullptr);
			ParamTy.push_back(PointerType::get(output->getType(), addrSpace));
		}
	}
	assert(
			(ParamTy.size() + AggInParamTy.size() + AggOutParamTy.size())
					== (inputs.size() + outputs.size()
							+ int(bool(AggregatedInTy)))
					&& "Number of scalar and aggregate params does not match inputs, outputs");

	assert(
			(StructInValues.empty() || AggregateInputs)
					&& "Expected StructValues only with AggregateArgs set");
	assert(
			(StructOutValues.empty() || AggregateOutputs)
					&& "Expected StructValues only with AggregateArgs set");

	// Concatenate scalar and aggregate params in ParamTy.
	IntegerType *AggregatedOutTy = nullptr;
	if (AggregateOutputs && !AggOutParamTy.empty()) {
		size_t aggregatedWidth = 0;
		for (auto t : AggOutParamTy)
			aggregatedWidth += t->getIntegerBitWidth();
		AggregatedOutTy = IntegerType::get(M->getContext(), aggregatedWidth);
		auto addrSpace = ParamTy.size();
		ParamTy.push_back(PointerType::get(AggregatedOutTy, addrSpace));
		prefillMetadata(IODirection::IO_DIR_OUT, aggregatedWidth, nullptr);
	}

	LLVM_DEBUG( {
		dbgs() << "Function type: " << *RetTy << " f("
		;
		for (Type *i : ParamTy)
			dbgs() << *i << ", "
			;
		dbgs() << ")\n"
		;
	}
	);

	FunctionType *funcType = FunctionType::get(RetTy, ParamTy,
			AllowVarArgs && oldFunction->isVarArg());

	std::string SuffixToUse =
			Suffix.empty() ?
					(header->getName().empty() ?
							"threadSplit" : header->getName().str()) :
					Suffix;
	auto newFnName = _getNewFunctionName(*oldFunction, *header);
	// Create the new function
	Function *newFunction = Function::Create(funcType,
			GlobalValue::InternalLinkage, oldFunction->getAddressSpace(),
			newFnName, M);
	constructFunctionInheritAttributes(oldFunction, newFunction);
	newFunction->insert(newFunction->end(), newRootNode);
	assert(
			AggInParamTy.size() != 1
					&& "AggregateInputs should be set to 0 then");
	assert(
			AggOutParamTy.size() != 1
					&& "AggregateOutputs should be set to 0 then");
	{
		IRBuilder<> Builder(oldFunction->getContext());
		// Create scalar and aggregate iterators to name all of the arguments we
		// inserted.
		Function::arg_iterator ScalarArgIt = newFunction->arg_begin();
		Function::arg_iterator AggregatedInArgIt = std::next(ScalarArgIt,
				AggregatedInArgIndex);

		_constructFunction_UpdateInputUsesToUseNewArgs(Builder, newFunction,
				inputs, StructInValues, AggregatedInTy, ScalarArgIt,
				AggregatedInArgIt);
		Function::arg_iterator ScalarOutArgIt = std::next(AggregatedInArgIt,
				StructInValues.empty() ? 0 : 1);
		Function::arg_iterator AggregatedOutArgIt = std::next(ScalarOutArgIt,
				outputs.size() - StructOutValues.size());
		_constructFunction_UpdateOutputUsesToUseNewArgs(Builder, newFunction,
				outputs, StructOutValues, AggregatedOutTy, ExitingBlocks,
				ScalarOutArgIt, AggregatedOutArgIt);
	}
	_constructFunction_AssignNamesToNewArgs(newFunction, ParamTy, inputs,
			outputs, StructInValues, StructOutValues, AggregatedInTy,
			AggregatedOutTy);
	// Rewrite branches to basic blocks outside of the loop to new dummy blocks
	// within the new function. This must be done before we lose track of which
	// blocks were originally in the code region.
	std::vector<User*> Users(header->user_begin(), header->user_end());
	for (auto &U : Users)
		// The BasicBlock which contains the branch is not in the region
		// modify the branch target to a new block
		if (Instruction *I = dyn_cast<Instruction>(U))
			if (I->isTerminator() && I->getFunction() == oldFunction
					&& !Blocks.count(I->getParent()))
				I->replaceUsesOfWith(header, newHeader);

	std::vector<std::size_t> newArgOrder;
	for (size_t i = 0; i < newFunction->arg_size(); i++) {
		newArgOrder.push_back(i);
	}
	newFunction = mutateFunctionShuffleArgs(*newFunction, newArgOrder);
	// update newly added args to parent function to be connected to new thread function
	for (size_t i = 0; i < argsToAddToParentFn.size(); ++i) {
		argsToAddToParentFn[i].metadata.otherThreadFn = newFunction;
	}
	return {newFunction, newFnHwtHlsIoMD};
}

void HwtHlsCodeExtractor::_constructFunction_UpdateInputUsesToUseNewArgs(
		IRBuilder<> &Builder, Function *newFunction, const ValueSet &inputs,
		const ValueSet &StructInValues, Type *AggregatedInTy,
		Function::arg_iterator ScalarArgIt,
		Function::arg_iterator AggregatedInArgIt) {
	// Rewrite all users of inputs in the extracted region to use the
	// arguments (or appropriate addressing into struct) instead.
	size_t aggregatedInBitOffset = 0;
	LoadInst *AggregatedInLd = nullptr;
	for (unsigned i = 0, e = inputs.size(); i != e; ++i) {
		Value *RewriteVal;
		auto &Inp = *inputs[i];
		Value *parentLocalValue = dyn_cast<Argument>(&Inp);
		if (!parentLocalValue) {
			parentLocalValue = dyn_cast<AllocaInst>(&Inp);
		}
		if (parentLocalValue) {
			std::function<bool(llvm::User*)> isUserInsideOfExtractedSection = [
					Blocks=&Blocks](User *u) -> bool {
				if (Instruction *inst = dyn_cast<Instruction>(u))
					return static_cast<bool>(Blocks->count(inst->getParent()));
				return false;
			};
			replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace(Builder,
					*parentLocalValue, *ScalarArgIt,
					&isUserInsideOfExtractedSection);
			++ScalarArgIt;
			continue;
		}
		assert(!Inp.getType()->isPointerTy());
		Instruction *TI = newFunction->begin()->getTerminator();
		size_t width = Inp.getType()->getIntegerBitWidth();
		Builder.SetInsertPoint(TI);
		if (AggregateInputs && StructInValues.contains(&Inp)) {
			if (!AggregatedInLd) {
				AggregatedInLd = Builder.CreateLoad(AggregatedInTy,
						&*AggregatedInArgIt, true, Inp.getName());
			}
			RewriteVal = CreateBitRangeGetConst(&Builder, AggregatedInLd,
					aggregatedInBitOffset, width, "");
			aggregatedInBitOffset += width;
		} else {
			RewriteVal = Builder.CreateLoad(Inp.getType(), &*ScalarArgIt, true,
					Inp.getName());
			++ScalarArgIt;
		}
		std::vector<User*> Users(Inp.user_begin(), Inp.user_end());
		for (User *use : Users)
			if (Instruction *inst = dyn_cast<Instruction>(use))
				if (Blocks.count(inst->getParent()))
					inst->replaceUsesOfWith(inputs[i], RewriteVal);
	}
}

void HwtHlsCodeExtractor::_constructFunction_UpdateOutputUsesToUseNewArgs(
		IRBuilder<> &Builder, Function *newFunction, const ValueSet &outputs,
		const ValueSet &StructOutValues, Type *AggregatedOutTy,
		const llvm::SetVector<BasicBlock*> &ExitingBlocks,
		Function::arg_iterator ScalarOutArgIt,
		Function::arg_iterator AggregatedOutArgIt) {
	// Create stores to arguments representing outputs from this newFunction
	SmallVector<Value*> aggregatedOutputValues;
	for (unsigned i = 0, e = outputs.size(); i != e; ++i) {
		auto &Out = *outputs[i];
		Value *parentLocalValue = dyn_cast<Argument>(&Out);
		if (!parentLocalValue) {
			parentLocalValue = dyn_cast<AllocaInst>(&Out);
		}

		if (parentLocalValue) {
			std::function<bool(llvm::User*)> isUserInsideOfExtractedSection = [
					Blocks=&Blocks](User *u) -> bool {
				if (Instruction *inst = dyn_cast<Instruction>(u))
					return static_cast<bool>(Blocks->count(inst->getParent()));
				return false;
			};
			replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace(Builder,
					*parentLocalValue, *ScalarOutArgIt,
					&isUserInsideOfExtractedSection);
			++ScalarOutArgIt;
			continue;
		}
		assert(!Out.getType()->isPointerTy());
		Instruction *TI = newFunction->begin()->getTerminator();
		Builder.SetInsertPoint(TI);
		if (AggregateOutputs && StructOutValues.contains(&Out)) {
			assert(
					AggregatedOutArgIt != newFunction->arg_end()
							&& "Number of aggregate output arguments should match "
									"the number of defined values");
			aggregatedOutputValues.push_back(&Out);
		} else {
			// Store the arguments right after the definition of output value.
			// This should be proceeded after creating exit stubs to be ensure that invoke
			// result restore will be placed in the outlined function.
			assert(
					ScalarOutArgIt != newFunction->arg_end()
							&& "Number of scalar output arguments should match "
									"the number of defined values");
			auto *OutI = dyn_cast<Instruction>(&Out);
			assert(OutI);
			if (isa<AllocaInst>(OutI))
				continue; // temporary alloca for output
			// Find proper insertion point.
			BasicBlock::iterator InsertPt;
			// In case OutI is an invoke, we insert the store at the beginning in the
			// 'normal destination' BB. Otherwise we insert the store right after OutI.
			if (auto *InvokeI = dyn_cast<InvokeInst>(OutI))
				InsertPt = InvokeI->getNormalDest()->getFirstInsertionPt();
			else if (auto *Phi = dyn_cast<PHINode>(OutI))
				InsertPt = Phi->getParent()->getFirstInsertionPt();
			else
				InsertPt = std::next(OutI->getIterator());

			Instruction *InsertBefore = &*InsertPt;
			assert(
					(InsertBefore->getFunction() == newFunction
							|| Blocks.count(InsertBefore->getParent()))
							&& "InsertPt should be in new function");
			Builder.SetInsertPoint(InsertPt);
			Builder.CreateStore(&Out, &*ScalarOutArgIt, true);
			++ScalarOutArgIt;
		}
	}
	if (aggregatedOutputValues.size()) {
		assert(
				StructOutValues.size() > 1
						&& "If it was just 1 the AggregateOutputs should have been set to false");
		// store aggregated outputs in latch of extracted functions
		// so outputs are produced after every iteration of thread loop (== after execution of original extracted section)
		// :note: construction in old function, the code will be moved later in moveCodeToFunction()
		for (auto exitingBB : ExitingBlocks) {
			Builder.SetInsertPoint(exitingBB->getTerminator());
			auto outV = CreateBitConcat(&Builder, StructOutValues.getArrayRef(),
					"AggregatedOut.val");
			Builder.CreateStore(outV, &*AggregatedOutArgIt, true);
		}
	}
}

void HwtHlsCodeExtractor::_constructFunction_AssignNamesToNewArgs(
		Function *newFunction, const std::vector<Type*> &ParamTy,
		const ValueSet &inputs, const ValueSet &outputs,
		const ValueSet &StructInValues, const ValueSet &StructOutValues,
		Type *AggregatedInTy, Type *AggregatedOutTy) {
	size_t NumScalarParams = ParamTy.size();
	if (AggregatedInTy)
		--NumScalarParams;
	if (AggregatedOutTy)
		--NumScalarParams;
	// Set names for input and output arguments.
	if (NumScalarParams) {
		auto ScalarArgIt = newFunction->arg_begin();
		for (unsigned i = 0, e = inputs.size(); i != e; ++i) {
			if (!AggregateInputs || !StructInValues.contains(inputs[i])) {
				ScalarArgIt->setName(
						inputs[i]->getName()
								+ (isa<Argument>(inputs[i]) ? "" : ".i"));
				++ScalarArgIt;
			}
		}
		if (AggregatedInTy)
			++ScalarArgIt; // skip input aggregate
		for (unsigned i = 0, e = outputs.size(); i != e; ++i)
			if (!AggregateOutputs || !StructOutValues.contains(outputs[i])) {
				ScalarArgIt->setName(outputs[i]->getName() + ".o");
				++ScalarArgIt;
			}
	}
}

void HwtHlsCodeExtractor::_tryToFindOriginalCodeLocOfInitialBranch(
		Function *oldFunction, Instruction *BranchI) {
	// If the original function has debug info, we have to add a debug location
	// to the new branch instruction from the artificial entry block.
	// We use the debug location of the first instruction in the extracted
	// blocks, as there is no other equivalent line in the source code.
	if (oldFunction->getSubprogram()) {
		any_of(Blocks, [&BranchI](const BasicBlock *BB) {
			return any_of(*BB, [&BranchI](const Instruction &I) {
				if (!I.getDebugLoc())
					return false;
				BranchI->setDebugLoc(I.getDebugLoc());
				return true;
			});
		});
	}
}

void HwtHlsCodeExtractor::_updateBlocksForPhisInEntryAndExit(BasicBlock *header,
		BasicBlock *newFuncRoot, SmallPtrSet<BasicBlock*, 1> &ExitBlocks,
		BasicBlock *codeReplacer) {
	// Loop over all of the PHI nodes in the header and exit blocks, and change
	// any references to the old incoming edge to be the new incoming edge.
	for (BasicBlock::iterator I = header->begin(); isa<PHINode>(I); ++I) {
		PHINode *PN = cast<PHINode>(I);
		for (unsigned i = 0, e = PN->getNumIncomingValues(); i != e; ++i)
			if (!Blocks.count(PN->getIncomingBlock(i)))
				PN->setIncomingBlock(i, newFuncRoot);
	}

	for (BasicBlock *ExitBB : ExitBlocks)
		for (PHINode &PN : ExitBB->phis()) {
			Value *IncomingCodeReplacerVal = nullptr;
			for (unsigned i = 0, e = PN.getNumIncomingValues(); i != e; ++i) {
				// Ignore incoming values from outside of the extracted region.
				if (!Blocks.count(PN.getIncomingBlock(i)))
					continue;

				// Ensure that there is only one incoming value from codeReplacer.
				if (!IncomingCodeReplacerVal) {
					PN.setIncomingBlock(i, codeReplacer);
					IncomingCodeReplacerVal = PN.getIncomingValue(i);
				} else
					assert(
							IncomingCodeReplacerVal == PN.getIncomingValue(i)
									&& "PHI has two incompatible incoming values from codeRepl");
			}
		}
}

HwtHlsCodeExtractor::ValueSet HwtHlsCodeExtractor::_sinkAndHoistCodeFromRegion(
		const hwtHls::CodeExtractorAnalysisCache &CEAC, ValueSet &inputs,
		ValueSet &outputs, BasicBlock *newFuncRoot) {
	ValueSet SinkingCands, HoistingCands;
	BasicBlock *CommonExit = nullptr;
	findAllocas(CEAC, SinkingCands, HoistingCands, CommonExit);
	assert(HoistingCands.empty() || CommonExit);

	// Find inputs to, outputs from the code region.
	findInputsOutputs(inputs, outputs, SinkingCands);
	if (AggregateInputs) {
		size_t aggregatedInputCnt = 0;
		for (auto inp : inputs) {
			if (isa<Argument>(inp)) {
				ExcludeArgsFromAggregate.insert(inp);
			} else {
				assert(!inp->getType()->isPointerTy());
				aggregatedInputCnt++;
			}
		}
		if (aggregatedInputCnt <= 1)
			AggregateInputs = false;
	}
	if (AggregateOutputs && outputs.size() <= 1)
		AggregateOutputs = false;

	// Now sink all instructions which only have non-phi uses inside the region.
	// Group the allocas at the start of the block, so that any bitcast uses of
	// the allocas are well-defined.
	AllocaInst *FirstSunkAlloca = nullptr;
	for (auto *II : SinkingCands) {
		if (auto *AI = dyn_cast<AllocaInst>(II)) {
			AI->moveBefore(*newFuncRoot, newFuncRoot->getFirstInsertionPt());
			if (!FirstSunkAlloca)
				FirstSunkAlloca = AI;
		}
	}
	assert(
			(SinkingCands.empty() || FirstSunkAlloca)
					&& "Did not expect a sink candidate without any allocas");
	for (auto *II : SinkingCands) {
		if (!isa<AllocaInst>(II)) {
			cast<Instruction>(II)->moveAfter(FirstSunkAlloca);
		}
	}

	if (!HoistingCands.empty()) {
		auto *HoistToBlock = findOrCreateBlockForHoisting(CommonExit);
		Instruction *TI = HoistToBlock->getTerminator();
		for (auto *II : HoistingCands)
			cast<Instruction>(II)->moveBefore(TI);
	}

	// Collect objects which are inputs to the extraction region and also
	// referenced by lifetime start markers within it. The effects of these
	// markers must be replicated in the calling function to prevent the stack
	// coloring pass from merging slots which store input objects.
	ValueSet LifetimesStart;
	eraseLifetimeMarkersOnInputs(Blocks, SinkingCands, LifetimesStart);
	return LifetimesStart;
}

SmallPtrSet<BasicBlock*, 1> HwtHlsCodeExtractor::_collectExitBlocks(
		SmallPtrSet<BasicBlock*, 1> &ExitBlocks,
		DenseMap<BasicBlock*, BlockFrequency> &ExitWeights,
		llvm::SetVector<BasicBlock*> &ExitingBlocks) {
	// Calculate the exit blocks for the extracted region and the total exit
	// weights for each of those blocks.
	for (BasicBlock *Block : Blocks) {
		for (BasicBlock *Succ : successors(Block)) {
			if (!Blocks.count(Succ)) {
				// Update the branch weight for this successor.
				if (BFI) {
					BlockFrequency &BF = ExitWeights[Succ];
					BF += BFI->getBlockFreq(Block)
							* BPI->getEdgeProbability(Block, Succ);
				}
				ExitingBlocks.insert(Block);
				ExitBlocks.insert(Succ);
			}
		}
	}
	NumExitBlocks = ExitBlocks.size();

	for (BasicBlock *Block : Blocks) {
		for (BasicBlock *OldTarget : successors(Block))
			if (!Blocks.contains(OldTarget))
				OldTargets.push_back(OldTarget);
	}
	return ExitBlocks;
}

void HwtHlsCodeExtractor::_discardIncompatibleAssumes() {
	// Remove @llvm.assume calls that will be moved to the new function from the
	// old function's assumption cache.
	for (BasicBlock *Block : Blocks) {
		for (Instruction &I : llvm::make_early_inc_range(*Block)) {
			if (auto *AI = dyn_cast<AssumeInst>(&I)) {
				if (AC)
					AC->unregisterAssumption(AI);
				AI->eraseFromParent();
			}
		}
	}
}

BlockFrequency HwtHlsCodeExtractor::_calculateNewEntryFreq(BasicBlock *header) {
	// Calculate the entry frequency of the new function before we change the root
	//   block.
	BlockFrequency EntryFreq;
	if (BFI) {
		assert(BPI && "Both BPI and BFI are required to preserve profile info");
		for (BasicBlock *Pred : predecessors(header)) {
			if (Blocks.count(Pred))
				continue;
			EntryFreq += BFI->getBlockFreq(Pred)
					* BPI->getEdgeProbability(Pred, header);
		}
	}
	return EntryFreq;
}

void HwtHlsCodeExtractor::_updateNewEntryFreq(BlockFrequency EntryFreq,
		Function *newFunction, BasicBlock *codeReplacer) {
	// Update the entry count of the function.
	if (BFI) {
		auto Count = BFI->getProfileCountFromFreq(EntryFreq);
		if (Count)
			newFunction->setEntryCount(
					ProfileCount(*Count, Function::PCT_Real)); // FIXME
		BFI->setBlockFreq(codeReplacer, EntryFreq);
	}
}

void HwtHlsCodeExtractor::_finalDebugChecks(Function *oldFunction,
		Function *newFunction) {
	LLVM_DEBUG(if (verifyFunction(*newFunction, &errs())) {
		newFunction->dump()
		;
		report_fatal_error("verification of newFunction failed!")
		;
	}
);
    																																													LLVM_DEBUG(
			if (verifyFunction(*oldFunction)) report_fatal_error("verification of oldFunction failed!"));
	LLVM_DEBUG(
			if (AC && verifyAssumptionCache(*oldFunction, *newFunction, AC)) report_fatal_error("Stale Assumption cache for old Function!"));
}

//void HwtHlsCodeExtractor::_handleNewArgumentsOfOldAndNewFn(
//		Function &oldFunction, Function &newFunction, ValueSet &inputs,
//		ValueSet &outputs,
//		SmallVector<ArgToAddToParentFn> &argsToAddToParentFn) {
//	auto oldFnHwtHlsIoMD = HwtHlsIoMetadata_get(oldFunction);
//	// :note: this returns the list initialized for default values (as hwtHls.io is not specified yet )
//	auto newFnHwtHlsIoMD = HwtHlsIoMetadata_get(newFunction);
//	bool hasNewChannelToOldFn = false;
//	size_t newArgIndex = 0;
//	for (auto inValue : inputs) {
//		if (auto oldFnArg = dyn_cast<Argument>(inValue)) {
//			newFnHwtHlsIoMD[newArgIndex] =
//					oldFnHwtHlsIoMD[oldFnArg->getArgNo()];
//		} else {
//			newFnHwtHlsIoMD[newArgIndex] = HwtHlsIoMetadata()
//			llvm_unreachable(
//					"Create a map for new channel between oldFunction and newFunction");
//			hasNewChannelToOldFn = true;
//		}
//		newArgIndex++;
//	}
//	for (auto outValue : outputs) {
//		if (auto oldFnArg = dyn_cast<Argument>(outValue)) {
//			newFnHwtHlsIoMD[newArgIndex] =
//					oldFnHwtHlsIoMD[oldFnArg->getArgNo()];
//		} else {
//			llvm_unreachable(
//					"Create a map for new channel between oldFunction and newFunction");
//			hasNewChannelToOldFn = true;
//		}
//		newArgIndex++;
//	}
//	HwtHlsIoMetadata_set(newFunction, newFnHwtHlsIoMD);
//}

size_t countNonArguments(HwtHlsCodeExtractor::ValueSet &items) {
	size_t nonArgInputCnt = 0;
	for (auto i : items) {
		if (!isa<Argument>(i)) {
			nonArgInputCnt++;
		}
	}
	return nonArgInputCnt;
}

void HwtHlsCodeExtractor::_useVolatileForAccessToArgAllocas(
		CallInst &TheCall) const {
	size_t argI = 0;
	for (auto &_a : TheCall.args()) {
		auto a = _a.get();
		if (auto aAlloca = dyn_cast<AllocaInst>(a)) {
			for (auto allocaUser : aAlloca->users()) {
				if (auto ld = dyn_cast<LoadInst>(allocaUser)) {
					ld->setVolatile(true);
				} else if (auto st = dyn_cast<StoreInst>(allocaUser)) {
					st->setVolatile(true);
				}
			}
		}
		argI++;
	}
}

// :note: compiled from llvm-18 but modified for different in/out aggregation
/// emitCallAndSwitchStatement - This method sets up the caller side by adding
/// the call instruction, splitting any PHI nodes in the header block as
/// necessary.
CallInst* HwtHlsCodeExtractor::emitCallAndSwitchStatement(Function *newFunction,
		BasicBlock *codeReplacer, ValueSet &inputs, ValueSet &outputs,
		llvm::SetVector<BasicBlock*> &ExitingBlocks,
		MutableArrayRef<HwtHlsIoMetadata> newFnHwtHlsIoMD,
		MutableArrayRef<ArgToAddToParentFn> argsToAddToParentFn) {
	// Emit a call to the new function, passing in: *pointer to struct (if
	// aggregating parameters), or plan inputs and allocated memory for outputs
	std::vector<Value*> params, ReloadOutputs, Reloads;
	ValueSet StructInValues;
	ValueSet StructOutValues;

	Module *M = newFunction->getParent();
	LLVMContext &Context = M->getContext();
	const DataLayout &DL = M->getDataLayout();
	CallInst *call = nullptr;
	auto &Ctx = M->getContext();
	auto &ParentFn = *codeReplacer->getParent();
	size_t oldFunctionArgI = ParentFn.arg_size(); // current index of newly added argument to parent function

	auto updateMetadataForChannelIoArg = [&argsToAddToParentFn,
			&newFnHwtHlsIoMD, &ParentFn, newFunction, &oldFunctionArgI](
			IODirection dirForNewFn, size_t newFnArgI,
			std::optional<size_t> width, std::optional<AllocaInst*> tmpAlloca) {
		assert(newFnArgI < newFnHwtHlsIoMD.size());
		size_t oldFnNewArgI = oldFunctionArgI - ParentFn.arg_size();
		assert(oldFnNewArgI < argsToAddToParentFn.size());
		if (!width.has_value() && tmpAlloca.has_value())
			width =
					tmpAlloca.value()->getAllocatedType()->getScalarSizeInBits();
		HwtHlsIoMetadata &childMd = newFnHwtHlsIoMD[newFnArgI];
		assert(childMd.direction == dirForNewFn);
		childMd.otherThreadFn = &ParentFn;
		childMd.otherArgIndex = oldFunctionArgI;
		//HwtHlsIoMetadata parentMd(IODirection::IO_DIR_OUT, 0, width,
		//		width, true, newFunction, argI);
		auto &parentMd = argsToAddToParentFn[oldFnNewArgI];
		if (width.has_value()) {
			auto w = width.value();
			if (dirForNewFn == IODirection::IO_DIR_IN) {
				assert(childMd.readWordWidth == w);
				assert(childMd.writeWordWidth == 0);
				assert(parentMd.metadata.readWordWidth == 0);
				assert(parentMd.metadata.writeWordWidth == w);
			} else {
				assert(dirForNewFn == IODirection::IO_DIR_OUT);
				assert(childMd.readWordWidth == 0);
				assert(childMd.writeWordWidth == w);
				assert(parentMd.metadata.readWordWidth == w);
				assert(parentMd.metadata.writeWordWidth == 0);
			}
		}
		if (tmpAlloca.has_value())
			parentMd.parentFnTmp = tmpAlloca.value();
		assert(parentMd.metadata.direction == IODirection_reverse(dirForNewFn));
		parentMd.metadata.otherThreadFn = newFunction;
		parentMd.metadata.otherArgIndex = newFnArgI;
		//argsToAddToParentFn.push_back((ArgToAddToParentFn ) { AggregatedInTmp,
		//				parentMd });
	};
	// Add inputs as params, or to be filled into the struct
	// (params are passed trough tmp AllocaInst and may be aggregated together using concat)
	auto inTmpAllocaIP =
			AllocationBlock ?
					&*AllocationBlock->getFirstInsertionPt() :
					&codeReplacer->getParent()->front().front();

	IRBuilder<> Builder(Ctx);
	unsigned ScalarInputArgNo = 0;
	AllocaInst *AggregatedInTmp = nullptr;
	SmallVector<unsigned, 1> SwiftErrorArgs;
	for (Value *input : inputs) {
		if (AggregateInputs && !ExcludeArgsFromAggregate.contains(input)) {
			StructInValues.insert(input);
		} else {
			if (input->isSwiftError())
				SwiftErrorArgs.push_back(ScalarInputArgNo);
			if (isa<Argument>(input) || isa<AllocaInst>(input)) {
				params.push_back(input);
				if (auto ai = dyn_cast<AllocaInst>(input)) {
					size_t width =
							ai->getAllocatedType()->getScalarSizeInBits();
					updateMetadataForChannelIoArg(IODirection::IO_DIR_IN,
							ScalarInputArgNo, width, ai);
					++oldFunctionArgI;
				}
			} else {
				size_t width = input->getType()->getIntegerBitWidth();
				auto alloca = new AllocaInst(IntegerType::get(Ctx, width),
						DL.getAllocaAddrSpace(), nullptr, input->getName(),
						inTmpAllocaIP);
				Builder.SetInsertPoint(codeReplacer, codeReplacer->end());
				Builder.CreateStore(input, alloca, true);
				updateMetadataForChannelIoArg(IODirection::IO_DIR_IN,
						ScalarInputArgNo, width, alloca);
				params.push_back(alloca);
				++oldFunctionArgI;
			}
			++ScalarInputArgNo;
		}
	}
	// size_t StructInputArgI = ScalarInputArgNo;
	if (StructInValues.size()) {
		size_t width = 0;
		for (Value *V : StructInValues) {
			if (ExcludeArgsFromAggregate.contains(V))
				continue;
			assert(!V->getType()->isPointerTy());
			width += V->getType()->getScalarSizeInBits();
		}
		// Allocate a struct at the beginning of this function
		AggregatedInTmp = new AllocaInst(IntegerType::get(Ctx, width),
				DL.getAllocaAddrSpace(), nullptr, "agrInArg", inTmpAllocaIP);
		updateMetadataForChannelIoArg(IODirection::IO_DIR_IN, ScalarInputArgNo,
				width, AggregatedInTmp);
		++oldFunctionArgI;
		++ScalarInputArgNo;
	}

	// Create allocas for the outputs
	unsigned ScalarOutputArgNo = 0;
	auto tmpAllocaIp = &codeReplacer->getParent()->front().front();
	for (Value *output : outputs) {
		if (AggregateOutputs && !ExcludeArgsFromAggregate.contains(output)) {
			StructOutValues.insert(output);
		} else {
			AllocaInst *alloca = new AllocaInst(output->getType(),
					DL.getAllocaAddrSpace(), nullptr,
					output->getName() + ".loc", tmpAllocaIp);
			ReloadOutputs.push_back(alloca);
			params.push_back(alloca);

			updateMetadataForChannelIoArg(IODirection::IO_DIR_OUT,
					ScalarInputArgNo, output->getType()->getScalarSizeInBits(),
					alloca);
			assert(!isa<Argument>(output));
			++oldFunctionArgI;
			++ScalarOutputArgNo;
		}
	}

	AllocaInst *AggregatedOutTmp = nullptr;
	if (StructOutValues.size()) {
		assert(
				StructOutValues.size() > 1
						&& "If it was just 1 the AggregateOutputs should have been set to false");
		size_t width = 0;
		for (auto o : StructOutValues) {
			width += o->getType()->getScalarSizeInBits();
		}
		// :note: constructed in old functions
		AggregatedOutTmp = new AllocaInst(IntegerType::get(Ctx, width),
				DL.getAllocaAddrSpace(), nullptr, "AggregatedOutTmp",
				tmpAllocaIp);
		// newly generated alloca for output
		updateMetadataForChannelIoArg(IODirection::IO_DIR_OUT, ScalarInputArgNo,
				{ }, AggregatedOutTmp);
		++oldFunctionArgI;
		++ScalarOutputArgNo;
	}
	if (AggregateInputs && !StructInValues.empty()) {
		if (ArgsInZeroAddressSpace && DL.getAllocaAddrSpace() != 0) {
			auto *StructSpaceCast = new AddrSpaceCastInst(AggregatedInTmp,
					PointerType::get(Context, 0), "structArg.ascast");
			StructSpaceCast->insertAfter(AggregatedInTmp);
			params.push_back(StructSpaceCast);
		} else {
			params.push_back(AggregatedInTmp);
		}
		// Store aggregated inputs in the struct.
		Builder.SetInsertPoint(codeReplacer);
		auto conc = CreateBitConcat(&Builder, StructInValues.getArrayRef());
		Builder.CreateStore(conc, AggregatedInTmp, true);
	}

	// Emit the call to the function
	call = CallInst::Create(newFunction, params,
			NumExitBlocks > 1 ? "targetBlock" : "");
	// Add debug location to the new call, if the original function has debug
	// info. In that case, the terminator of the entry block of the extracted
	// function contains the first debug location of the extracted function,
	// set in extractCodeRegion.
	if (codeReplacer->getParent()->getSubprogram()) {
		if (auto DL =
				newFunction->getEntryBlock().getTerminator()->getDebugLoc())
			call->setDebugLoc(DL);
	}
	call->insertInto(codeReplacer, codeReplacer->end());

	// Set swifterror parameter attributes.
	for (unsigned SwiftErrArgNo : SwiftErrorArgs) {
		call->addParamAttr(SwiftErrArgNo, Attribute::SwiftError);
		newFunction->addParamAttr(SwiftErrArgNo, Attribute::SwiftError);
	}

	LoadInst *AggregatedOutTmpLd = nullptr;
	size_t AggregatedOutTmpLdBitOffset = 0;
	// Reload the outputs passed in by reference, use the struct if output is in
	// the aggregate or reload from the scalar argument.
	for (unsigned i = 0, e = outputs.size(), scalarIdx = 0; i != e; ++i) {
		Value *load;
		auto &Out = *outputs[i];
		if (AggregateOutputs && StructOutValues.contains(outputs[i])) {
			if (!AggregatedOutTmpLd) {
				Builder.SetInsertPoint(codeReplacer);
				AggregatedOutTmpLd = Builder.CreateLoad(
						AggregatedOutTmp->getAllocatedType(), AggregatedOutTmp,
						"aggregatedOut.ld");
			}
			size_t width = Out.getType()->getIntegerBitWidth();
			Builder.SetInsertPoint(codeReplacer);
			load = CreateBitRangeGetConst(&Builder, AggregatedOutTmpLd,
					AggregatedOutTmpLdBitOffset, width,
					Out.getName() + ".reload");
			AggregatedOutTmpLdBitOffset += width;
		} else {
			auto Output = ReloadOutputs[scalarIdx];
			++scalarIdx;
			load = new LoadInst(Out.getType(), Output,
					Out.getName() + ".reload", codeReplacer);
		}
		Reloads.push_back(load);
		std::vector<User*> Users(Out.user_begin(), Out.user_end());
		for (User *U : Users) {
			Instruction *inst = cast<Instruction>(U);
			if (!Blocks.count(inst->getParent()))
				inst->replaceUsesOfWith(&Out, load);
		}
	}

	// Now we can emit a switch statement using the call as a value.
	SwitchInst *TheSwitch = SwitchInst::Create(
			Constant::getNullValue(Type::getInt16Ty(Context)), codeReplacer, 0,
			codeReplacer);

	// Since there may be multiple exits from the original region, make the new
	// function return an unsigned, switch on that number.  This loop iterates
	// over all of the blocks in the extracted region, updating any terminator
	// instructions in the to-be-extracted region that branch to blocks that are
	// not in the region to be extracted.
	std::map<BasicBlock*, BasicBlock*> ExitBlockMap;

	// Iterate over the previously collected targets, and create new blocks inside
	// the function to branch to.
	unsigned switchVal = 0;
	for (BasicBlock *OldTarget : OldTargets) {
		if (Blocks.count(OldTarget))
			continue;
		BasicBlock *&NewTarget = ExitBlockMap[OldTarget];
		if (NewTarget)
			continue;

		// If we don't already have an exit stub for this non-extracted
		// destination, create one now!
		NewTarget = BasicBlock::Create(Context,
				OldTarget->getName() + ".exitStub", newFunction);
		unsigned SuccNum = switchVal++;

		Value *brVal = nullptr;
		assert(NumExitBlocks < 0xffff && "too many exit blocks for switch");
		switch (NumExitBlocks) {
		case 0:
		case 1:
			break;  // No value needed.
		case 2:         // Conditional branch, return a bool
			brVal = ConstantInt::get(Type::getInt1Ty(Context), !SuccNum);
			break;
		default:
			brVal = ConstantInt::get(Type::getInt16Ty(Context), SuccNum);
			break;
		}

		ReturnInst::Create(Context, brVal, NewTarget);

		// Update the switch instruction.
		TheSwitch->addCase(ConstantInt::get(Type::getInt16Ty(Context), SuccNum),
				OldTarget);
	}

	for (BasicBlock *Block : Blocks) {
		Instruction *TI = Block->getTerminator();
		for (unsigned i = 0, e = TI->getNumSuccessors(); i != e; ++i) {
			if (Blocks.count(TI->getSuccessor(i)))
				continue;
			BasicBlock *OldTarget = TI->getSuccessor(i);
			// add a new basic block which returns the appropriate value
			BasicBlock *NewTarget = ExitBlockMap[OldTarget];
			assert(NewTarget && "Unknown target block!");

			// rewrite the original branch instruction with this new target
			TI->setSuccessor(i, NewTarget);
		}
	}
	for (auto a : argsToAddToParentFn) {
		assert(a.parentFnTmp);
	}
	// Now that we've done the deed, simplify the switch instruction.
	Type *OldFnRetTy = TheSwitch->getParent()->getParent()->getReturnType();
	switch (NumExitBlocks) {
	case 0:
		// There are no successors (the block containing the switch itself), which
		// means that previously this was the last part of the function, and hence
		// this should be rewritten as a `ret'

		// Check if the function should return a value
		if (OldFnRetTy->isVoidTy()) {
			ReturnInst::Create(Context, nullptr, TheSwitch);  // Return void
		} else if (OldFnRetTy == TheSwitch->getCondition()->getType()) {
			// return what we have
			ReturnInst::Create(Context, TheSwitch->getCondition(), TheSwitch);
		} else {
			// Otherwise we must have code extracted an unwind or something, just
			// return whatever we want.
			ReturnInst::Create(Context, Constant::getNullValue(OldFnRetTy),
					TheSwitch);
		}

		TheSwitch->eraseFromParent();
		break;
	case 1:
		// Only a single destination, change the switch into an unconditional
		// branch.
		BranchInst::Create(TheSwitch->getSuccessor(1), TheSwitch);
		TheSwitch->eraseFromParent();
		break;
	case 2:
		BranchInst::Create(TheSwitch->getSuccessor(1),
				TheSwitch->getSuccessor(2), call, TheSwitch);
		TheSwitch->eraseFromParent();
		break;
	default:
		// Otherwise, make the default destination of the switch instruction be one
		// of the other successors.
		TheSwitch->setCondition(call);
		TheSwitch->setDefaultDest(TheSwitch->getSuccessor(NumExitBlocks));
		// Remove redundant case
		TheSwitch->removeCase(SwitchInst::CaseIt(TheSwitch, NumExitBlocks - 1));
		break;
	}

	// Insert lifetime markers around the reloads of any output values. The
	// allocas output values are stored in are only in-use in the codeRepl block.
	//insertLifetimeMarkersSurroundingCall(M, ReloadOutputs, ReloadOutputs, call);

	return call;
}

void HwtHlsCodeExtractor::_addVariablesToAssertBeginAndEndSyncIfNecessary(
		IRBuilder<> &Builder, Function *oldFunction, BasicBlock *header,
		BasicBlock *codeReplacerBB, ValueSet &inputs, ValueSet &outputs) {
	auto headerIP = header->getFirstNonPHIOrDbgOrAlloca();
	auto Ty1b = IntegerType::get(oldFunction->getContext(), 1);
	if (!beginMayBeAsync && countNonArguments(inputs) == 0) {
		// add 1b variable for begin sync if necessary
		auto newFnName = _getNewFunctionName(*oldFunction, *header);
		assert(!codeReplacerBB->getTerminator());
		Builder.SetInsertPoint(&*oldFunction->getEntryBlock().begin());
		auto beginSyncAlloca = Builder.CreateAlloca(Ty1b, 0,
				"threadBeginSync." + newFnName);
		Builder.SetInsertPoint(codeReplacerBB); // write to inputs before extracted section
		Builder.CreateStore(ConstantInt::get(Ty1b, 1), beginSyncAlloca, /*isVolatile*/
		true);
		Builder.SetInsertPoint(headerIP); // load from inputs at the beginning of the extracted section
		Builder.CreateLoad(Ty1b, beginSyncAlloca, /*isVolatile*/true);
		inputs.insert(beginSyncAlloca);
	}
	//AllocaInst *endSyncAlloca = nullptr;
	if (!endMayBeAsync && countNonArguments(outputs) == 0) {
		// add 1b variable for output sync in necessary
		auto newFnName = _getNewFunctionName(*oldFunction, *header);
		assert(!codeReplacerBB->getTerminator());
		// :attention: the uses of outputs are replaced with a load from tmp phi
		//   that is why new instruction has to be created and constant can not be used directly
		Builder.SetInsertPoint(header->getTerminator());
		auto fr = Builder.CreateFreeze(ConstantInt::get(Ty1b, 1),
				"threadEndSync." + newFnName);
		outputs.insert(fr);
	}

}

// :note: copied from llvm-18 but complete rewrite
/// Perform the extraction, returning the new function and providing an
/// interface to see what was categorized as inputs and outputs.
///
/// \param CEAC - Cache to speed up operations for the CodeExtractor when
/// hoisting, and extracting lifetime values and assumes.
/// \param Inputs [out] - filled with  values marked as inputs to the
/// newly outlined function.
/// \param Outputs [out] - filled with values marked as outputs to the
/// newly outlined function.
/// \returns zero when called on a CodeExtractor instance where isEligible
/// returns false.
Function* HwtHlsCodeExtractor::extractCodeRegion(
		const hwtHls::CodeExtractorAnalysisCache &CEAC, bool extractedIsInLoop,
		ValueSet &inputs, ValueSet &outputs,
		SmallVector<ArgToAddToParentFn> &argsToAddToParentFn) {
	assert(inputs.empty() && "This is supposed to be output argument");
	assert(outputs.empty() && "This is supposed to be output argument");
	// Assumption: this is a single-entry code region, and the header is the first
	// block in the region.
	BasicBlock *header = *Blocks.begin();
	Function *oldFunction = header->getParent();
	IRBuilder<> Builder(oldFunction->getContext());

	BlockFrequency EntryFreq = _calculateNewEntryFreq(header);

	_discardIncompatibleAssumes();

	// If we have any return instructions in the region, split those blocks so
	// that the return is not in the region.
	splitReturnBlocks();
	SmallPtrSet<BasicBlock*, 1> ExitBlocks;
	llvm::SetVector<BasicBlock*> ExitingBlocks;
	DenseMap<BasicBlock*, BlockFrequency> ExitWeights;
	_collectExitBlocks(ExitBlocks, ExitWeights, ExitingBlocks);

	// If we have to split PHI nodes of the entry or exit blocks, do so now.
	severSplitPHINodesOfEntry(header);
	severSplitPHINodesOfExits(ExitBlocks);

	// This takes place of the original loop
	BasicBlock *codeReplacerBB = BasicBlock::Create(header->getContext(),
			"threadSplitCodeRepl", oldFunction, header);
	codeReplacerBB->IsNewDbgInfoFormat = oldFunction->IsNewDbgInfoFormat;

	// The new function needs a root node because other nodes can branch to the
	// head of the region, but the entry node of a function cannot have preds.
	BasicBlock *newFuncRoot = BasicBlock::Create(header->getContext(),
			"newFuncRoot");
	newFuncRoot->IsNewDbgInfoFormat = oldFunction->IsNewDbgInfoFormat;

	auto *BranchI = BranchInst::Create(header);
	_tryToFindOriginalCodeLocOfInitialBranch(oldFunction, BranchI);
	BranchI->insertInto(newFuncRoot, newFuncRoot->end());

	auto LifetimesStart = _sinkAndHoistCodeFromRegion(CEAC, inputs, outputs,
			newFuncRoot);
	_addVariablesToAssertBeginAndEndSyncIfNecessary(Builder, oldFunction,
			header, codeReplacerBB, inputs, outputs);
	// Construct new function based on inputs/outputs & add allocas for all defs.

	Function *newFunction;
	SmallVector<HwtHlsIoMetadata> newFnHwtHlsIoMD;
	SmallVector<ArgToAddToParentFn> _argsToAddToParentFn;
	std::tie(newFunction, newFnHwtHlsIoMD) = constructFunction(inputs, outputs,
			header, newFuncRoot, codeReplacerBB, ExitingBlocks, oldFunction,
			_argsToAddToParentFn, oldFunction->getParent());
	_updateNewEntryFreq(EntryFreq, newFunction, codeReplacerBB);
	//_handleNewArgumentsOfOldAndNewFn(*oldFunction, *newFunction, inputs,
	//		outputs, argsToAddToParentFn);

	CallInst *TheCall = emitCallAndSwitchStatement(newFunction, codeReplacerBB,
			inputs, outputs, ExitingBlocks, newFnHwtHlsIoMD,
			_argsToAddToParentFn);
	_useVolatileForAccessToArgAllocas(*TheCall);
	argsToAddToParentFn.insert(argsToAddToParentFn.end(),
			_argsToAddToParentFn.begin(), _argsToAddToParentFn.end());
	HwtHlsIoMetadata_set(*newFunction, newFnHwtHlsIoMD);

	// The tmp alloca is generated for outputs and the use of outputs was overridden to use this new alloca
	// bb0:
	//   %o0.loc = alloca i1, align 1 ; newly generated tmp alloca for output
	//   %o0.orig = alloca i1, align 1
	//   store volatile i1 true, ptr %orig.out0, align 1
	// CodeRepl:
	//   call void @llvm.lifetime.start.p0(i64 -1, ptr %o0.loc)
	//   call void @noDeps.t1(ptr addrspace(2) %dataOut1, ptr %main.t1, ptr %o0.loc)
	//   %o0.reload = load i1, ptr %o0.loc, align 1
	//   call void @llvm.lifetime.end.p0(i64 -1, ptr %.loc)
	//   br label %bb.main.t1

	moveCodeToFunction(newFunction);
	//if (endSyncAlloca) {
	//	assert(TheCall->getParent() == codeReplacerBB);
	//	Builder.SetInsertPoint(codeReplacerBB,
	//			TheCall->getIterator()->getNextNode()->getIterator());
	//	Builder.CreateLoad(Ty1b, endSyncAlloca, /*isVolatile*/true);
	//}

	// Replicate the effects of any lifetime start/end markers which referenced
	// input objects in the extraction region by placing markers around the call.
	// :note: this is not compatible with extraction as thread as allocas will be converted to channel
	//	insertLifetimeMarkersSurroundingCall(oldFunction->getParent(),
	//			LifetimesStart.getArrayRef(), { }, TheCall);

	// Propagate personality info to the new function if there is one.
	if (oldFunction->hasPersonalityFn())
		newFunction->setPersonalityFn(oldFunction->getPersonalityFn());

	// Update the branch weights for the exit block.
	if (BFI && NumExitBlocks > 1)
		calculateNewCallTerminatorWeights(codeReplacerBB, ExitWeights, BPI);

	_updateBlocksForPhisInEntryAndExit(header, newFuncRoot, ExitBlocks,
			codeReplacerBB);
	if (extractedIsInLoop) {
		// the inf loop must be added with newFuncRoot as header and each returning block as latch
		// the return itself should return only void and should be replaced by jump to top inf loop header
		splitBlockBefore(newFuncRoot, newFuncRoot->begin(), nullptr, nullptr,
				nullptr, "threadEntry");
		SmallVector<BasicBlock*> newBBs;
		newBBs.reserve(newFunction->size());
		for (auto &BB : *newFunction) {
			newBBs.push_back(&BB);
		}
		for (auto *BB : newBBs) {
			if (auto ret = dyn_cast<ReturnInst>(BB->getTerminator())) {
				assert(ret->getType()->isVoidTy());
				auto *toTopInfLoopBranchI = BranchInst::Create(newFuncRoot);
				toTopInfLoopBranchI->insertBefore(ret);
				ret->eraseFromParent();
				//if (endSyncAlloca) {
				//	Builder.SetInsertPoint(toTopInfLoopBranchI);
				//	Builder.CreateStore(ConstantInt::get(Ty1b, 1),
				//			endSyncAlloca, /*isVolatile*/true);
				//}
			}
		}
	}
	//else if (endSyncAlloca) {
	//	for (auto &BB : *newFunction) {
	//		if (auto ret = dyn_cast<ReturnInst>(BB.getTerminator())) {
	//			Builder.SetInsertPoint(ret);
	//			Builder.CreateStore(ConstantInt::get(Ty1b, 1), endSyncAlloca, /*isVolatile*/
	//			true);
	//		}
	//	}
	//}
	fixupDebugInfoPostExtraction(*oldFunction, *newFunction, *TheCall);

	// Mark the new function `noreturn` if applicable. Terminators which resume
	// exception propagation are treated as returning instructions. This is to
	// avoid inserting traps after calls to outlined functions which unwind.
	bool doesNotReturn = none_of(*newFunction, [](const BasicBlock &BB) {
		const Instruction *Term = BB.getTerminator();
		return isa<ReturnInst>(Term) || isa<ResumeInst>(Term);
	});
	if (doesNotReturn)
		newFunction->setDoesNotReturn();

	_finalDebugChecks(oldFunction, newFunction);
	TheCall->eraseFromParent(); // because the load/store to channels of thread replaces the call
	return newFunction;
}

}
