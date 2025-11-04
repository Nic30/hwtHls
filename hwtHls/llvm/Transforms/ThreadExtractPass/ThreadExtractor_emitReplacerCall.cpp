#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>

#include <iterator>
#include <llvm/Analysis/BlockFrequencyInfo.h>
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/IR/Module.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

#define DEBUG_TYPE "hwtHls::ThreadExtractor"

namespace hwtHls {


class HwtHlsIoMDChannelUpdateCtx {
	MutableArrayRef<ArgToAddToParentFn> argsToAddToParentFn;
	size_t newParentArgIndexOffseet;
	MutableArrayRef<HwtHlsIoMetadata> newFnHwtHlsIoMD;
	Function &oldFunction;
	Function *newFunction;
	size_t &oldFunctionNewArgI;

public:
	HwtHlsIoMDChannelUpdateCtx(
			MutableArrayRef<ArgToAddToParentFn> argsToAddToParentFn,
			size_t newParentArgIndexOffseet,
			MutableArrayRef<HwtHlsIoMetadata> newFnHwtHlsIoMD,
			Function &oldFunction, Function *newFunction,
			size_t &oldFunctionArgI) :
			argsToAddToParentFn(argsToAddToParentFn), newParentArgIndexOffseet(
					newParentArgIndexOffseet), newFnHwtHlsIoMD(newFnHwtHlsIoMD), oldFunction(
					oldFunction), newFunction(newFunction), oldFunctionNewArgI(
					oldFunctionArgI) {
	}
	void updateForChannelIoArg(IODirection dirForNewFn, size_t newFnArgI,
			std::optional<size_t> width, std::optional<AllocaInst*> tmpAlloca) {
		assert(newFnArgI < newFnHwtHlsIoMD.size());
		size_t oldFnNewArgI = newParentArgIndexOffseet + oldFunctionNewArgI - oldFunction.arg_size();
		assert(oldFnNewArgI < argsToAddToParentFn.size());
		if (!width.has_value() && tmpAlloca.has_value())
			width =
					tmpAlloca.value()->getAllocatedType()->getScalarSizeInBits();
		HwtHlsIoMetadata &childMd = newFnHwtHlsIoMD[newFnArgI];
		assert(childMd.direction == dirForNewFn);
		childMd.otherThreadFn = &oldFunction;
		childMd.otherArgIndex = newParentArgIndexOffseet + oldFunctionNewArgI;
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
	}
};

CallInst *HwtHlsCodeExtractor::emitReplacerCall(
    const ValueSet &inputs, const ValueSet &outputs,
    const ValueSet &StructValues, Function *newFunction,
    StructType *StructArgTy, Function *oldFunction, BasicBlock *ReplIP,
    BlockFrequency EntryFreq, ArrayRef<Value *> LifetimesStart,
    std::vector<Value *> &Reloads) {
	LLVMContext &Context = oldFunction->getContext();
	Module *M = oldFunction->getParent();
	const DataLayout &DL = M->getDataLayout();

	// This takes place of the original loop
	BasicBlock *codeReplacer =
		BasicBlock::Create(Context, "codeRepl", oldFunction, ReplIP);
	if (AllocationBlock)
	  assert(AllocationBlock->getParent() == oldFunction &&
			 "AllocationBlock is not in the same function");
	BasicBlock *AllocaBlock =
		AllocationBlock ? AllocationBlock : &oldFunction->getEntryBlock();

	// Update the entry count of the function.
	if (BFI)
		BFI->setBlockFreq(codeReplacer, EntryFreq);

	size_t oldFunctionNewArgI = 0; // current index of newly added argument to parent function
	HwtHlsIoMDChannelUpdateCtx channelMdUpdater(argsToAddToParentFn, newParentArgIndexOffseet,
			newFnHwtHlsIoMD, *oldFunction, newFunction, oldFunctionNewArgI);

	std::vector<Value *> params;
	// Add inputs as params, or to be filled into the struct
	// (params are passed trough tmp AllocaInst and may be aggregated together using concat)
	auto inTmpAllocaIP = AllocaBlock->getFirstInsertionPt();

	IRBuilder<> Builder(Context);
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
					channelMdUpdater.updateForChannelIoArg(
							IODirection::IO_DIR_IN, ScalarInputArgNo, width,
							ai);
					++oldFunctionNewArgI;
				}
			} else {
				size_t width = input->getType()->getIntegerBitWidth();
				auto alloca = new AllocaInst(IntegerType::get(Context, width),
						DL.getAllocaAddrSpace(), nullptr, input->getName(),
						inTmpAllocaIP);
				Builder.SetInsertPoint(codeReplacer, codeReplacer->end());
				Builder.CreateStore(input, alloca, true);
				channelMdUpdater.updateForChannelIoArg(IODirection::IO_DIR_IN,
						ScalarInputArgNo, width, alloca);
				params.push_back(alloca);
				++oldFunctionNewArgI;
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
		AggregatedInTmp = new AllocaInst(IntegerType::get(Context, width),
				DL.getAllocaAddrSpace(), nullptr, "agrInArg", inTmpAllocaIP);
		channelMdUpdater.updateForChannelIoArg(IODirection::IO_DIR_IN,
				ScalarInputArgNo, width, AggregatedInTmp);
		++oldFunctionNewArgI;
		++ScalarInputArgNo;
	}

	// Create allocas for the outputs
	unsigned ScalarOutputArgNo = 0;
	std::vector<Value *> ReloadOutputs;
	auto tmpAllocaIp = codeReplacer->getParent()->front().front().getIterator();
	for (Value *output : outputs) {
		if (AggregateOutputs && !ExcludeArgsFromAggregate.contains(output)) {
			StructOutValues.insert(output);
		} else {
			AllocaInst *alloca = new AllocaInst(output->getType(),
					DL.getAllocaAddrSpace(), nullptr,
					output->getName() + ".loc", tmpAllocaIp);
			ReloadOutputs.push_back(alloca);
			params.push_back(alloca);

			channelMdUpdater.updateForChannelIoArg(IODirection::IO_DIR_OUT,
					ScalarInputArgNo, output->getType()->getScalarSizeInBits(),
					alloca);
			assert(!isa<Argument>(output));
			++oldFunctionNewArgI;
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
		AggregatedOutTmp = new AllocaInst(IntegerType::get(Context, width),
				DL.getAllocaAddrSpace(), nullptr, "AggregatedOutTmp",
				tmpAllocaIp);
		// newly generated alloca for output
		channelMdUpdater.updateForChannelIoArg(IODirection::IO_DIR_OUT,
				ScalarInputArgNo, { }, AggregatedOutTmp);
		++oldFunctionNewArgI;
		++ScalarOutputArgNo;
	}

	if (AggregateInputs && !StructInValues.empty()) {
		params.push_back(AggregatedInTmp);
		// Store aggregated inputs in the struct.
		Builder.SetInsertPoint(codeReplacer);
		auto conc = CreateBitConcat(&Builder, StructInValues.getArrayRef());
		Builder.CreateStore(conc, AggregatedInTmp, true);
	}
	{
		// cast addr spaces as specified in newFunction
		size_t expectedParamAddrSpace = 1;
		for (auto &p : params) {
			auto t = p->getType();
			assert(t->isPointerTy());
			if (t->getPointerAddressSpace() != expectedParamAddrSpace) {
				auto *aSpaceCast = new AddrSpaceCastInst(p,
						PointerType::get(Context, expectedParamAddrSpace),
						"arg.ascast");
				aSpaceCast->insertInto(codeReplacer, codeReplacer->end());
				p = aSpaceCast;
			}
			expectedParamAddrSpace++;
		}
	}
	// Emit the call to the function
	CallInst *call = CallInst::Create(newFunction, params,
			ExtractedFuncRetVals.size() > 1 ? "targetBlock" : "", codeReplacer);


	// Set swifterror parameter attributes.
	for (unsigned SwiftErrArgNo : SwiftErrorArgs) {
		call->addParamAttr(SwiftErrArgNo, Attribute::SwiftError);
		newFunction->addParamAttr(SwiftErrArgNo, Attribute::SwiftError);
	}

	// Add debug location to the new call, if the original function has debug
	// info. In that case, the terminator of the entry block of the extracted
	// function contains the first debug location of the extracted function,
	// set in extractCodeRegion.
	if (codeReplacer->getParent()->getSubprogram()) {
		if (auto DL =
				newFunction->getEntryBlock().getTerminator()->getDebugLoc())
			call->setDebugLoc(DL);
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
						true, "aggregatedOut.ld");
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
					Out.getName() + ".reload", true, codeReplacer);
		}
		Reloads.push_back(load);
		// [todo]
		// std::vector<User*> Users(Out.user_begin(), Out.user_end());
		// for (User *U : Users) {
		// 	Instruction *inst = cast<Instruction>(U);
		// 	if (!Blocks.count(inst->getParent()))
		// 		inst->replaceUsesOfWith(&Out, load);
		// }
	}
	_emitReplacerCall_constructSwitch(newFunction, codeReplacer, call);
	// Insert lifetime markers around the reloads of any output values. The
	// allocas output values are stored in are only in-use in the codeRepl block.
	//insertLifetimeMarkersSurroundingCall(M, ReloadOutputs, ReloadOutputs, call);

	return call;
}

}
