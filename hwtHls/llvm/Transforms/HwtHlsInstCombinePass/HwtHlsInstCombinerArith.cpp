#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/ConstantRange.h>
#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

llvm::Instruction* HwtHlsInstCombiner::tryReduceUMinNe_to_ULT(CmpInst &I) {
	/*
	 %1 = call i3 @llvm.umin.i3(i3 %0, i3 1)
	 %2 = trunc i3 %1 to i2 ; trunc is optional, it is guaranteed that the constant will fit to result
	 ; because it is used in icmp later
	 %3 = icmp ne i2 %2, 1

	 to
	 %3 = icmp ult i3 %0, 1
	 */
	Value *v0;
	// :note: C and C0 hold same value, but have different bitwidth
	ConstantInt *C;
	ConstantInt *C0;
	CmpPredicate Pred;
	if (match(&I,
			m_ICmp(Pred, m_TruncOrSelf(m_UMin(m_Value(v0), m_ConstantInt(C0))),
					m_ConstantInt(C)))) {
		size_t maxBitwidth = std::max(C0->getType()->getIntegerBitWidth(),
				C->getType()->getIntegerBitWidth());
		if (Pred == CmpInst::Predicate::ICMP_NE
				&& C0->getValue().zext(maxBitwidth)
						== C->getValue().zext(maxBitwidth)) {
			Type *Ty = Builder.getIntNTy(maxBitwidth);
			v0 = Builder.CreateZExtOrTrunc(v0, Ty);
			C = dyn_cast<ConstantInt>(Builder.CreateZExtOrTrunc(C, Ty));
			auto newI = Builder.CreateICmpULT(v0, C);
			return replaceInstUsesWith(I, newI);
		}
	}

	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceZExt_onTurncUMin(
		llvm::ZExtInst &I) {
	//  %18 = call i3 @llvm.umin.i3(i3 %17, i3 2)
	//  %19 = trunc i3 %18 to i2
	//  %27 = zext i2 %19 to i3
	//  to %28 = %18
	Value *v0, *vUMin;
	ConstantInt *CI;
	if (match(I.getOperand(0), m_Trunc(m_Value(vUMin)))
			&& match(vUMin, m_UMin(m_Value(v0), m_ConstantInt(CI)))) {
		size_t resultMaxUsedBits = CI->getType()->getIntegerBitWidth()
				- CI->getValue().countLeadingZeros();
		size_t truncResWidth = I.getOperand(0)->getType()->getIntegerBitWidth();
		if (truncResWidth >= resultMaxUsedBits) {
			// umin truncates the value, explicit trunc-zext is not required
			Builder.SetInsertPoint(&I);
			auto newI = Builder.CreateZExtOrTrunc(vUMin, I.getType());
			return replaceInstUsesWith(I, newI);
		}
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceICmp_onTurncUMin(
		llvm::ICmpInst &I) {
	// %1 = call i3 @llvm.umin.i3(i3 %0, i3 1) ; umin does not interfere with icmp
	// %2 = trunc i3 %1 to i2 ; trunc does not affect result because %1 value have fewer bits
	// %3 = icmp eq i2 %2, 0
	//
	// to
	// %3 = icmp eq i2 %0, 0

	Value *v0;
	CmpPredicate Pred;
	ConstantInt *C0, *C;
	if (match(&I,
			m_ICmp(Pred, m_TruncOrSelf(m_UMin(m_Value(v0), m_ConstantInt(C0))),
					m_ConstantInt(C)))) {
		Builder.SetInsertPoint(&I);

		C = dyn_cast<ConstantInt>(Builder.CreateZExt(C, C0->getType()));
		assert(C);
		const auto &CV = C->getValue();
		const auto &C0V = C0->getValue();

		if (Pred == ICmpInst::Predicate::ICMP_EQ) {
			if (C0V != CV) {
				auto newI = Builder.CreateICmpEQ(v0, C);
				return replaceInstUsesWith(I, newI, true);
			}
		} else if (Pred == ICmpInst::Predicate::ICMP_ULE) {
			if (C0V.ule(CV)) {
				return replaceInstUsesWith(I, Builder.getInt1(true));
			} else {
				auto newI = Builder.CreateICmpULE(v0, C);
				return replaceInstUsesWith(I, newI, true);
			}
		} else if (Pred == ICmpInst::Predicate::ICMP_ULT) {
			if (C0V.ult(CV)) {
				return replaceInstUsesWith(I, Builder.getInt1(true));
			} else {
				auto newI = Builder.CreateICmpULT(v0, C);
				return replaceInstUsesWith(I, newI, true);
			}
		}
	}
	return nullptr;
}

void HwtHlsInstCombiner::_setAssumeRangeIfisBetterRange(Value *V,
		const ConstantRange &newAssumedRange, bool UseInstrInfo,
		Instruction *CtxI) {
	assert(CtxI);
	if (newAssumedRange.isFullSet())
		return; // newAssumedRange does not actually specify anything
	auto CR = ConstantRange::getFull(V->getType()->getIntegerBitWidth());
	// Try to restrict the range based on information from assumptions.
	for (auto &AssumeVH : AC.assumptionsFor(V)) {
		if (!AssumeVH)
			continue;
		CallInst *I = cast<CallInst>(AssumeVH);
		assert(
				I->getParent()->getParent() == CtxI->getParent()->getParent()
						&& "Got assumption for the wrong function!");
		assert(
				I->getCalledFunction()->getIntrinsicID() == Intrinsic::assume
						&& "must be an assume intrinsic");

		if (!isValidAssumeForContext(I, CtxI, &DT))
			continue;
		Value *Arg = I->getArgOperand(0);
		ICmpInst *Cmp = dyn_cast<ICmpInst>(Arg);
		// Currently we just use information from comparisons.
		if (!Cmp || Cmp->getOperand(0) != V)
			continue;
		// TODO: Set "ForSigned" parameter via Cmp->isSigned()?
		ConstantRange RHS = computeConstantRange(Cmp->getOperand(1), /* ForSigned */
		false, UseInstrInfo, &AC, I, &DT, Options.computeKnownBitsDepth);
		auto CR2 = CR.intersectWith(
				ConstantRange::makeAllowedICmpRegion(Cmp->getPredicate(), RHS));
		if (CR2 == newAssumedRange)
			return; // already assumed
		if (CR2.contains(newAssumedRange)) {
			// new assumption will be more specific, we do not need this one
			// convert it to assume(true) so it is removed later
			replaceOperand(*I, 0, Builder.getInt1(true));
		}
		CR = CR2;
	}

	// based on llvm-18 InstCombineCompares.cpp/foldICmpUSubSatOrUAddSatWithConstant
	CmpInst::Predicate Pred;
	APInt C;
	APInt Offset;

	newAssumedRange.getEquivalentICmp(Pred, C, Offset);

	auto Ty = V->getType();
	Builder.SetInsertPoint(CtxI->getNextNode());
	auto LHS = V;
	if (!Offset.isZero())
		LHS = Builder.CreateAdd(V, ConstantInt::get(Ty, Offset));
	Value *newAssumeSrc = Builder.CreateICmp(Pred, LHS,
			ConstantInt::get(Ty, C));
	Builder.CreateAssumption(newAssumeSrc);
}

void HwtHlsInstCombiner::_precomputeRangeAssumptionForZExtAndTrunc(Value *V,
		bool ForSigned, bool UseInstrInfo, size_t Depth) {
	if (Depth == 0)
		return;
	if (auto I = dyn_cast<Instruction>(V)) {
		if (isa<ZExtInst>(V) || isa<TruncInst>(I)) {
			auto src = I->getOperand(0);
			_precomputeRangeAssumptionForZExtAndTrunc(src, ForSigned,
					UseInstrInfo, Depth - 1);
			auto CR = computeConstantRange(src, ForSigned, UseInstrInfo, &AC, I,
					&DT, Depth);
			CR = CR.zextOrTrunc(I->getType()->getIntegerBitWidth());
			_setAssumeRangeIfisBetterRange(I, CR, UseInstrInfo, I);
		} else {
			bool is_computeConstantRange_compatible = (isa<BinaryOperator>(V)
					|| isa<IntrinsicInst>(V) || isa<SelectInst>(V)
					|| isa<FPToUIInst>(I) || isa<FPToSIInst>(I));
			if (is_computeConstantRange_compatible) {
				bool isSelect = isa<SelectInst>(V);
				for (auto O : I->operand_values()) {
					if (!isSelect || I->getOperand(0) != O)
						_precomputeRangeAssumptionForZExtAndTrunc(O, ForSigned,
								UseInstrInfo, Depth - 1);
				}
			}
		}
	}
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceICmpNEonPHI_to_UGT_or_ULT(
		llvm::ICmpInst &I) {
	// [todo]
	// CorrelatedValuePropagationPass
	// LazyValueInfo *LVI = &AM.getResult<LazyValueAnalysis>(F);
	if (I.getPredicate() == ICmpInst::Predicate::ICMP_NE) {
		if (auto lhsPhi = dyn_cast<PHINode>(I.getOperand(0))) {
			if (auto rhsC = dyn_cast<ConstantInt>(I.getOperand(1))) {
				// computeKnownBits
				auto BitWidth = lhsPhi->getType()->getIntegerBitWidth();
				ConstantRange CR = ConstantRange::getEmpty(BitWidth);
				for (Use &_phiIV : lhsPhi->incoming_values()) {
					auto phiIV = _phiIV.get();
					// [todo] cache range query and do not perform _precomputeRangeAssumptionForZExtAndTrunc
					// if there is a record in cache
					_precomputeRangeAssumptionForZExtAndTrunc(phiIV, /*ForSigned*/
					false, /*UseInstrInfo*/true, Options.computeKnownBitsDepth);
					auto IVCR = computeConstantRange(phiIV, /*ForSigned*/
					false, /*UseInstrInfo*/true, &AC, /*CtxI*/
							dyn_cast<Instruction>(phiIV), &DT,
							Options.computeKnownBitsDepth);
					if (CR.isFullSet())
						return nullptr; // failed to find any constraint
					CR = CR.unionWith(IVCR,
							ConstantRange::PreferredRangeType::Unsigned);
					if (CR.isFullSet())
						return nullptr; // failed to find any constraint
				}
				Builder.SetInsertPoint(&I);
				auto C = rhsC->getValue();
				ConstantRange CR_ULT = ConstantRange(APInt::getZero(BitWidth),
						C);
				//auto KB = computeKnownBits(lhsPhi, Options.computeKnownBitsDepth, SQ);
				auto constrainedUlt = CR.intersectWith(CR_ULT,
						ConstantRange::PreferredRangeType::Unsigned);
				if (!constrainedUlt.isEmptySet() && constrainedUlt == CR_ULT) {
					// umin(x, c) == x -> (x != c) == (x < c)
					auto r = Builder.CreateICmpULT(lhsPhi, rhsC);
					return replaceInstUsesWith(I, r);
				}
				ConstantRange CR_UGT = ConstantRange(C,
						APInt::getAllOnes(BitWidth));
				auto constrainedUgt = CR.intersectWith(CR_UGT,
						ConstantRange::PreferredRangeType::Unsigned);
				if (!constrainedUgt.isEmptySet() && constrainedUgt == CR_UGT) {
					// umax(x, c) == x -> (x != c) == (x > c)
					auto r = Builder.CreateICmpUGT(lhsPhi, rhsC);
					return replaceInstUsesWith(I, r);
				}
				if (constrainedUlt.isEmptySet()
						&& constrainedUgt.isEmptySet()) {
					// !(x < c) && !(x > c) -> x == c -> (x != c) == false
					return replaceInstUsesWith(I, Builder.getInt1(false));
				}
			}
		}
	}
	return nullptr;

}

}
