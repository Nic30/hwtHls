#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/ConstantRange.h>
#include <llvm/Transforms/Utils/Local.h>
#include <map>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

Value* HwtHlsInstCombiner::_rewriteCmpConstOnAddSubOpConst(BinaryOperator &BI,
		CmpInst &ICMPI, const APInt &cmpRhsVal) {
	// %lhs = add i8 %v0, %const0
	// %res = icmp eq/ne/ult i8 %lhs, %const1

	// const0 can be constant or ZExt i1 to iN which is equivalent to select %c, %v0, %v0+1
	// [todo]

	using BinaryOps = BinaryOperator::BinaryOps;
	using Predicate = CmpInst::Predicate;
	if (auto BI_rhsC = dyn_cast<ConstantInt>(BI.getOperand(1))) {
		auto Opc = BI.getOpcode();
		auto newLhs = BI.getOperand(0);
		auto newCmpRhsVal = cmpRhsVal;
		auto BI_rhsVal = BI_rhsC->getValue();

		switch (Opc) {
		case BinaryOps::Add:
			newCmpRhsVal -= BI_rhsVal;
			break;
		case BinaryOps::Sub:
			newCmpRhsVal += BI_rhsVal;
			break;
		default:
			return nullptr;
		}
		auto Pred = ICMPI.getPredicate();
		switch (Pred) {
		case Predicate::ICMP_EQ:
		case Predicate::ICMP_NE: {
			// can hoist, with updated rhs
			auto newI = Builder.CreateICmp(Pred, newLhs,
					Builder.getInt(newCmpRhsVal), ICMPI.getName());
			return newI;
		}
		//case Predicate::ICMP_ULT: {
		//	// when hoisting this potentially must be split to multiple compares because of hoisting
		//	// in this simple case we check only for cases where cmpRhsVal is in format of "1+0*" (format is regex)
		//	/*
		//	 * x = newLhs + c0
		//	 * I = x < c1
		//	 * // c1 in "1+0*" format, this checks if n lower bits are 0
		//	 * // I checks if n lower bits of I is zero which is equivalent to Or(x != c + c0 for c in range(n))
		//	 * */
        //
		//	auto zeroCnt = cmpRhsVal.countTrailingZeros();
		//	auto oneCnt = cmpRhsVal.popcount();
		//	if (zeroCnt + oneCnt != cmpRhsVal.getBitWidth()) {
		//		// it is not sequence of 1 with optional trailing zeros
		//		return nullptr;
		//	}
		//	SmallVector<Value*> andMembers;
		//	// x < -1 (all ones) -> x != -1
		//	// x < -2 (all ones except lsb, e.g. 0b1110) -> (x != -1 & x != -2)
		//	// ...
		//	for (int i = zeroCnt; i >= 0; --i) {
		//		auto ne = Builder.CreateICmpNE(newLhs,
		//				Builder.getInt(newCmpRhsVal + i));
		//		andMembers.push_back(ne);
		//	}
        //
		//	auto newI = Builder.CreateAnd(andMembers);
		//	return newI;
		//}
		default: {
		}
		}
	}
	return nullptr;
}

