#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>

#include <iterator>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/functionMutating.h>

using namespace llvm;

#define DEBUG_TYPE "hwtHls::ThreadExtractor"

namespace hwtHls {

void HwtHlsCodeExtractor::_emitFunctionBody_UpdateInputUsesToUseNewArgs(
		IRBuilder<> &Builder, Function *newFunction, const ValueSet &inputs,
		const ValueSet &StructInValues, SmallVectorImpl<Value*> &NewValues) {
	// Rewrite all users of inputs in the extracted region to use the
	// arguments (or appropriate addressing into struct) instead.
	size_t aggregatedInBitOffset = 0;
	LoadInst *AggregatedInLd = nullptr;
	// expect params in format (in*, aggregatedIn?, out*, aggregatedOut?)
	Argument *inAggregate = nullptr;
	if (!StructInValues.empty()) {
		inAggregate = newFunction->getArg(
				inputs.size() - StructInValues.size());
	}
	Function::arg_iterator ScalarArgIt = newFunction->arg_begin();
	size_t inAggregateWidth = 0;
	for (auto v : StructInValues) {
		auto t = v->getType();
		if (isa<PointerType>(t)) {
			auto a = dyn_cast<AllocaInst>(v);
			assert(a);
			t = a->getAllocatedType();
		}

		if (auto IT = dyn_cast<IntegerType>(t)) {
			inAggregateWidth += IT->getIntegerBitWidth();
		} else {
			llvm_unreachable("NotImplemented");
		}
	}
	IntegerType * AggregatedInTy = nullptr;
	if (inAggregateWidth)
		AggregatedInTy = IntegerType::get(newFunction->getContext(),
			inAggregateWidth);
	for (unsigned i = 0, e = inputs.size(); i != e; ++i) {
		Value *RewriteVal;
		auto &Inp = *inputs[i];
		Value *parentLocalValue = dyn_cast<Argument>(&Inp);
		if (!parentLocalValue) {
			parentLocalValue = dyn_cast<AllocaInst>(&Inp);
		}
		bool isMemberOfInAggregate = AggregateInputs
				&& StructInValues.contains(&Inp);
		if (parentLocalValue && !isMemberOfInAggregate) {
			std::function<bool(llvm::User*)> isUserInsideOfExtractedSection = [
					Blocks=&Blocks](User *u) -> bool {
				if (Instruction *inst = dyn_cast<Instruction>(u))
					return static_cast<bool>(Blocks->count(inst->getParent()));
				return false;
			};
			replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace(Builder,
					*parentLocalValue, *ScalarArgIt,
					&isUserInsideOfExtractedSection);
			RewriteVal = &*ScalarArgIt++;
		} else {
			assert(!Inp.getType()->isPointerTy());
			assert(!newFunction->begin()->getTerminator());
			Builder.SetInsertPoint(&*newFunction->begin());
			size_t width = Inp.getType()->getIntegerBitWidth();
			if (isMemberOfInAggregate) {
				if (!AggregatedInLd) {
					AggregatedInLd = Builder.CreateLoad(AggregatedInTy,
							inAggregate, true, Inp.getName());
				}
				RewriteVal = CreateBitRangeGetConst(&Builder, AggregatedInLd,
						aggregatedInBitOffset, width, "");
				aggregatedInBitOffset += width;
			} else {
				RewriteVal = Builder.CreateLoad(Inp.getType(), &*ScalarArgIt,
						true, Inp.getName());
				++ScalarArgIt;
			}
		}

		NewValues.push_back(RewriteVal);
	}
}

void HwtHlsCodeExtractor::_emitFunctionBody_constructOutStores(
		IRBuilder<> &Builder, Function *newFunction, const ValueSet &outputs,
		const ValueSet &StructOutValues,
		Function::arg_iterator ScalarOutArgIt) {

	// Create stores to arguments representing outputs from this newFunction
	Function::arg_iterator AggregatedOutArgIt = std::ranges::next(ScalarOutArgIt, outputs.size() - StructOutValues.size());
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
		assert(TI);
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
			if (OutI == returnValFreeze)
				llvm_unreachable("NotImplemented - replace this later with ");

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
		for (auto& BB: *newFunction) {
			if (auto ret = dyn_cast<ReturnInst>(BB.getTerminator())) {
				SmallVector<Value*> StructOutValuesTmp;
				StructOutValuesTmp.reserve(StructOutValues.size());
				for (auto V: StructOutValues) {
					// [todo] rm this and replace aggregated and non-aggregated outputs on one place
					if (V == returnValFreeze) {
						V = ret->getReturnValue();
					}
					StructOutValuesTmp.push_back(V);
				}
				Builder.SetInsertPoint(ret);
				auto outV = CreateBitConcat(&Builder, StructOutValuesTmp,
						"AggregatedOut.val");
				Builder.CreateStore(outV, &*AggregatedOutArgIt, true);
			}
		}
	}
}
/// If the original function has debug info, we have to add a debug location
/// to the new branch instruction from the artificial entry block.
/// We use the debug location of the first instruction in the extracted
/// blocks, as there is no other equivalent line in the source code.
static void applyFirstDebugLoc(Function *oldFunction,
                               ArrayRef<BasicBlock *> Blocks,
                               Instruction *BranchI) {
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

// :note: compiled from llvm-21 but modified for different in/out aggregation
void HwtHlsCodeExtractor::emitFunctionBody(const ValueSet &inputs,
		const ValueSet &outputs, const ValueSet &StructValues,
		llvm::Function *newFunction, llvm::StructType *StructArgTy,
		llvm::BasicBlock *header, const ValueSet &SinkingCands,
		llvm::SmallVectorImpl<llvm::Value*> &NewValues) {
	Function *oldFunction = header->getParent();
	LLVMContext &Context = oldFunction->getContext();
	// The new function needs a root node because other nodes can branch to the
	// head of the region, but the entry node of a function cannot have preds.
	BasicBlock *newFuncRoot = BasicBlock::Create(Context, "newFuncRoot",
			newFunction);
	 _emitFunctionBody_sink(SinkingCands, newFuncRoot);
	 IRBuilder<> Builder(Context);
	//if (beginSyncAlloca) {
	//	Type * Ty1b = Builder.getInt1Ty();
	//	auto headerIP = header->getFirstNonPHIOrDbgOrAlloca();
	//	Builder.SetInsertPoint(headerIP); // load from inputs at the beginning of the extracted section
	//	Builder.CreateLoad(Ty1b, beginSyncAlloca, /*isVolatile*/true);
	//}

	_emitFunctionBody_UpdateInputUsesToUseNewArgs(Builder, newFunction, inputs,
			StructInValues, NewValues);

	moveCodeToFunction(newFunction);
	_emitFunctionBody_replaceUsesOfInputs(inputs, NewValues);
	_emitFunctionBody_return(newFunction, header, newFuncRoot);

	// Connect newFunction entry block to new header.
	BranchInst *BranchI = BranchInst::Create(header, newFuncRoot);
	applyFirstDebugLoc(oldFunction, Blocks.getArrayRef(), BranchI);
	size_t outArgOffset = inputs.size() - StructInValues.size() + (StructInValues.size() ? 1 : 0);
	Function::arg_iterator ScalarArgOutIt = std::ranges::next(newFunction->arg_begin(), outArgOffset);
	_emitFunctionBody_constructOutStores(Builder, newFunction, outputs,
			StructOutValues, ScalarArgOutIt);

	// setDoesNotReturn(); is not applied because it would make code after call unreachable
	//  but later we will remove this call from oldFunction and use channel
	//  communincation instead, that is why the code fater this call would be always reachable
}


}
