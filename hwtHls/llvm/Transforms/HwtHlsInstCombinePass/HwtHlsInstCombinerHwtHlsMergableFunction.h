#pragma once

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <llvm/IR/Dominators.h>

namespace hwtHls {
	
struct MergableFunctionChainItem {
	llvm::CallInst *mergableFnCall;
	llvm::Value
		*enCondition; // if enConditionNegated==false and enCondition==true the
					  // mergableFnCall is executed
	bool enConditionNegated;
	MergableFunctionChainItem() :
		mergableFnCall(nullptr),
		enCondition(nullptr),
		enConditionNegated(false) {}
};

llvm::Value* getStateInOfMergableFunction(llvm::CallInst &I);
llvm::Value* getMaskOfMergableFunction(llvm::CallInst &I);
llvm::Value* getDataOfMergableFunction(llvm::CallInst &I);
bool condensateSequenceOfInstructionsWithDominanceGuaranteed(
	llvm::ArrayRef<llvm::Instruction *> instructions,
	const llvm::DominatorTree &DT);
// :param call0: bottom most call which also to get called function, metadata
// and stateIn
llvm::CallInst *CreateMergedMergableCall(llvm::IRBuilderBase &Builder,
										 llvm::CallInst &call0,
										 llvm::Instruction *insertPoint,
										 ConcatMemberVector &newMask,
										 ConcatMemberVector &newData);
}