Instruction* HwtHlsInstCombiner::tryReduceCmpInst_hoistConstICmpOnConstArithAndSel(
		CmpInst &I) {
	// :attention: this leads to enormous code duplication of long ctlz chains, problem is that this likely increases a
	// range of compare when going up in instructions but there we do not know about other compares and how compare range expands in general
	// from this reason we just add select and expect that it will be optimized later but this generates 3 times more instructions which then
	// are likely to fall apart to up to (3+4)x more instructions as select is rewritten into and/or/not
	auto rhs = I.getOperand(1);
	if (!isa<ConstantInt>(rhs))
		return nullptr;
	auto cmpRhsVal = dyn_cast<ConstantInt>(rhs)->getValue();
	auto lhs = I.getOperand(0);
	//auto Pred = I.getPredicate();

	//if (auto SI = dyn_cast<SelectInst>(lhs)) {
	//	/*
	//	 * Example:
	//	 * x = cond0 ? v0: v1
	//	 * I = x < c
	//	 *
	//	 * to
	//	 *
	//	 * I0 = v0 < c
	//	 * I1 = v1 < c
	//	 * I = cond0 ? I0: I1
	//	 * */
	//	if (SI->getType()->getScalarSizeInBits() == 1)
	//		return nullptr; // hoisting of users not necessary because it would not
	//	// result in reduced bitwidth of a mux
    //
	//	auto VT = SI->getTrueValue();
	//	auto VF = SI->getFalseValue();
	//	auto VTC = dyn_cast<Constant>(VT);
	//	auto VFC = dyn_cast<Constant>(VF);
	//	if (VTC || VFC) {
	//		auto newCmpT = I.clone();
	//		newCmpT->insertBefore(&I);
	//		replaceOperand(*newCmpT, 0, VT);
	//		Worklist.push(newCmpT);
    //
	//		auto newCmpF = I.clone();
	//		newCmpF->insertBefore(&I);
	//		replaceOperand(*newCmpF, 0, VF);
	//		Worklist.push(newCmpF);
    //
	//		Builder.SetInsertPoint(&I);
	//		auto newI = Builder.CreateSelect(SI->getCondition(), newCmpT,
	//				newCmpF, I.getName(), /*MDFrom*/SI);
	//		return replaceInstUsesWith(I, newI);
	//	} else {
	//		// check for
	//		// %v0_p1 = add/sub i8 %v0, const0
	//		// %v1 = select i1 %c, i8 %v0, i8 %v0_p1 ; or TValue-FValue swapped
	//		// %res = icmp ne/eq/ult i8 %v1, const1 ; ult is appliable only if it check for
	//		//   set of lower bits :see: :meth:`_rewriteICmpConstOnAddSubOpConst`
    //
	//		// and try to convert to select of ICMP on v0 instead
	//		// %v0_p1 = add i8 %v0, const0
	//		// %v1 = select i1 %c, i8 %v0, i8 %v0_p1
	//		// %res = icmp eq i8 %v1, const1
    //
	//		// to:
	//		// %res.0 = icmp eq i8 %v0, const1 - const0
	//		// %res.1 = icmp eq i8 %v0, const1
	//		// %v0_p1 = add i8 %v0, const0
	//		// %res = select i1 %c, i1 %res.1, i1 %res.0
    //
	//		Builder.SetInsertPoint(&I);
	//		using Predicate = CmpInst::Predicate;
	//		switch (Pred) {
	//		case Predicate::ICMP_EQ:
	//		case Predicate::ICMP_NE:
	//		case Predicate::ICMP_ULT: {
	//			ConstantInt *addSubConst;
	//			Value *newVF = nullptr;
	//			Value *newVT = nullptr;
	//			// %v0_p1 = add/sub i8 %v0, const
	//			// %v1 = select i1 %c, i8 %v0, i8 %v0_p1
	//			// %res = icmp ne/eq i8 %v1, 1
	//			if (match(VF, m_Add(m_Specific(VT), m_ConstantInt(addSubConst)))
	//					|| match(VF,
	//							m_Sub(m_Specific(VT),
	//									m_ConstantInt(addSubConst)))) {
	//				Value *v0 = VT;
	//				newVF = _rewriteCmpConstOnAddSubOpConst(
	//						*dyn_cast<BinaryOperator>(VF), I, cmpRhsVal);
	//				if (!newVF)
	//					return nullptr;
	//				newVT = Builder.CreateICmp(Pred, v0, rhs);
	//			} else if (match(VT,
	//					m_Add(m_Specific(VF), m_ConstantInt(addSubConst)))
	//					|| match(VT,
	//							m_Sub(m_Specific(VF),
	//									m_ConstantInt(addSubConst)))) {
	//				Value *v0 = VF;
	//				// VT-VF swapped
	//				// %v0_p1 = add/sub i8 %v0, const
	//				// %v1 = select i1 %c, i8 %v0_p1, i8 %v0
	//				// %res = icmp ne/eq i8 %v1, 1
	//				newVT = _rewriteCmpConstOnAddSubOpConst(
	//						*dyn_cast<BinaryOperator>(VT), I, cmpRhsVal);
	//				if (!newVT)
	//					return nullptr;
	//				newVF = Builder.CreateICmp(Pred, v0, rhs);
	//			} else {
	//				return nullptr;
	//			}
	//			auto newI = Builder.CreateSelect(SI->getCondition(), newVT,
	//					newVF);
	//			return replaceInstUsesWith(I, newI);
	//		}
	//		default:
	//			break;
	//		}
	//	}
	//} else
	if (auto BI = dyn_cast<BinaryOperator>(lhs)) {
		Builder.SetInsertPoint(&I);
		if (Value *r = _rewriteCmpConstOnAddSubOpConst(*BI, I, cmpRhsVal)) {
			return replaceInstUsesWith(I, r);
		}
	}

	return nullptr;
}
bool HwtHlsInstCombiner::pruneInvertedCmpDuplicatesInBlocks(Function &F) {
	bool change = false;
	for (auto &BB : F) {
		change |= pruneInvertedCmpDuplicatesInBlock(BB);
	}
	return change;
}
// This function does job similar to CSE.
// It deduplicates ICmp inverted and negated predicates in a single block only.
bool HwtHlsInstCombiner::pruneInvertedCmpDuplicatesInBlock(BasicBlock &BB) {
	// lhs -> unique cmp instructions and the rage which it specifies
	std::map<Value*, std::vector<std::pair<Instruction*, ConstantRange>>> seenCompares;

	bool change = false;
	for (auto &I : BB) {
		Instruction *lhs;
		const APInt *C;
		CmpInst::Predicate Pred;
		bool matched = false;
		bool inversed = false;
		if (match(&I, m_ICmp(Pred, m_Instruction(lhs), m_APInt(C)))) {
			matched = true;
		} else if (match(&I,
				m_Not(m_ICmp(Pred, m_Instruction(lhs), m_APInt(C))))) {
			matched = true;
			inversed = true;
		}
		if (!matched || lhs->getParent() != &BB) {
			continue;
		}
		assert(
				!isInstructionTriviallyDead(&I, &TLI)
						&& "Dead instructions should have been removed before calling this");
		ConstantRange CR = ConstantRange::makeExactICmpRegion(Pred, *C);
		if (inversed) {
			CR = CR.inverse();
		}
		auto seen = seenCompares.find(lhs);
		if (seen != seenCompares.end()) {
			bool replaced = false;
			for (const auto& [DomPred, DominatingCR] : seen->second) {
				assert(DomPred);
				assert(
						DomPred != &I
								&& "This must not happen because iteration should be only forward");
				if (CR == DominatingCR) {
					replaced = true;
					replaceInstUsesWith(I, DomPred);
					Worklist.push(&I); // must push to worklist to remove from function later
					break;
				}
			}
			if (!replaced) {
				// attempt to search for inversed predicated and create its negation and use it instead of this
				auto CRInv = CR.inverse();
				for (const auto& [DomPred, DominatingCR] : seen->second) {
					assert(DomPred);
					assert(
							DomPred != &I
									&& "This must not happen because iteration should be only forward");
					if (CRInv == DominatingCR) {
						Builder.SetInsertPoint(DomPred->getNextNode());
						if (inversed && DomPred->getNextNode() == &I) {
							// use this as representative inversion DomPred if this is not of DomPred term just behind it
							seen->second.push_back( { &I, CR });
							break;
						} else {
							assert(!match(DomPred, m_Not(m_Value())));
							auto DomPredInv = Builder.CreateNot(DomPred);
							replaceInstUsesWith(I, DomPredInv);
							Worklist.push(&I); // must push to worklist to remove from function later
							Worklist.pushValue(DomPredInv);
							seen->second.push_back(
									{ dyn_cast<Instruction>(DomPredInv), CRInv }); // register it for others to use
							replaced = true;
							break;
						}
					}
				}
			}

			if (replaced) {
				change = true;
				if (inversed)
					Worklist.pushValue(I.getOperand(0));
			} else {
				// add into seen
				seen->second.push_back( { &I, CR });
			}
		} else {
			// add into seen
			seenCompares[lhs] = { { &I, CR } };
		}
	}
	return change;
}

}
