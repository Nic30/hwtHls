#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>

#include <llvm/Analysis/BlockFrequencyInfo.h>
#include <llvm/Analysis/BranchProbabilityInfo.h>

#include <hwtHls/llvm/Transforms/utils/functionMutating.h>

using namespace llvm;

#define DEBUG_TYPE "hwtHls::ThreadExtractor"

namespace hwtHls {

void HwtHlsCodeExtractor::_constructFunctionDeclaration_AssignNamesToNewArgs(
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

Type* HwtHlsCodeExtractor::_addVariablesToAssertBeginAndEndSyncIfNecessary(
		ValueSet &inputs, ValueSet &outputs, Type *RetTy) {
	auto countNonArguments = [](HwtHlsCodeExtractor::ValueSet &items) {
		size_t nonArgInputCnt = 0;
		for (auto i : items) {
			if (!isa<Argument>(i)) {
				nonArgInputCnt++;
			}
		}
		return nonArgInputCnt;
	};
	//// Construct new function based on inputs/outputs & add allocas for all defs.
	BasicBlock* header = Blocks[0];
	Function *oldFunction = header->getParent();
	IRBuilder<> Builder(oldFunction->getContext());
	Builder.SetInsertPoint(&*oldFunction->getEntryBlock().begin());
	auto Ty1b = IntegerType::get(oldFunction->getContext(), 1);
	if (!beginMayBeAsync && countNonArguments(inputs) == 0) {
		// add 1b variable for begin sync if necessary
		//auto newFnName = _getNewFunctionName(*oldFunction, *header);
		//assert(!codeReplacerBB->getTerminator());
		beginSyncFreeze = dyn_cast<FreezeInst>( Builder.CreateFreeze(ConstantInt::get(Ty1b, 1), Suffix + ".threadBeginSync"));
		inputs.insert(beginSyncFreeze);
	}
	if (!RetTy->isVoidTy()) {
		// :note: will be replaced after the switch condition is resolved
		returnValFreeze = dyn_cast<FreezeInst>(Builder.CreateFreeze(ConstantInt::get(RetTy, 0), Suffix + ".threadReturn"));
		outputs.insert(returnValFreeze);
		RetTy = Type::getVoidTy(RetTy->getContext());
	}
	if (!endMayBeAsync && countNonArguments(outputs) == 0) {
		// add 1b variable for output sync in necessary
		//auto newFnName = _getNewFunctionName(*oldFunction, *header);
		// :attention: the uses of outputs are replaced with a load from tmp phi
		//   that is why new instruction has to be created and constant can not be used directly
		Builder.SetInsertPoint(header->getTerminator());
		endSyncFreeze = dyn_cast<FreezeInst>( Builder.CreateFreeze(ConstantInt::get(Ty1b, 1), Suffix + ".threadEndSync"));
		outputs.insert(endSyncFreeze);
	}
	return RetTy;
}

/// extracted from llvm-21, but complete rewrite because input/outputs are aggregated into a bit
/// vector, begin/end sync var. may be a added and return val. is passed trough arg
///
/// Generates the function declaration for the function containing the
/// extracted code.
/// :note: params are in format (in*, aggregatedIn?, out*, aggregatedOut?)
/// :note: this expects all GEPs, Alloca, loops and private var to be sinked into extracted region
Function* HwtHlsCodeExtractor::constructFunctionDeclaration(
	    const ValueSet &inputs, const ValueSet &outputs, BlockFrequency EntryFreq,
	    const Twine &Name, ValueSet &StructValues, StructType *&StructTy) {
	LLVM_DEBUG(dbgs() << "inputs: " << inputs.size() << "\n");
	LLVM_DEBUG(dbgs() << "outputs: " << outputs.size() << "\n");

	Function * oldFunction = Blocks[0]->getParent();
	Type *RetTy = getSwitchType();
	RetTy = _addVariablesToAssertBeginAndEndSyncIfNecessary(const_cast<ValueSet&>(inputs), const_cast<ValueSet&>(outputs), RetTy);
	_discardAggragationIfJustOneInOrOut(inputs, outputs);

	std::vector<Type*> ParamTy; // types of parameters for new function
	std::vector<Type*> AggInParamTy; // types of input parameters which will be concatenated together
	std::vector<Type*> AggOutParamTy;
	//const DataLayout &DL = M->getDataLayout();
	auto oldFnHwtHlsIoMD = HwtHlsIoMetadata_get(*oldFunction);
	// pre-fill dummy metadata

	auto prefillMetadata = [this](
			IODirection dirForNewFn, size_t width, AllocaInst *tmpAlloca) {
		auto isIn = dirForNewFn == IODirection::IO_DIR_IN;
		newFnHwtHlsIoMD.push_back(
				HwtHlsIoMetadata(dirForNewFn, 0, isIn ? width : 0,
						isIn ? 0 : width, nullptr, 0, true, true,
						isIn ? 0 : outputBufferCapacity)); // connection should be initialized later in emitCallAndSwitchStatement()
		argsToAddToParentFn.push_back(
				{ tmpAlloca, HwtHlsIoMetadata(IODirection_reverse(dirForNewFn),
						0, isIn ? 0 : width, isIn ? width : 0, nullptr, 0, true,
						true, isIn ? inputBufferCapacity : 0) }); // connection should be initialized later in emitCallAndSwitchStatement()

	};

	LLVMContext &Context = oldFunction->getContext();
	// :note: this will be just pointer representing HwIO of parent function
	// if there is no use left in parent function the argument will be removed from parent fn.
	// else it will be shared between parent and this function and interconnect will have
	// to be instantiated later

	// Add the types of the input values to the function's argument list
	for (Value *value : inputs) {
		LLVM_DEBUG(dbgs() << "value used in func: " << *value << "\n");
		auto addrSpace = ParamTy.size();
		if (auto a = dyn_cast<Argument>(value)) {
			// this is io of the oldFunction
			newFnHwtHlsIoMD.push_back(oldFnHwtHlsIoMD[a->getArgNo()]);
			ParamTy.push_back(PointerType::get(Context, addrSpace));
		} else if (isa<GetElementPtrInst>(value)) {
			llvm_unreachable(
					"GetElementPtrInst should be already sinked into extracted region");
		} else if (AggregateInputs
				&& !ExcludeArgsFromAggregate.contains(value)) {
			assert(!isa<PointerType>(value->getType()));
			//if (isa<PointerType>(value->getType())) {
			//	auto tmpAlloca = dyn_cast<AllocaInst>(value);
			//	assert(tmpAlloca);
			//	auto t = tmpAlloca->getAllocatedType();
			//	assert(t->isIntegerTy());
			//	AggInParamTy.push_back(t);
			//} else {
				// stack input type to input aggregated struct
				AggInParamTy.push_back(value->getType());
			//}
			StructInValues.insert(value);
		//} else if (isa<PointerType>(value->getType())) {
		//	// this is some temporary value like beginSyncAlloca
		//	auto tmpAlloca = dyn_cast<AllocaInst>(value);
		//	assert(tmpAlloca);
		//	size_t width = tmpAlloca->getAllocatedType()->getIntegerBitWidth();
		//	prefillMetadata(IODirection::IO_DIR_IN, width, tmpAlloca);
		} else {
			size_t width = value->getType()->getScalarSizeInBits();
			prefillMetadata(IODirection::IO_DIR_IN, width, nullptr);
			ParamTy.push_back(PointerType::get(Context, addrSpace));
		}
	}
	assert(
			(ParamTy.size() + AggInParamTy.size() == inputs.size())
					&& "Number of scalar and aggregate params does not match inputs, outputs");
	//size_t AggregatedInArgIndex = ParamTy.size();
	IntegerType *AggregatedInTy = nullptr;
	// :note: arguments can be of IntegerType or PointerType, pointers represent
	//  channels and are excluded from aggregation
	if (AggregateInputs && !AggInParamTy.empty()) {
		size_t aggregatedWidth = 0;
		for (auto t : AggInParamTy)
			aggregatedWidth += t->getIntegerBitWidth();
		AggregatedInTy = IntegerType::get(Context, aggregatedWidth);
		auto addrSpace = ParamTy.size();
		ParamTy.push_back(PointerType::get(Context, addrSpace));
		prefillMetadata(IODirection::IO_DIR_IN, aggregatedWidth, nullptr);
	}

	// Add the types of the output values to the function's argument list.
	for (Value *output : outputs) {
		LLVM_DEBUG(dbgs() << "instr used in func: " << *output << "\n");
		auto addrSpace = ParamTy.size();
		assert(!isa<Argument>(output)); // output pointers are input value (because the address is the input)
		if (AggregateOutputs && !ExcludeArgsFromAggregate.contains(output)) {
			assert(!isa<PointerType>(output->getType()));
			//if (isa<PointerType>(output->getType())) {
			//	auto tmpAlloca = dyn_cast<AllocaInst>(output);
			//	ParamTy.push_back(tmpAlloca->getAllocatedType());
			//} else {
				AggOutParamTy.push_back(output->getType());
			//}
			StructOutValues.insert(output);
		} else {
			size_t width = output->getType()->getScalarSizeInBits();
			prefillMetadata(IODirection::IO_DIR_OUT, width, nullptr);
			ParamTy.push_back(PointerType::get(Context, addrSpace));
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
		AggregatedOutTy = IntegerType::get(Context, aggregatedWidth);
		auto addrSpace = ParamTy.size();
		ParamTy.push_back(PointerType::get(Context, addrSpace));
		prefillMetadata(IODirection::IO_DIR_OUT, aggregatedWidth, nullptr);
	}

	// This function returns unsigned, outputs will go back by reference.
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

	// Create the new function
	Function *newFunction = Function::Create(funcType,
			GlobalValue::InternalLinkage, oldFunction->getAddressSpace(),
			Name, oldFunction->getParent());
	constructFunctionDeclaration_inheritAttributes(oldFunction, newFunction);

	assert(
			AggInParamTy.size() != 1
					&& "AggregateInputs should be set to 0 then");
	assert(
			AggOutParamTy.size() != 1
					&& "AggregateOutputs should be set to 0 then");

	_constructFunctionDeclaration_AssignNamesToNewArgs(newFunction, ParamTy,
			inputs, outputs, StructInValues, StructOutValues, AggregatedInTy,
			AggregatedOutTy);

	std::vector<std::size_t> newArgOrder;
	for (size_t i = 0; i < newFunction->arg_size(); i++) {
		newArgOrder.push_back(i);
	}
	newFunction = mutateFunctionShuffleArgs(*newFunction, newArgOrder);
	// update newly added args to parent function to be connected to new thread function
	for (size_t i = 0; i < argsToAddToParentFn.size(); ++i) {
		argsToAddToParentFn[i].metadata.otherThreadFn = newFunction;
	}
	// Update the entry count of the function.
	if (BFI) {
		auto Count = BFI->getProfileCountFromFreq(EntryFreq);
		if (Count.has_value())
			newFunction->setEntryCount(
					Function::ProfileCount(*Count, Function::PCT_Real)); // FIXME
	}
	return newFunction;
}

}
