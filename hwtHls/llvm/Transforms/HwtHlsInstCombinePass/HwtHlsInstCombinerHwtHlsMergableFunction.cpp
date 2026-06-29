// :see: also HwtHlsSimplifyCFGPass_phiToLogicalExpr
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerHwtHlsMergableFunction.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/ConstantRange.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsHoisting.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

Value* getStateInOfMergableFunction(llvm::CallInst &I) {
	// expects args in format: fnId, stateIn, dataIn, mask
	return I.getArgOperand(1);
}

Value* getMaskOfMergableFunction(llvm::CallInst &I) {
	// expects args in format: fnId, stateIn, dataIn, mask
	assert(I.arg_size() == 4);
	return I.getArgOperand(3);
}

Value* getDataOfMergableFunction(llvm::CallInst &I) {
	// expects args in format: fnId, stateIn, dataIn, mask
	assert(I.arg_size() == 4);
	return I.getArgOperand(2);
}

//std::string rtrim_digits(const std::string &_s) {
//	auto s = _s; // copy
//	auto it = std::find_if(s.rbegin(), s.rend(), [](char c) {
//		return !std::isdigit<char>(c, std::locale::classic());
//	});
//	s.erase(it.base(), s.end());
//	return s;
//}

bool isSameMergableFnCall(llvm::CallInst &I, llvm::CallInst &I2) {
	auto *F = I.getCalledFunction();
	auto fnId = I.getArgOperand(0);
	if (F->hasMetadata(
			HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData)) {
		auto F2 = I2.getCalledFunction();
		if (!F2->hasMetadata(
				HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData)) {
			return false;
		}
		return fnId == I2.getArgOperand(0);
	} else {
		llvm_unreachable("NotImplemented type of mergable function");
	}
}

bool isUsedOnlySameMergableFnCallOrInstr(llvm::CallInst &CallI,
		llvm::Instruction &I, Value &V) {
	for (User *u : V.users()) {
		if (u == &I) {
			continue;
		}
		if (auto c = dyn_cast<CallInst>(u)) {
			if (isSameMergableFnCall(CallI, *c))
				continue;
		}
		return false;
	}
	return true;
}

CallInst* CreateMergedMergableCall(llvm::IRBuilderBase &Builder,
		CallInst &call0, Instruction *insertPoint, ConcatMemberVector &newMask,
		ConcatMemberVector &newData) {
	Builder.SetInsertPoint(insertPoint);
	auto stateIn = getStateInOfMergableFunction(call0);
	// inline stateIn function if it is same call not used anywhere else
	for (;;) {
		if (!stateIn->hasNUndroppableUses(1))
			break;
		auto stateInC = dyn_cast<CallInst>(stateIn);
		if (!stateInC)
			break;
		if (!isSameMergableFnCall(call0, *stateInC))
			break;
		// satateIn is mergable function call, prepend its
		// [todo] first extract all data in high to low format, then merge it to newData/newMask in low to high format
		//        to avoid reallocation of ConcatMemberVector which supports only push_back
		ConcatMemberVector newMaskTmp;
		ConcatMemberVector newDataTmp;
		newDataTmp.push_back_flattened(getDataOfMergableFunction(*stateInC));
		newMaskTmp.push_back_flattened(getMaskOfMergableFunction(*stateInC));
		for (auto m : newMask.members) {
			newMaskTmp.push_back(m);
		}
		for (auto d : newData.members) {
			newDataTmp.push_back(d);
		}
		newMask = newMaskTmp;
		newData = newDataTmp;
		stateIn = getStateInOfMergableFunction(*stateInC);
	}
	auto fnId = call0.getArgOperand(0);
	auto *F = call0.getCalledFunction();
	auto _data = newData.resolveValue(Builder, nullptr, insertPoint);
	auto _mask = newMask.resolveValue(Builder, nullptr, insertPoint);
	assert(
			_data->getType()->getIntegerBitWidth()
					% _mask->getType()->getIntegerBitWidth() == 0);
	std::array<Type*, 4> Tys = { fnId->getType(), stateIn->getType(),
			_data->getType(), _mask->getType() };
	Module *M = F->getParent();
	// :note: storing to std::string is required, if stored to StringRef the string is deallocated immediately
	auto FnName = F->getName().rtrim("0123456789").str()
			+ std::to_string(_data->getType()->getIntegerBitWidth());
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(FnName, F->getReturnType(), Tys[0], Tys[1],
					Tys[2], Tys[3]).getCallee());
	TheFn->getArg(0)->setName("fnId");
	TheFn->getArg(1)->setName("state");
	TheFn->getArg(2)->setName("data");
	TheFn->getArg(3)->setName("mask");
	TheFn->copyAttributesFrom(F);
	TheFn->copyMetadata(F, 0);

	CallInst *res = Builder.CreateCall(TheFn, { fnId, stateIn, _data, _mask });
	res->copyMetadata(call0);
	res->copyIRFlags(&call0);
	res->setAttributes(call0.getAttributes());
	return res;
}

