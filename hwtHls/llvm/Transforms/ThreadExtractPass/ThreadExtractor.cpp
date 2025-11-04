#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/BlockFrequencyInfo.h>
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <llvm/ADT/SetVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/functionMutating.h>

using namespace llvm;
using ProfileCount = Function::ProfileCount;

#define DEBUG_TYPE "hwtHls::ThreadExtractor"

namespace hwtHls {

// :see: CodeExtractor::CodeExtractor
HwtHlsCodeExtractor::HwtHlsCodeExtractor(llvm::ArrayRef<llvm::BasicBlock*> BBs, //
		llvm::SmallVector<ArgToAddToParentFn> &argsToAddToParentFn, //
		bool extractedIsInLoop,           //
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
		hwtHls::llvmSrc::CodeExtractor(BBs, DT, AggregateArgs, BFI, BPI, AC,
				AllowVarArgs, false/*AllowAlloca*/, AllocationBlock, Suffix,
				false/*ArgsInZeroAddressSpace*/),           //
		AggregateInputs(AggregateInputs),           //
		AggregateOutputs(AggregateOutputs),         //
		beginMayBeAsync(beginMayBeAsync),           //
		endMayBeAsync(endMayBeAsync),               //
		inputBufferCapacity(inputBufferCapacity),   //
		outputBufferCapacity(outputBufferCapacity), //
		extractedIsInLoop(extractedIsInLoop),       //
		argsToAddToParentFn(argsToAddToParentFn),   //
		newParentArgIndexOffseet(BBs[0]->getParent()->arg_size() + argsToAddToParentFn.size()), //
		beginSyncFreeze(nullptr),                   //
		endSyncFreeze(nullptr),                     //
		returnValFreeze(nullptr) {
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

void HwtHlsCodeExtractor::_discardAggragationIfJustOneInOrOut(
		const ValueSet &inputs, const ValueSet &outputs) {
	if (AggregateInputs) {
		size_t aggregatedInputCnt = 0;
		for (auto inp : inputs) {
			if (isa<Argument>(inp)) {
				ExcludeArgsFromAggregate.insert(inp);
			} else {
				// assert(!inp->getType()->isPointerTy());
				aggregatedInputCnt++;
			}
		}
		if (aggregatedInputCnt <= 1)
			AggregateInputs = false;
	}
	if (AggregateOutputs && outputs.size() <= 1)
		AggregateOutputs = false;
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

// // The tmp alloca is generated for outputs and the use of outputs was overridden to use this new alloca
// // bb0:
// //   %o0.loc = alloca i1, align 1 ; newly generated tmp alloca for output
// //   %o0.orig = alloca i1, align 1
// //   store volatile i1 true, ptr %orig.out0, align 1
// // CodeRepl:
// //   call void @llvm.lifetime.start.p0(i64 -1, ptr %o0.loc)
// //   call void @noDeps.t1(ptr addrspace(2) %dataOut1, ptr %main.t1, ptr %o0.loc)
// //   %o0.reload = load i1, ptr %o0.loc, align 1
// //   call void @llvm.lifetime.end.p0(i64 -1, ptr %.loc)
// //   br label %bb.main.t1

void HwtHlsCodeExtractor::wrapExtractedInInfLoop(Function *newFunction) {
	BasicBlock * newFuncRoot = &newFunction->getEntryBlock();
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
			toTopInfLoopBranchI->insertBefore(ret->getIterator());
			ret->eraseFromParent();
			//if (endSyncAlloca) {
			//	Builder.SetInsertPoint(toTopInfLoopBranchI);
			//	Builder.CreateStore(ConstantInt::get(Ty1b, 1),
			//			endSyncAlloca, /*isVolatile*/true);
			//}
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
	newFunction->setDoesNotReturn();
}

// finalize thread extraction by deletion of CallInst which was temporally created for compatibility with llvm::CodeExtractor
void HwtHlsCodeExtractor::deleteCallInst(Function *newFunction) {
	CallInst *TheCall = nullptr;
	for (auto u : newFunction->users()) {
		if (auto CI = dyn_cast<CallInst>(u)) {
			assert(!TheCall);
			TheCall = CI;
		}
	}
	SmallVector<Value*> args(TheCall->args());
	TheCall->eraseFromParent(); // because the load/store to channels of thread replaces the call
	for (auto &a : args) {
		if (auto ai = dyn_cast<AddrSpaceCastInst>(a)) {
			if (ai->hasNUses(0)) {
				ai->eraseFromParent();
			}
		}
	}
}

void HwtHlsCodeExtractor::deleteTmpValues() {
	std::array<FreezeInst*, 3> tmpVals = {beginSyncFreeze, endSyncFreeze, returnValFreeze};
	for (FreezeInst *I: tmpVals) {
		if (I) {
			I->replaceAllUsesWith(I->getOperand(0));
			I->eraseFromParent();
		}
	}
}

llvm::Function* HwtHlsCodeExtractor::extractCodeRegion(
		const llvm::CodeExtractorAnalysisCache &CEAC,
		ValueSet &Inputs, ValueSet &Outputs) {
	Function* newFunction = llvmSrc::CodeExtractor::extractCodeRegion(CEAC,  Inputs, Outputs);
	if (extractedIsInLoop)
		wrapExtractedInInfLoop(newFunction);
	deleteCallInst(newFunction);
	deleteTmpValues();
	//argsToAddToParentFn.insert(argsToAddToParentFn.end(),
	//		_argsToAddToParentFn.begin(), _argsToAddToParentFn.end());

	HwtHlsIoMetadata_set(*newFunction, newFnHwtHlsIoMD);
	return newFunction;
}

}
