#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>
#include <llvm/IR/PatternMatch.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

// copied from llvm-18 LoopIdiomRecognize.cpp
CallInst* HwtHlsInstCombiner::_createPopcntIntrinsic(IRBuilderBase &IRBuilder,
		Value *Val) {
	Value *Ops[] = { Val };
	Type *Tys[] = { Val->getType() };

	Module *M = IRBuilder.GetInsertBlock()->getParent()->getParent();
	Function *Func = Intrinsic::getOrInsertDeclaration(M, Intrinsic::ctpop, Tys);
	CallInst *CI = IRBuilder.CreateCall(Func, Ops);

	return CI;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceIntrinsicInst_ctpopReduceBitwidth(
		llvm::IntrinsicInst &I) {
	// remove constant bits from input of the ctpop
	ConcatMemberVector srcArgs;
	auto srcArg = I.getArgOperand(0);
	bool srcNegated = false;
	{
		Value *srcArgUnNegated;
		if (match(srcArg, m_Not(m_Value(srcArgUnNegated)))) {
			srcNegated = true;
			srcArg = srcArgUnNegated;
		}
		srcArgs.push_back_flattened(srcArg);
	}
	size_t offset = 0;
	ConcatMemberVector newStrArgs;
	bool reduced = false;
	for (auto a : srcArgs.members) {
		if (auto CI = dyn_cast<ConstantInt>(a.value)) {
			offset += CI->getValue().extractBits(a.width, a.offset).popcount();
			reduced = true;
		} else {
			newStrArgs.push_back(a);
		}
	}
	if (!reduced) {
		return nullptr;
	}
	Builder.SetInsertPoint(&I);
	Value *C = newStrArgs.resolveValue(Builder, nullptr, &I);
	Worklist.addValue(C);
	if (srcNegated) {
		C = Builder.CreateNot(C);
	}
	Value *bitCnt = _createPopcntIntrinsic(Builder, C);
	Worklist.addValue(bitCnt);
	bitCnt = Builder.CreateZExtOrTrunc(bitCnt, I.getType());
	if (offset != 0) {
		bitCnt = Builder.CreateAdd(bitCnt,
				Builder.getIntN(I.getType()->getIntegerBitWidth(), offset));
	}
	return replaceInstUsesWith(I, bitCnt);
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceIntrinsicInst_ctpopToCtlz(
		llvm::IntrinsicInst &I) {
	Instruction *src;
	auto srcNegated = false;
	if (match(I.getArgOperand(0), m_Not(m_Instruction(src)))) {
		srcNegated = true;
	} else {
		src = dyn_cast<Instruction>(I.getArgOperand(0));
		if (!src)
			return nullptr;
	}
	size_t bitwidth = src->getType()->getIntegerBitWidth();
	bool isCountFromLsbSide = true;
	{
		// checking for bit implications from LSB to MSB
		Value *prevBit = SearchBitRangeGetConst(src, 0, 1);
		if (!prevBit)
			return nullptr;
		for (size_t bitI = 1; bitI < bitwidth; ++bitI) {
			// * check that src operand value bit n ==> bit n-1
			//    if this is the case convert this to ctlo (which is ctlz(~x))
			// * check for ctlz, same case as ctlo but the src operand is negated
			Value *thisBit = SearchBitRangeGetConst(src, bitI, 1);
			if (!thisBit)
				return nullptr;
			if (auto impl = isImpliedConditionAndOrTree(Builder, thisBit,
					prevBit, DL, &AC, &DT, &I)) {
				if (!impl.value()) {
					isCountFromLsbSide = false;
					break;
				}
			} else {
				isCountFromLsbSide = false;
				break;
			}
			prevBit = thisBit;
		}
	}
	Intrinsic::ID fn;
	bool isCountFromMsbSide = true;
	if (isCountFromLsbSide) {
		fn = Intrinsic::cttz;
		isCountFromMsbSide = false;
	} else {
		fn = Intrinsic::ctlz;
		// same check as before, but now checking from MSB to LSB
		Value *prevBit = SearchBitRangeGetConst(src, bitwidth - 1, 1);
		if (!prevBit)
			return nullptr;
		for (int bitI = bitwidth - 2; bitI >= 0; --bitI) {
			Value *thisBit = SearchBitRangeGetConst(src, bitI, 1);
			if (!thisBit)
				return nullptr;
			if (auto impl = isImpliedConditionAndOrTree(Builder, thisBit,
					prevBit, DL, &AC, &DT, &I)) {
				if (!impl.value()) {
					isCountFromMsbSide = false;
					break;
				}
			} else {
				isCountFromMsbSide = false;
				break;
			}
			prevBit = thisBit;
		}
		if (!isCountFromMsbSide)
			return nullptr;
	}

	Value *r;
	if (srcNegated) {
		// counting appearance of zeros in a vector where bit==0 implies that all previous bits are 0
	} else {
		// counting appearance of ones in a vector where bit=1 implies that all previous bits are 1
		src = dyn_cast<Instruction>(Builder.CreateNot(src));
	}
	r = Builder.CreateIntrinsic(fn, { src->getType() }, { src, /*isZeroPoisonous*/
	Builder.getFalse() });
	return replaceInstUsesWith(I, r);
}

}