// try merge multiple calls of function marked with metadataName_mergableFunction_statePlusMaskedData
// :note: I is top (root) of the expression tree and the search continues down to uses
llvm::Instruction* HwtHlsInstCombiner::tryReduceMergableFunctionInSequence(
		llvm::CallInst &I) {
	if (!Options.mergeMergableFunctionCalls)
		return nullptr;

	auto *F = I.getCalledFunction();
	if (!F->hasMetadata(
			HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData))
		return nullptr;

	auto stateSrc = getStateInOfMergableFunction(I);
	auto stateSrcI = dyn_cast<CallInst>(stateSrc); // same instruction which is going to be merged with I
	if (!stateSrcI)
		return nullptr;

	if (!isSameMergableFnCall(I, *stateSrcI))
		return nullptr;

	if (!isUsedOnlySameMergableFnCallOrInstr(I, I, *stateSrcI))
		return nullptr; // allow only the case where the I is the only user of predecessor mergable function

	Builder.SetInsertPoint(stateSrcI);
	auto &BB = *I.getParent();
	auto &SrcBB = *stateSrcI->getParent();

	ConcatMemberVector newMask;
	ConcatMemberVector newData;
	newMask.push_back_flattened(getMaskOfMergableFunction(*stateSrcI));
	newData.push_back_flattened(stateSrcI->getArgOperand(2));
	// fnId remains the same, state in is used from stateSrc
	if (&BB == &SrcBB) {
		auto *d = I.getArgOperand(2);
		auto *m = getMaskOfMergableFunction(I);
		if (d != stateSrcI && !hoistIntoDominatingBlock(*d, *stateSrcI, DT)) {
			return nullptr;
		}
		if (m != stateSrcI && !hoistIntoDominatingBlock(*m, *stateSrcI, DT)) {
			return nullptr;
		}
		newMask.push_back_flattened(m);
		newData.push_back_flattened(d);

	} else if (any_of(successors(&SrcBB), [&BB](BasicBlock *SucBB) {
		return SucBB == &BB;
	})) {
		auto srcTerm = SrcBB.getTerminator();
		auto srcTermBr = dyn_cast<BranchInst>(srcTerm);
		if (!srcTermBr)
			return nullptr;
		Value *IExeCond = nullptr;
		bool conditionNegated = false;
		if (srcTermBr->isConditional()) {
			IExeCond = srcTermBr->getCondition();
			if (srcTermBr->getSuccessor(0) != &BB) {
				conditionNegated = true;
			}
		}

		auto *d = I.getArgOperand(2);
		auto *m = getMaskOfMergableFunction(I);
		if (d != stateSrcI && !hoistIntoDominatingBlock(*d, *stateSrcI, DT)) {
			return nullptr;
		}
		if (m != stateSrcI && !hoistIntoDominatingBlock(*m, *stateSrcI, DT)) {
			return nullptr;
		}

		if (IExeCond) {
			// if execution of next step is conditional update mask with the condition
			// to perform operation only if the I is truly executed
			if (IExeCond != stateSrcI
					&& !hoistIntoDominatingBlock(*IExeCond, *stateSrcI, DT)) {
				return nullptr;
			}
			auto maskZero = ConstantInt::get(m->getType(), 0);
			if (conditionNegated) {
				m = Builder.CreateSelect(IExeCond, maskZero, m);
			} else {
				m = Builder.CreateSelect(IExeCond, m, maskZero);
			}
		}
		newMask.push_back_flattened(m);
		newData.push_back_flattened(d);
	} else {
		return nullptr;
	}
	auto res = CreateMergedMergableCall(Builder, *stateSrcI, stateSrcI, newMask,
			newData);
	// both "stateSrcI" and "I" are replaced with new widened instruction "res"
	Worklist.add(stateSrcI); // must add explicitly because replaceInstUsesWith does not add it
	//replaceInstUsesWith(*stateSrcI, res);
	auto r = replaceInstUsesWith(I, res);
	return r;
}

