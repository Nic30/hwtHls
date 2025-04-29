#pragma once
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <llvm/IR/PatternMatch.h>
// :note: combiner functions are defined as templates so they can be used with any combiner class without using virtual methods

namespace hwtHls {
template<typename InstructionCombinerT>
llvm::Instruction* tryReduceZExt_onZExt(InstructionCombinerT& IC, llvm::ZExtInst &I) {
	llvm::Value *srcVal;
	if (llvm::PatternMatch::match(I.getOperand(0), llvm::PatternMatch::m_ZExt(llvm::PatternMatch::m_Value(srcVal)))) {
		// flatten nested ZExts
		IC.Builder.SetInsertPoint(&I);
		auto newI = IC.Builder.CreateZExt(srcVal, I.getType());
		return IC.replaceInstUsesWith(I, newI);
	}
	return nullptr;
}

template<typename InstructionCombinerT>
llvm::Instruction* tryReduceConstOpConcat(InstructionCombinerT& IC, llvm::CallInst &CI) {
	llvm::SmallVector<llvm::Value*> newOps;
	llvm::ConstantInt *lastInt = nullptr;
	llvm::UndefValue *lastUndef = nullptr;
	llvm::PoisonValue *lastPoison = nullptr;
	auto &Ctx = CI.getContext();
	for (llvm::Use &_A : CI.args()) {
		auto &A = *_A.get();
		if (auto *ACint = llvm::dyn_cast<llvm::ConstantInt>(&A)) {
			if (lastInt) {
				lastInt = llvm::ConstantInt::get(Ctx,
						ACint->getValue().concat(lastInt->getValue()));
				newOps.back() = lastInt;
			} else {
				lastInt = ACint;
				newOps.push_back(ACint);
			}
			lastUndef = nullptr;
			lastPoison = nullptr;
		} else if (auto *poison = llvm::dyn_cast<llvm::PoisonValue>(&A)) {
			if (lastPoison) {
				size_t newWidth = lastPoison->getType()->getIntegerBitWidth()
						+ poison->getType()->getIntegerBitWidth();
				newOps.back() = lastPoison = llvm::PoisonValue::get(
						llvm::IntegerType::get(Ctx, newWidth));
			} else {
				lastPoison = poison;
				newOps.push_back(poison);
			}
			lastInt = nullptr;
			lastUndef = nullptr;
		} else if (auto *undef = llvm::dyn_cast<llvm::UndefValue>(&A)) {
			if (lastUndef) {
				size_t newWidth = lastUndef->getType()->getIntegerBitWidth()
						+ undef->getType()->getIntegerBitWidth();
				newOps.back() = lastUndef = llvm::UndefValue::get(
						llvm::IntegerType::get(Ctx, newWidth));
			} else {
				lastUndef = undef;
				newOps.push_back(undef);
			}
			lastInt = nullptr;
			lastPoison = nullptr;
		} else {
			newOps.push_back(&A);
			lastInt = nullptr;
			lastUndef = nullptr;
			lastPoison = nullptr;
		}
	}
	if (newOps.size() < CI.arg_size()) {
		IC.Builder.SetInsertPoint(&CI);
		auto replacement = CreateBitConcat(&IC.Builder, newOps);
		return IC.replaceInstUsesWith(CI, replacement);
	}
	return nullptr;
}

template<typename InstructionCombinerT>
llvm::Instruction* tryReduceConstOpBitRangeGet(InstructionCombinerT& IC, llvm::CallInst &CI) {
	auto srcOp = CI.getArgOperand(0);
	auto indexOp = llvm::dyn_cast<llvm::ConstantInt>(CI.getArgOperand(1));
	assert(indexOp && "BitRangeGet offset should always be constant");
	auto &Ctx = CI.getContext();
	if (auto srcC = llvm::dyn_cast<llvm::ConstantInt>(srcOp)) {
		size_t resWidth = CI.getType()->getIntegerBitWidth();
		return IC.replaceInstUsesWith(CI,
				llvm::ConstantInt::get(Ctx,
						srcC->getValue().extractBits(resWidth,
								indexOp->getZExtValue())));
	} else if (llvm::isa<llvm::PoisonValue>(srcOp)) {
		return IC.replaceInstUsesWith(CI, llvm::PoisonValue::get(CI.getType()));
	} else if (llvm::isa<llvm::UndefValue>(srcOp)) {
		return IC.replaceInstUsesWith(CI, llvm::UndefValue::get(CI.getType()));
	}
	return nullptr;
}

template<typename InstructionCombinerT>
llvm::Instruction* tryReduceBitRangeGetOnConcat(InstructionCombinerT& IC, llvm::CallInst &I) {
	// if BitRangeGet exactly selects some member of BitConcat replace this with selected member
	if (auto src = llvm::dyn_cast<llvm::CallInst>(I.getArgOperand(0))) {
		assert(llvm::isa<llvm::ConstantInt>(I.getArgOperand(1)));
		if (IsBitConcat(src)) {
			IC.Builder.SetInsertPoint(src->getNextNode());
			auto offset = I.getArgOperand(1);
			auto width = I.getType()->getIntegerBitWidth();
			llvm::Value *r = CreateBitRangeGet(&IC.Builder, src, offset, width); // reuse folding implemented in CreateBitRangeGet
			if (r != &I)
				return IC.replaceInstUsesWith(I, r);
		}
	}
	return nullptr;
}

template<typename InstructionCombinerT>
llvm::Instruction* tryReduceBitRangeGetOnBitRangeGet(InstructionCombinerT& IC, llvm::CallInst &I) {
	// if BitRangeGet exactly selects some member of BitConcat replace this with selected member
	if (auto src = llvm::dyn_cast<llvm::CallInst>(I.getArgOperand(0))) {
		auto offset = I.getArgOperand(1);
		assert(llvm::isa<llvm::ConstantInt>(offset));
		if (IsBitRangeGet(src)) {
			IC.Builder.SetInsertPoint(src->getNextNode());
			auto srcOffset = src->getArgOperand(1);
			assert(llvm::isa<llvm::ConstantInt>(srcOffset));
			auto width = I.getType()->getIntegerBitWidth();
			auto srcOfSrc = src->getArgOperand(0);
			auto offsetVal = llvm::dyn_cast<llvm::ConstantInt>(srcOffset)->getZExtValue() + llvm::dyn_cast<llvm::ConstantInt>(offset)->getZExtValue();
			llvm::Value *r = CreateBitRangeGetConst(&IC.Builder, srcOfSrc, offsetVal, width);
			if (r != &I)
				return IC.replaceInstUsesWith(I, r);
		}
	}
	return nullptr;
}


template<typename InstructionCombinerT>
llvm::Instruction* tryReduceConcatToZExt(InstructionCombinerT& IC, llvm::CallInst &CI) {
	if (CI.arg_size() == 2) {
		if (auto rhs = llvm::dyn_cast<llvm::ConstantInt>(CI.getArgOperand(1))) {
			if (rhs->isZero()) {
				IC.Builder.SetInsertPoint(&CI);
				return IC.replaceInstUsesWith(CI, IC.Builder.CreateZExt(CI.getArgOperand(0), CI.getType()));
			}
		}
	}
	return nullptr;
}

template<typename InstructionCombinerT>
llvm::Instruction* tryReduceConcatOnConcatOrContinuousSlices(InstructionCombinerT& IC,
		llvm::CallInst &CI) {
	ConcatMemberVector values;
	bool operandsChanged = false;
	size_t lastSize = 0;
	for (auto &A : CI.args()) {
		values.push_back_flattened(A.get());
		if (lastSize != values.members.size() - 1) {
			operandsChanged = true;
		}
		lastSize = values.members.size();
	}
	if (!operandsChanged)
		return nullptr;

	IC.Builder.SetInsertPoint(CI.getNextNode());

	auto newI = values.resolveValue(IC.Builder, nullptr, &CI);
	if (newI == &CI)
		return nullptr;

	return IC.replaceInstUsesWith(CI, newI);
}

template<typename InstructionCombinerT>
bool BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(InstructionCombinerT& IC,
		llvm::CallInst &I) {
	auto src = I.getArgOperand(0);
	if (auto srcI = llvm::dyn_cast<llvm::Instruction>(src))
		return IC._moveIntoSliceSuccessorsOf(I, *srcI);
	return false;
}

template<typename InstructionCombinerT>
bool TruncInstMoveIntoSliceSuccessorsOfSrcOperand(InstructionCombinerT& IC,
		llvm::TruncInst &I) {
	auto src = I.getOperand(0);
	if (auto srcI = llvm::dyn_cast<llvm::Instruction>(src))
		return IC._moveIntoSliceSuccessorsOf(I, *srcI);
	return false;

}

}
