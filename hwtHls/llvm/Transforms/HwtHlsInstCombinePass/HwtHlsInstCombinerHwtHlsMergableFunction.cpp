#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <map>

#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/ConstantRange.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsHoisting.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

Value* getMaskOfMergableFunction(llvm::CallInst &I) {
	// expects args in format: fnId, stateIn, dataIn, mask?
	if (I.arg_size() == 4) {
		return I.getArgOperand(3);
	} else {
		assert(I.arg_size() == 3);
		return ConstantInt::getTrue(I.getContext());
	}
}

std::string rtrim_digits(const std::string &_s) {
	auto s = _s; // copy
	auto it = std::find_if(s.rbegin(), s.rend(), [](char c) {
		return !std::isdigit<char>(c, std::locale::classic());
	});
	s.erase(it.base(), s.end());
	return s;
}

// try merge multiple calls of
llvm::Instruction* HwtHlsInstCombiner::tryReduceMergableFunction(
		llvm::CallInst &I) {
	auto *F = I.getCalledFunction();
	if (!F->hasMetadata(
			HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData))
		return nullptr;
	auto fnId = I.getArgOperand(0);
	auto stateSrc = I.getArgOperand(1);
	auto stateSrcI = dyn_cast<CallInst>(stateSrc);
	if (!stateSrcI)
		return nullptr;
	if (F->getName() != stateSrcI->getCalledFunction()->getName()
			|| fnId != stateSrcI->getArgOperand(0))
		return nullptr;
	auto &BB = *I.getParent();
	auto &SrcBB = *stateSrcI->getParent();

	ConcatMemberVector newMask;
	ConcatMemberVector newData;
	// fnId remains the same, state in is used from stateSrc

	if (&BB == &SrcBB) {
		newMask.push_back_flattened(getMaskOfMergableFunction(*stateSrcI));
		newData.push_back_flattened(stateSrcI->getArgOperand(2));

		newMask.push_back_flattened(getMaskOfMergableFunction(I));
		newData.push_back_flattened(I.getArgOperand(2));

	} else if (any_of(successors(&SrcBB), [&BB](BasicBlock *SucBB) {
		return SucBB == &BB;
	})) {
		auto srcTerm = SrcBB.getTerminator();
		auto srcTermBr = dyn_cast<BranchInst>(srcTerm);
		if (!srcTermBr)
			return nullptr;
		Builder.SetInsertPoint(stateSrcI);
		Value *IExeCond = nullptr;
		bool conditionNegated = false;
		if (srcTermBr->isConditional()) {
			IExeCond = srcTermBr->getCondition();
			if (srcTermBr->getSuccessor(0) != &BB) {
				conditionNegated = true;
			}
		}
		newMask.push_back_flattened(getMaskOfMergableFunction(*stateSrcI));
		newData.push_back_flattened(stateSrcI->getArgOperand(2));

		auto *d = I.getArgOperand(2);
		auto *m = getMaskOfMergableFunction(I);
		if (!hoistIntoDominatingBlock(*d, *stateSrcI, DT)) {
			return nullptr;
		}
		if (!hoistIntoDominatingBlock(*m, *stateSrcI, DT)) {
			return nullptr;
		}

		if (IExeCond) {
			if (!hoistIntoDominatingBlock(*IExeCond, *stateSrcI, DT)) {
				return nullptr;
			}
			auto maskZero = ConstantInt::get(m->getType(), 0);
			if (conditionNegated) {
				m = Builder.CreateSelect(IExeCond, maskZero, m);
			} else {
				m = Builder.CreateSelect(IExeCond, m, maskZero);
			}
			Worklist.pushValue(m);
		}
		newMask.push_back_flattened(m);
		newData.push_back_flattened(d);
	} else {
		return nullptr;
	}
	Builder.SetInsertPoint(stateSrcI);
	auto stateIn = stateSrcI->getArgOperand(1);
	auto _data = newData.resolveValue(Builder, nullptr, stateSrcI);
	auto _mask = newMask.resolveValue(Builder, nullptr, stateSrcI);
	std::array<Type*, 4> Tys = {fnId->getType(), stateIn->getType(), _data->getType(), _mask ->getType()};

	Worklist.pushValue(_data);
	Worklist.pushValue(_mask);
	Module*M = F->getParent();
	// :note: storing to std::string is required, if stored to StringRef the string is deallocated immediately
	auto FnName = F->getName().rtrim("0123456789").str() + std::to_string(_data->getType()->getIntegerBitWidth());
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					FnName, F->getReturnType(),
					Tys[0], Tys[1], Tys[2], Tys[3]).getCallee());
	TheFn->getArg(0)->setName("fnId");
	TheFn->getArg(1)->setName("state");
	TheFn->getArg(2)->setName("data");
	TheFn->getArg(3)->setName("mask");
	TheFn->copyAttributesFrom(F);
	TheFn->copyMetadata(F, 0);

	CallInst* res = Builder.CreateCall(TheFn, { fnId, stateIn, _data, _mask });
	res->copyMetadata(I);
	res->copyIRFlags(&I);
	res->setAttributes(I.getAttributes());

	Worklist.pushValue(res);
	Worklist.pushValue(stateSrcI);
	replaceInstUsesWith(*stateSrcI, res);

	return replaceInstUsesWith(I, res);
}

}