///*
// * .. code-block::llvm
// *     %step0 = call i16 @hwtHls.pyObjectPlaceholder.0.addMasked.i16.i16(i32 0, i16 0, i16 %dataIn)
// *     %res = select i1 %step0.en, i16 %step0, i16 0
// *     ; to
// *     %res = call i16 @hwtHls.pyObjectPlaceholder.0.addMasked.i16.i16(i32 0, i16 0, i16 %dataIn, i1 %step0.en)
// * */
//llvm::Instruction* HwtHlsInstCombiner::_tryReduceMergableFunctionInSelect_optinalToMasked(
//		llvm::SelectInst &SI, CallInst *T, std::optional<CallInst*> _F) {
//	bool conditionNegated;
//	CallInst *call0;
//	Value *otherV;
//	if (T) {
//		conditionNegated = false;
//		call0 = T;
//		otherV = SI.getFalseValue();
//	} else {
//		conditionNegated = true;
//		auto F = dyn_cast<CallInst>(SI.getFalseValue());
//		if (!F)
//			return nullptr;
//		if (!F->getCalledFunction()->hasMetadata(
//				HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData))
//			return nullptr;
//		call0 = F;
//		otherV = SI.getTrueValue();
//	}
//
//	errs() << "_tryReduceMergableFunctionInSelect_optinalToMasked: " << SI
//			<< "\n";
//	if (!isUsedOnlySameMergableFnCallOrInstr(*call0, SI, *call0))
//		return nullptr;
//	if (getStateInOfMergableFunction(*call0) != otherV)
//		return nullptr;
//	if (!hoistIntoDominatingBlock(SI, *call0->getNextNode(), DT)) {
//		// try hoist select just after call0 so it is asserted that replacement of select
//		// dominates all uses of call0 as well
//		return nullptr;
//	}
//	ConcatMemberVector newMask;
//	ConcatMemberVector newData;
//	auto m = getMaskOfMergableFunction(*call0);
//	auto maskZero = ConstantInt::get(m->getType(), 0);
//	Value *IExeCond = SI.getCondition();
//	if (conditionNegated) {
//		m = Builder.CreateSelect(IExeCond, maskZero, m);
//	} else {
//		m = Builder.CreateSelect(IExeCond, m, maskZero);
//	}
//
//	newMask.push_back_flattened(m);
//	newData.push_back_flattened(call0->getArgOperand(2));
//	auto res = CreateMergedMergableCall(Builder, *call0, &SI, newMask, newData);
//	Worklist.add(call0);
//	replaceInstUsesWith(*call0, res);
//	return replaceInstUsesWith(SI, res);
//}

bool condensateSequenceOfInstructionsWithDominanceGuaranteed(
		llvm::ArrayRef<Instruction*> instructions, const DominatorTree &DT) {
	Instruction *IP = instructions.front()->getNextNode(); // next because hoistIntoDominatingBlock moves before insertPoint
	assert(IP);
	bool first = true;
	for (Instruction *I : instructions) {
		if (first)
			continue;
		if (IP != I)
			// try to hoist instruction so it is directly after last instruction from instructions array
			if (!hoistIntoDominatingBlock(*I, *IP, DT))
				return false;
		IP = I->getNextNode();
	}
	return true;
}

