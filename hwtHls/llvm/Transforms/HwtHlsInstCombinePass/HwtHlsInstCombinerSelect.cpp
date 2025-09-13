#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/bitMath.h>

#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

bool matchUniqueCmpTree(Value *Op, SmallPtrSet<ConstantInt*, 16> &seenConstants,
		CmpInst::Predicate Pred, Value *&v0);

bool matchUniqueCmpTreeMatchAndOr(Value *Op,
		SmallPtrSet<ConstantInt*, 16> &seenConstants, CmpInst::Predicate Pred,
		Value *&v0) {
	using Predicate = CmpInst::Predicate;
	Value *Op1, *Op2;
	if ((Pred == Predicate::ICMP_EQ
			&& match(Op, m_Or(m_Value(Op1), m_Value(Op2))))
			|| (Pred == Predicate::ICMP_NE
					&& match(Op, m_And(m_Value(Op1), m_Value(Op2))))) {
		return matchUniqueCmpTree(Op1, seenConstants, Pred, v0)
				&& matchUniqueCmpTree(Op2, seenConstants, Pred, v0);
	} else {
		return false;
	}
}
// Check if Op is a and/or/xor or icmp ne/eq v0, c on same v0 and c is unique constant
// :attention: V0 must be initialized to nullptr or already found value
bool matchUniqueCmpTree(Value *Op, SmallPtrSet<ConstantInt*, 16> &seenConstants,
		CmpInst::Predicate Pred, Value *&v0) {
	SmallPtrSet<ConstantInt*, 16> seenConstantsTmp = seenConstants; // copy because we can not update if match fails
	using Predicate = CmpInst::Predicate;
	Predicate _Pred;
	ConstantInt *cmpRhs;
	auto PredInv = CmpInst::getInversePredicate(Pred);
	Value *v0n = nullptr;
	if (v0 == nullptr) {
		if (match(Op, m_ICmp(_Pred, m_Value(v0), m_ConstantInt(cmpRhs)))
				&& _Pred == Pred) {
		} else if (match(Op, m_Not(m_Value(v0n)))
				&& matchUniqueCmpTree(v0n, seenConstantsTmp, PredInv, v0)) {
			return true;
		} else {
			return matchUniqueCmpTreeMatchAndOr(Op, seenConstants, Pred, v0);
		}
	} else {
		if (match(Op, m_ICmp(_Pred, m_Specific(v0), m_ConstantInt(cmpRhs)))
				&& _Pred == Pred) {
		} else if (match(Op, m_Not(m_Value(v0n)))
				&& matchUniqueCmpTree(v0n, seenConstantsTmp, PredInv, v0)) {
			return true;
		} else {
			return matchUniqueCmpTreeMatchAndOr(Op, seenConstants, Pred, v0);
		}
	}

	if (seenConstantsTmp.contains(cmpRhs))
		return false;
	else
		seenConstantsTmp.insert(cmpRhs);
	seenConstants = seenConstantsTmp;
	return true;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceSelectInst_unNegate(
		llvm::SelectInst &SI) {
	Value *C;
	if (match(SI.getCondition(), m_Not(m_Value(C)))) {
		auto VT = SI.getTrueValue();
		auto VF = SI.getFalseValue();
		replaceOperand(SI, 0, C);
		replaceOperand(SI, 1, VF);
		replaceOperand(SI, 2, VT);
		Worklist.push(&SI);
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::_tryReduceSelectInst_toAndOr_SelectOfCompares(
		llvm::SelectInst &SI) {
	if (!SI.getType()->isIntegerTy(1))
		return nullptr;
	auto C = SI.getCondition();
	auto VT = SI.getTrueValue();
	auto VF = SI.getFalseValue();

	// check for select of compares of the same value
	// allow any cmp to be !(v0!=c)
	// :note: it is important that constants are unique
	// because (v0 != 0) ? (v0 != 0) : (v0 != 1)  ; ==1 if v=1
	//         (v0 != 0) ? (v0 != 1) : (v0 != 0)  ; ==0 if v=1

	// generic equation for rewrite of select to and-or
	// v = c?v0:v1 = (c & v0) | (!c & v1)

	// detect EQ,NE in condition operand
	Value *v0 = nullptr;
	SmallPtrSet<ConstantInt*, 16> seenConstants;
	bool match = false;
	ICmpInst::Predicate condP = ICmpInst::Predicate::ICMP_EQ;
	if (matchUniqueCmpTree(C, seenConstants, ICmpInst::Predicate::ICMP_EQ,
			v0)) {
		match = true;
	} else {
		seenConstants.clear();
		if (matchUniqueCmpTree(C, seenConstants, ICmpInst::Predicate::ICMP_NE,
				v0)) {
			match = true;
			condP = ICmpInst::Predicate::ICMP_NE;
		}
	}

	// detect EQ,NE in value operands
	auto valueP = ICmpInst::Predicate::ICMP_EQ;
	if (match) {
		SmallPtrSet<ConstantInt*, 16> seenConstantsBkp = seenConstants;
		auto PInv = ICmpInst::getInversePredicate(valueP);
		if (matchUniqueCmpTree(VT, seenConstants, valueP, v0)
				&& matchUniqueCmpTree(VF, seenConstants, valueP, v0)) {
		} else if (matchUniqueCmpTree(VT, seenConstantsBkp, PInv, v0)
				&& matchUniqueCmpTree(VF, seenConstantsBkp, PInv, v0)) {
			valueP = PInv;
		} else {
			match = false;
		}
	}

	if (match) {
		switch (condP) {
		case ICmpInst::Predicate::ICMP_EQ: {
			switch (valueP) {
			case ICmpInst::Predicate::ICMP_EQ: {
				//  specialized cases eq-eq:
				//  %c0 = icmp eq i9 %v0, 8
				//  %c1 = icmp eq i9 %v0, 7
				//  %c2 = icmp eq i9 %v0, 6
				//  %res = select i1 %c0, i1 %c1, i1 %c2
				//  %res = c2 ; because v0 is always just a single value (thus c0&c1==false)
				return replaceInstUsesWith(SI, VF);
			}
			case ICmpInst::Predicate::ICMP_NE: {
				// specialized cases eq-ne:
				// %c0 = icmp eq i8 %v0, 8
				// %c1 = icmp ne i8 %v0, 6
				// %c2 = icmp ne i8 %v0, 7
				// %res = select i1 %c0 i1 %c1, i1 %c2
				// %res = (true & %c1) | (!c0 & %c2)  ; because if c0=1 it is true on both sides and if it is 0 it is c0=0 then c2 is activated
				auto Cn = Builder.CreateNot(C);
				Worklist.pushValue(Cn);
				auto newF = Builder.CreateAnd(Cn, VF);
				Worklist.pushValue(newF);
				auto newI = Builder.CreateOr(VT, newF);
				return replaceInstUsesWith(SI, newI);
			}
			default:
				llvm_unreachable(
						"All possible variant should have been checked");
			}
			break;
		}
		case ICmpInst::Predicate::ICMP_NE: {
			switch (valueP) {
			case ICmpInst::Predicate::ICMP_EQ: {
				// specialized cases ne-eq:
				// %c0 = icmp ne i8 %v0, 8
				// %c1 = icmp eq i8 %v0, 6
				// %c2 = icmp eq i8 %v0, 7
				// %res = select i1 %c0 i1 %c1, i1 %c2
				// %res = (c0 & %c1) | false  ; because if c0=1 it is true on both sides and if it is 0 it is c0=0 then c2 is activated
				auto newI = Builder.CreateAnd(C, VT);
				return replaceInstUsesWith(SI, newI);
			}
			case ICmpInst::Predicate::ICMP_NE: {
				// specialized cases ne-ne:
				// :note: ne predicates are merged using and
				// %c0 = icmp ne i8 %v0, 8
				// %c1 = icmp ne i8 %v0, 6
				// %c2 = icmp ne i8 %v0, 7
				// %res = select i1 %c0 i1 %c1, i1 %c2
				//  %c0 == false ===> c2 == true because v0 == some constant from c0 set and c2 constant set is known to have empty intersect
				// %res = (%c0 & %c1) | (!c0 & true)
				// %res = !c0 | c1
				auto c0n = Builder.CreateNot(C);
				Worklist.pushValue(c0n);
				auto newI = Builder.CreateOr(c0n, VT);
				return replaceInstUsesWith(SI, newI);
			}
			default:
				llvm_unreachable(
						"All possible variant should have been checked");
			}
			break;
		}
		default:
			llvm_unreachable("All possible variant should have been checked");
		}
	}

	return nullptr;
}

Instruction* HwtHlsInstCombiner::tryReduceSelectInst_toAndOr(
		llvm::SelectInst &SI) {
	if (!SI.getType()->isIntegerTy())
		return nullptr;
	size_t width = SI.getType()->getIntegerBitWidth();
	auto VT = SI.getTrueValue();
	auto VF = SI.getFalseValue();
	auto VTC = dyn_cast<ConstantInt>(VT);
	auto VFC = dyn_cast<ConstantInt>(VF);

	Builder.SetInsertPoint(&SI);

	auto C = SI.getCondition();
	if (VTC && VFC) {
		// bot value operands are constants -> concatenation of constants and condition or its negation
		auto _VTC = VTC->getValue();
		auto _VFC = VTC->getValue();

		auto unequalBitMask = _VTC ^ VFC->getValue();
		SmallVector<Value*> concatOps;
		size_t off = 0;
		for (const auto& [isUnequal, uneqSeqLen] : iter1and0sequences(unequalBitMask, 0,
				width)) {
			auto VTVal = _VTC.extractBits(uneqSeqLen, off);
			if (!isUnequal) {
				concatOps.push_back(Builder.getInt(VTVal));
				off += uneqSeqLen;
				continue;
			}
			auto VFVal = _VFC.extractBits(uneqSeqLen, off);
			for (const auto& [tBit, seqLen] : iter1and0sequences(VTVal, 0,
					uneqSeqLen)) {
				// number of bits processed in one step,
				// specifies the number of lsb bits which is same in _VTC/_VFC separately
				// bits on this position may be 0 or 1 depending on C
				Value *bitVal = C;
				if (!tBit) {
					// bit is 0 if C is 1, negation is required
					bitVal = Builder.CreateNot(bitVal);
				}
				// extend to length of sequence which are driven by same value
				concatOps.push_back(
						Builder.CreateSExt(bitVal,
								Builder.getIntNTy(seqLen)));
				off += seqLen;
			}
		}
		assert(off == width);
		return replaceInstUsesWith(SI, CreateBitConcat(&Builder, concatOps));
	}

	// handle cases it zero or all ones value operands
	if (VFC && VFC->isZero()) {
		// select %c, v0, 0 -> and(c, v0)
		if (width != 1)
			C = Builder.CreateSExt(C, VT->getType());
		return replaceInstUsesWith(SI, Builder.CreateAnd(C, VT));
	} else if (VTC && VTC->isAllOnesValue()) {
		// select %c, 1, v1 -> or(c, v1)
		if (width != 1)
			C = Builder.CreateSExt(C, VT->getType());
		return replaceInstUsesWith(SI, Builder.CreateOr(C, VF));
	} else if (VTC && VTC->isZero()) {
		// select %c, 0, v1 -> and(!c, v1)
		if (width != 1)
			C = Builder.CreateSExt(C, VT->getType());
		auto nC = Builder.CreateNot(C);
		return replaceInstUsesWith(SI, Builder.CreateAnd(nC, VF));
	} else if (VFC && VFC->isAllOnesValue()) {
		// select %c, v0, 1 -> or(!c, v0)
		if (width != 1)
			C = Builder.CreateSExt(C, VT->getType());
		auto nC = Builder.CreateNot(C);
		return replaceInstUsesWith(SI, Builder.CreateOr(nC, VT));
	}

	// handle cases where VT/VF is C or its negation
	// %c = xor i1 %v0, true
	// %res = select i1 %c, i1 %v0, i1 %v1
	// ==
	// %res = select i1 %v0, i1 %v1, i1 %v0
	// ==
	// %res = and i1 %v0, %v1
	if (match(C, m_Not(m_Specific(VT)))) {
		auto newI = Builder.CreateAnd(VT, VF);
		return replaceInstUsesWith(SI, newI);
	}

	// %res = select i1 %v0, i1 %v0, i1 %v1
	// to: or v0, v1
	if (match(VT, m_SExtOrSelf(m_Specific(C)))) {
		auto newI = Builder.CreateOr(VT, VF);
		return replaceInstUsesWith(SI, newI);
	}
	// %res = select i1 %v0, i1 %v1, i1 %v0
	// to: and v0, v1
	if (match(VF, m_SExtOrSelf(m_Specific(C)))) {
		auto newI = Builder.CreateAnd(VT, VF);
		return replaceInstUsesWith(SI, newI);
	}
	if (width != 1)
		return nullptr;
	//// case for operands swapped
	//// %c = xor i1 %v1, true
	//// %res = select i1 %c, i1 %v0, i1 %v1
	//// ==
	//// %res = select i1 %v1, i1 %v1, i1 %v0
	//// ==
	//// %res = or i1 %v0, %v1
	//if (match(C, m_Xor(m_Specific(VF), m_AllOnes()))) {
	//	auto newI = Builder.CreateOr(VT, VF);
	//	return replaceInstUsesWith(SI, newI);
	//}
	return _tryReduceSelectInst_toAndOr_SelectOfCompares(SI);
}

template<unsigned opcode>
struct matcherForBinOpcode {
	template<typename LHS, typename RHS>
	static inline BinaryOp_match<LHS, RHS, opcode> match(const LHS &L,
			const RHS &R) {
		return BinaryOp_match<LHS, RHS, opcode>(L, R);
	}
	template<typename LHS, typename RHS>
	static inline BinaryOp_match<LHS, RHS, opcode, true> matchCommutative(
			const LHS &L, const RHS &R) {
		return BinaryOp_match<LHS, RHS, opcode, true>(L, R);
	}
};

template<unsigned opcode>
Value* matchIsSameOperatorWithSameOperandComutative(IRBuilderBase &Builder,
		SelectInst &SI, Value *VT, Value *VF,
		std::function<Value* (Value*, Value*)> operatorCreateFn) {
	Value *tLhs, *tRhs, *fLhs, *fRhs;
	using matcher = matcherForBinOpcode<opcode>;
	if (match(VT, matcher::match(m_Value(tLhs), m_Value(tRhs)))) {
		if (match(VF,
				matcherForBinOpcode<opcode>::matchCommutative(m_Specific(tLhs),
						m_Value(fRhs)))) {
			// tLhs is common
			auto newSel = Builder.CreateSelect(SI.getCondition(), tRhs, fRhs);
			auto newI = operatorCreateFn(tLhs, newSel);
			return newI;
		} else if (match(VF,
				matcher::matchCommutative(m_Value(fLhs), m_Specific(tRhs)))) {
			// tRhs is common
			auto newSel = Builder.CreateSelect(SI.getCondition(), tLhs, fLhs);
			auto newI = operatorCreateFn(tRhs, newSel);
			return newI;
		}
	}

	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceSelectInst_extractCommonFromOperands(
		llvm::SelectInst &SI) {
	auto *VT = SI.getTrueValue();
	auto *VF = SI.getFalseValue();
	if (VT == VF) {
		return replaceInstUsesWith(SI, VT);
	}
	if (!SI.getType()->isIntegerTy(1))
		return nullptr;

	Builder.SetInsertPoint(&SI);
	if (Value *newI = matchIsSameOperatorWithSameOperandComutative<
			Instruction::And>(Builder, SI, VT, VF, [&](Value *LHS, Value *RHS) {
		return Builder.CreateAnd(LHS, RHS);
	})) {
		// c ? (v0 & x) : (v0 & y) -> v0 & (c?x:y)
		return replaceInstUsesWith(SI, newI);
	}

	if (Value *newI = matchIsSameOperatorWithSameOperandComutative<
			Instruction::Or>(Builder, SI, VT, VF, [&](Value *LHS, Value *RHS) {
		return Builder.CreateOr(LHS, RHS);
	})) {
		// c ? (v0 | x) : (v0 | y) -> v0 | (c?x:y)
		return replaceInstUsesWith(SI, newI);
	}

	if (Value *newI = matchIsSameOperatorWithSameOperandComutative<
			Instruction::Xor>(Builder, SI, VT, VF, [&](Value *LHS, Value *RHS) {
		return Builder.CreateXor(LHS, RHS);
	})) {
		// c ? (v0 ^ x) : (v0 ^ y) -> v0 ^ (c?x:y)
		return replaceInstUsesWith(SI, newI);
	}

	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceSelectInst_selectOfImpliedBitsOrZero_toConcat(
		llvm::SelectInst &SI) {
	// %vt = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %b1)
	// %SI = select i1 %c, i2 %vt, i2 0 ; (also case with VF == -1 is suported)
	// * if VF==0 and every bit from vt implies b0 or is constant we can replace this with just vt
	//   with constant 1 replaced with c
	//   %SI = call i2 @hwtHls.bitConcat.i1.i1(i1 %c, i1 %b1)
	// * if VF==0 and implication is not proven but the vt is concat of 1b values
	//   the SI is replaced with concat of and()
	//   %SI = call i2 @hwtHls.bitConcat.i1.i1(i1 %c, i1 %c and %b1)
	// * if VF==-1 and vt is concat of 1b values
	//   replace SI with concat of or of c and each bit
	//   %SI = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %c or %b1)

	auto cond = SI.getCondition();
	if (isa<Constant>(cond)) {
		return nullptr; // const condition should be optimized first
	}
	bool VF_isAllOnes = false;
	if (auto VF = dyn_cast<ConstantInt>(SI.getFalseValue())) {
		if (VF->isZero()) {
		} else if (VF->isAllOnesValue()) {
			VF_isAllOnes = true;
		} else {
			return nullptr; // VF != 0 && VF != all ones
		}
	} else {
		return nullptr;
	}

	auto VT = dyn_cast<CallInst>(SI.getTrueValue());
	if (VT && IsBitConcat(VT)) {
		SmallVector<bool> isImplied;
		if (VF_isAllOnes) {
			for (Use &U : VT->args()) {
				auto *O = U.get();
				if (isa<ConstantInt>(O)) {
				} else if (O->getType()->getIntegerBitWidth() != 1) {
					return nullptr;
				}
			}
		} else {
			// VF is 0
			isImplied.resize(VT->arg_size());

			for (Use &U : VT->args()) {
				auto *O = U.get();
				isImplied[U.getOperandNo()] = false;
				if (isa<ConstantInt>(O)) {
				} else if (O->getType()->getIntegerBitWidth() != 1) {
					return nullptr;
				} else if (isImpliedConditionAndOrTree(Builder, O, cond, DL,
						&AC, &DT, &SI)) {
					isImplied[U.getOperandNo()] = true;
				}
			}
		}
		Value* condN = nullptr;
		SmallVector<Value*> newConcatArgs;
		for (Use &U : VT->args()) {
			auto *O = U.get();

			if (auto C = dyn_cast<ConstantInt>(O)) {
				for (const auto& [zeroOrOne, width] : iter1and0sequences(
						C->getValue(), 0, O->getType()->getIntegerBitWidth())) {
					if (VF_isAllOnes) {
						// or mode
						if (zeroOrOne) {
							// (c & 1) | (~c & 1) = (c | ~c) = 1
							newConcatArgs.push_back(Builder.getInt(APInt::getAllOnes(width)));
						} else {
							if (!condN)
								condN = Builder.CreateNot(cond);
							// (c & 0) | (~c & 1) = ~c
							for (unsigned i = 0; i < width; i++) {
								newConcatArgs.push_back(condN);
							}
						}
					} else {
						// and mode
						if (zeroOrOne) {
							// (c & 1) | (~c & 0) = (c | 0) = c
							for (unsigned i = 0; i < width; i++) {
								newConcatArgs.push_back(cond);
							}
						} else {
							// (c & 0) | (~c & 0) = 0
							newConcatArgs.push_back(Builder.getIntN(width, 0));
						}
					}
				}
			} else {
				if (VF_isAllOnes) {
					if (!condN)
						condN = Builder.CreateNot(cond);
					// (c & x) | (~c & 1) = ((c & x) | ~c) = (~c | x)
					O = Builder.CreateOr(condN, O);
					Worklist.pushValue(O);
				} else {
					// (c & x) | (~c & 0) = c & x
					auto _isImplied = isImplied[U.getOperandNo()];
					if (!_isImplied) {
						O = Builder.CreateAnd(cond, O);
						Worklist.pushValue(O);
					}
				}
				newConcatArgs.push_back(O);
			}
		}
		auto r = CreateBitConcat(&Builder, newConcatArgs, "");
		return replaceInstUsesWith(SI, r);
	}
	return nullptr;
}

}