// result[0] is a top of the tree
bool HwtHlsInstCombiner::_tryReduceMergableFunctionInSelect_detect(
		llvm::SelectInst &topSI, SmallVector<MergableFunctionChainItem> &result,
		Value *&stateIn) {
	Value *top = &topSI;
	auto isCompatibleCall =
			[&result](SelectInst *SI, llvm::CallInst *CI) {
				if (result.empty()) {
					if (!CI->hasNUndroppableUses(1)) {
						// expecting use only in top select or phi
						// phis are allowed because the calls in the loop
						// are often tree-like but with top node use used by select and the parent loop phi
						bool otherUsersAreJustPhiNodes = true;
						for (auto u : CI->users()) {
							if (SI != u && !isa<PHINode>(u)) {
								otherUsersAreJustPhiNodes = false;
								break;
							}
						}
						if (!otherUsersAreJustPhiNodes)
							return false;
					}
					if (!CI->getCalledFunction()->hasMetadata(
							HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData)) {
						return false;
					}
				} else {
					auto prevCall = result.back().mergableFnCall;
					if (!CI->hasNUndroppableUses(2)) {
						// expecting select and this call stateIn
						return false;
					}
					if (!isSameMergableFnCall(*prevCall, *CI)) {
						return false;
					}
					if (getStateInOfMergableFunction(*prevCall) != CI)
						return false;
				}
				return true;
			};
	while (auto SI = dyn_cast<SelectInst>(top)) {
		auto T = dyn_cast<CallInst>(SI->getTrueValue());
		MergableFunctionChainItem item;
		item.enCondition = SI->getCondition();
		if (T && isCompatibleCall(SI, T)) {
			item.mergableFnCall = T;
			item.enConditionNegated = false;
			top = SI->getFalseValue();
		} else if (auto F = dyn_cast<CallInst>(SI->getFalseValue())) {
			if (!isCompatibleCall(SI, F))
				break;
			item.mergableFnCall = F;
			item.enConditionNegated = true;
			top = SI->getTrueValue();
		} else {
			// true of false value of SelectInst is not compatible call of mergable function, this SelectInst is stateIn
			break;
		}
		result.push_back(item);
	}
	stateIn = top;
	return !result.empty();
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceMergableFunctionInSelect(
		llvm::SelectInst &SI) {
	if (!Options.mergeMergableFunctionCalls)
		return nullptr;
	if (SI.getTrueValue() == SI.getFalseValue()
			|| isa<Constant>(SI.getCondition()))
		return nullptr; // skip too simple cases handled elsewhere

	//auto T = dyn_cast<CallInst>(SI.getTrueValue());
	//if (!T)
	//	return _tryReduceMergableFunctionInSelect_optinalToMasked(SI, nullptr,
	//			{ });
	//if (!T->getCalledFunction()->hasMetadata(
	//		HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData))
	//	return _tryReduceMergableFunctionInSelect_optinalToMasked(SI, nullptr,
	//			{ });
	//
	//auto F = dyn_cast<CallInst>(SI.getFalseValue());
	//if (!F)
	//	return _tryReduceMergableFunctionInSelect_optinalToMasked(SI, T, { });
	//if (T->getParent() != F->getParent())
	//	return _tryReduceMergableFunctionInSelect_optinalToMasked(SI, T, { }); // only support the case with both in the same block
	//if (!isSameMergableFnCall(*T, *F))
	//	return _tryReduceMergableFunctionInSelect_optinalToMasked(SI, T, { });
	//
	ConcatMemberVector newMask;
	ConcatMemberVector newData;
	//CallInst *fnCall0;
	//CallInst *fnCall1; // call enabled by condition of this SelectI
	SmallVector<MergableFunctionChainItem> result;
	Value *stateIn;
	if (!_tryReduceMergableFunctionInSelect_detect(SI, result, stateIn))
		return nullptr;
	for (const MergableFunctionChainItem &r : reverse(result)) {
		// m & SI.cond
		auto m = getMaskOfMergableFunction(*r.mergableFnCall);
		auto maskZero = ConstantInt::get(m->getType(), 0);
		if (r.enConditionNegated) {
			m = Builder.CreateSelect(r.enCondition, maskZero, m);
		} else {
			m = Builder.CreateSelect(r.enCondition, m, maskZero);
		}
		newMask.push_back_flattened(m);
		newData.push_back_flattened(
				getDataOfMergableFunction(*r.mergableFnCall));
	}

	//if (getStateInOfMergableFunction(*T) == F) {
	//	// case c? T(.., F, ...) : F
	//	//      T is an optionally performed on result of F
	//	fnCall0 = F;
	//	fnCall1 = T;
	//} else if (getStateInOfMergableFunction(*F) == T) {
	//	// case c? T : F(.., T, ...)
	//	//      F is an optionally performed on result of T
	//	fnCall0 = T;
	//	fnCall1 = F;
	//} else {
	//	// T/F calls are not stateIn of each other
	//	return nullptr;
	//}
	//// select or other mergable fn must be only user of fnCall0/fnCall1 because we
	//// want to avoid case where we duplicate top of the mergable fn tree
	//bool c0HasMoreUsers = !fnCall0->hasNUndroppableUses(2); // select and c1HasMoreUsers stateIn
	//bool c1HasMoreUsers = !fnCall1->hasNUndroppableUses(1);
	//if (c0HasMoreUsers || c1HasMoreUsers)
	//	return nullptr;
	//if ((c0HasMoreUsers
	//		|| isUsedOnlySameMergableFnCallOrInstr(*fnCall0, SI, *fnCall0))
	//		&& (c1HasMoreUsers
	//				|| isUsedOnlySameMergableFnCallOrInstr(*fnCall0, SI,
	//						*fnCall1))) {
	//	if (c0HasMoreUsers || c1HasMoreUsers) {
	//		if (c0HasMoreUsers && c1HasMoreUsers
	//				&& fnCall0->getParent() != fnCall1->getParent()) {
	//			return nullptr;
	//		}
	//		if (DT.dominates(fnCall0, fnCall1)) {
	//			std::array<Instruction*, 3> instrs = {fnCall0, fnCall1, &SI};
	//			if (!condensateSequenceOfInstructionsWithDominanceGuaranteed(instrs, DT))
	//				return nullptr;
	//		} else if (DT.dominates(fnCall1, fnCall0)) {
	//			std::array<Instruction*, 3> instrs = {fnCall1, fnCall0, &SI};
	//			if (!condensateSequenceOfInstructionsWithDominanceGuaranteed(instrs, DT))
	//				return nullptr;
	//		} else {
	//			return nullptr;
	//		}
	//	}
	//} else {
	//	// can not resolve insertion point for new fn
	//	return nullptr;
	//}
	//Builder.SetInsertPoint(&SI);
	//if (!isUsedOnlySameMergableFnCallOrInstr(*fnCall0, SI, *fnCall0)
	//		|| !isUsedOnlySameMergableFnCallOrInstr(*fnCall0, SI, *fnCall1))
	//	return nullptr;
	//newMask.push_back_flattened(getMaskOfMergableFunction(*fnCall0));
	//newData.push_back_flattened(fnCall0->getArgOperand(2));
	//auto m = getMaskOfMergableFunction(*fnCall1);
	//m = Builder.CreateAnd(Builder.CreateSExt(SI.getCondition(), m->getType())); // m & SI.cond
	//newMask.push_back_flattened(m);
	//newData.push_back_flattened(fnCall1->getArgOperand(2));
	auto res = CreateMergedMergableCall(Builder, *result.back().mergableFnCall,
			&SI, newMask, newData);
	//Worklist.add(fnCall0);
	//Worklist.add(fnCall1);
	//Worklist.pushUsersToWorkList(*fnCall0);
	//Worklist.pushUsersToWorkList(*fnCall1);
	return replaceInstUsesWith(SI, res);
}

}
