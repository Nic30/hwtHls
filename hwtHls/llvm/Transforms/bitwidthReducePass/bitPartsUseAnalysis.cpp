#include "pybind/llvmIrCommon.h"
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitPartsUseAnalysis.h>
#include <llvm/IR/Constant.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/bitWidthInfo.h>

using namespace llvm;

namespace hwtHls {

BitPartsUseAnalysisContext::BitPartsUseAnalysisContext(
		BitPartsConstraints &_constraints) :
		constraints(_constraints) {
}

void BitPartsUseAnalysisContext::updateUseMaskEntirelyUsed(
		const llvm::Value *V) {
	if (auto I = dyn_cast<Instruction>(V)) {
		if (!constraints.findInConstraints(I, false)) {
			return; // untracked value, which will not be rewritten
		}
		updateUseMaskEntirelyUsed(I);
	}
}

std::optional<bool> BitPartsUseAnalysisContext::getKnownBitBoolValue(
		const llvm::Value *V) {
	assert(V->getType()->getIntegerBitWidth() == 1);
	if (auto *VC = dyn_cast<ConstantInt>(V)) {
		if (VC->getZExtValue()) {
			return true;
		} else {
			return false;
		}
	} else {
		auto cur = constraints.findInConstraints(V, false);
		if (!cur)
			return {};
		VarBitConstraint& kb = *cur;
		auto &replacement = kb.replacements[0];
		if (auto replacementV = dyn_cast<ConstantInt>(replacement.src)) {
			assert(replacement.srcBeginBitI == 0);
			assert(replacement.width == 1);
			return replacementV->getZExtValue();
		}
		return {};
	}
}


void BitPartsUseAnalysisContext::updateUseMaskEntirelyUsedOperand(
		const llvm::Value *op) {
	if (auto I2 = dyn_cast<Instruction>(op)) {
		if (auto cur = constraints.findInConstraints(I2, true)) {
			APInt useAll = APInt::getAllOnes(
					cur->useMask.getBitWidth());
			updateUseMask(I2, *cur, useAll);
		} else {
			updateUseMaskEntirelyUsed(op);
		}
	}
}

void BitPartsUseAnalysisContext::updateUseMaskEntirelyUsed(
		const llvm::Instruction *I) {
	if (auto cur = constraints.findInConstraints(I, true)) {
		// the use mask should be already propagated
		// or will be propagated once the use is found
		APInt tcm = cur->getTrullyComputedBitMask(I);
		if (cur->useMask == (tcm | cur->useMask))
			return; // no change
		else {
			cur->useMask |= tcm;
		}
	}

	if (auto SI = dyn_cast<SelectInst>(I)) {
		// case for Select where it is possible to ignore T/F branch
		auto C = getKnownBitBoolValue(SI->getCondition());
		if (C.has_value()) {
			const Value *V;
			if (C.value()) {
				V = SI->getTrueValue();
			} else {
				V = SI->getFalseValue();
			}
			updateUseMaskEntirelyUsedOperand(V);
			return;
		}
	}
	for (const Value *op : I->operand_values()) {
		updateUseMaskEntirelyUsedOperand(op);
	}
}

void BitPartsUseAnalysisContext::updateUseMask(const llvm::Value *V,
		const APInt &newMask) {
	if (auto I = dyn_cast<Instruction>(V)) {
		if (auto cur = constraints.findInConstraints(I, true)) {
			updateUseMask(I, *cur, newMask);
		} else {
			updateUseMaskEntirelyUsed(I);
		}
	}
}

void BitPartsUseAnalysisContext::updateUseMask(const llvm::Value *V,
		VarBitConstraint &vbc, const APInt &newMask) {
	const APInt &oldMask = vbc.useMask;
	assert(newMask.getBitWidth() == oldMask.getBitWidth() && "All masks must have same number of bits as original value");
	APInt _newMask = newMask & vbc.getTrullyComputedBitMask(V);
	auto vStr = printToStr(V);
	bool someNewBitsSet = (~oldMask & _newMask) != 0;
	if (someNewBitsSet) {
		vbc.useMask |= _newMask;
		if (auto I = dyn_cast<Instruction>(V))
			propagateUseMaskInstruction(I, vbc);
	}
	// propagate new use mask also for replacements
	if (_newMask != newMask) {
		// is some bits are not computed directly by this instruction,
		// we have to propagate change to replacements
		for (const KnownBitRangeInfo &r : vbc.replacements) {
			if (isa<ConstantData>(r.src) || r.src == V) {
				continue;
			}
			APInt replUseMask;
			if (V->getType()->isIntegerTy()) {
				replUseMask = newMask.extractBits(r.width, r.dstBeginBitI);
				replUseMask = replUseMask.zext(r.src->getType()->getIntegerBitWidth());
				replUseMask <<= r.srcBeginBitI;
			} else {
				replUseMask = newMask;
			}

			updateUseMask(r.src, replUseMask);
		}
	}
}
bool BitPartsUseAnalysisContext::propageteUseMaskBinaryOperator(const BinaryOperator &I, const VarBitConstraint &vbc) {
	auto o0 = I.getOperand(0);
	auto o1 = I.getOperand(1);
	switch (I.getOpcode()) {
	case llvm::BinaryOperator::And:
	case llvm::BinaryOperator::Or:
	case llvm::BinaryOperator::Xor: {
		//auto width = vbc.useMask.getBitWidth();
		//APInt isConst(width, 0);
		//for (const auto &item : vbc.replacements) {
		//	if (isa<Constant>(item.src)) {
		//		isConst.setBits(item.dstBeginBitI,
		//						item.srcBeginBitI + item.width);
		//	}
		//}
		//APInt isLhs(width, 0);
		//APInt isRhs(width, 0);
		//if (VarBitConstraint *o0Vbc = constraints.findInConstraints(o0, true)) {
		//	isLhs = RangeSequenceIterator::computeEqualityMask(vbc.replacements, o0Vbc->replacements, width);
		//}
		//if (VarBitConstraint* o1Vbc = constraints.findInConstraints(o1, true)) {
		//	isRhs = RangeSequenceIterator::computeEqualityMask(vbc.replacements, o1Vbc->replacements, width);
		//}
		auto trullyUsed = vbc.getTrullyComputedBitMask(&I);
		updateUseMask(o0, vbc.useMask & trullyUsed);//~isConst & ~isRhs);
		updateUseMask(o1, vbc.useMask & trullyUsed);//~isConst & ~isLhs);
		return true;
	}
	//case llvm::BinaryOperator::And: {
	//	// unused if other is 0
	//	// unused if it is known 1
	//	updateUseMask(o0, vbc.useMask);
	//	updateUseMask(o1, vbc.useMask);
	//	return true;
	//}
	//case llvm::BinaryOperator::Or: {
	//	// unused if other is 1
	//	// unused if it is known 0
	//	updateUseMask(o0, vbc.useMask);
	//	updateUseMask(o1, vbc.useMask);
	//	return true;
	//}
	//case llvm::BinaryOperator::Xor: {
	//	// unused if equal
	//	// or known unequal const
	//	updateUseMask(o0, vbc.useMask);
	//	updateUseMask(o1, vbc.useMask);
	//	return true;
	//}
	default:
		return false;
	}
}
void BitPartsUseAnalysisContext::propagateUseMaskInstruction(
		const Instruction *I, const VarBitConstraint &vbc) {
	assert(!vbc.useMask.isZero());
	if (auto *SI = dyn_cast<PHINode>(I)) {
		propagateUseMaskPHINode(SI, vbc);
		return;
	} else if (auto *SI = dyn_cast<SelectInst>(I)) {
		propageteUseMaskSelect(SI, vbc);
		return;
	} else if (auto *C = dyn_cast<CallInst>(I)) {
		propagateUseMaskCallInst(C, vbc);
		return;
	} else if (auto *CI = dyn_cast<CastInst>(I)) {
		auto op = CI->getOpcode();
		if (op == Instruction::CastOps::Trunc) {
			// mark C high bits unused in src
			return propagateUseMaskTrunc(CI, vbc);
		} else if (op == Instruction::CastOps::ZExt
				|| op == Instruction::CastOps::SExt) {
			return propagateUseMaskExt(CI, vbc);
		}
	} else if (auto *BI = dyn_cast<BinaryOperator>(I)) {
		if (propageteUseMaskBinaryOperator(*BI, vbc)) {
			return;
		}
		
	} else if (auto *CMP = dyn_cast<ICmpInst>(I)) {
		if (vbc.operandUseMask.empty()) {
			// case where this ICmpInst is excluded from analysis
		} else {
			assert(vbc.operandUseMask.size() == 2);
			updateUseMask(CMP->getOperand(0), vbc.operandUseMask[0]);
			updateUseMask(CMP->getOperand(1), vbc.operandUseMask[1]);
			return;
		}
	}
	// unknown instruction propagate with use all
	for (const Value *op : I->operand_values()) {
		updateUseMaskEntirelyUsed(op);
	}
	//// or of all user masks
	//bool isUsed = false;
	//for (User *user : I->users()) {
	//	auto u = constraints.find(user);
	//	if (u == constraints.end() || u->second->useMask != 0) {
	//		isUsed = true;
	//		break;
	//	}
	//}
	//if (isUsed) {
	//	if (!i->useMask.isAllOnesValue()) {
	//		i->useMask.setAllBits();
	//	}
	//} else {
	//	if (i->useMask != 0) {
	//		i->useMask.clearAllBits();
	//	}
	//}
}

void BitPartsUseAnalysisContext::propagateUseMaskCallInst(const CallInst *C,
		const VarBitConstraint &vbc) {
	if (IsBitConcat(C)) {
		unsigned off = 0;
		for (const Use &U : C->args()) {
			const Value *O = U.get();
			APInt m = vbc.useMask.lshr(off);
			if (auto *T = dyn_cast<IntegerType>(O->getType())) {
				auto oWidht = T->getBitWidth();
				auto newMask = m.trunc(oWidht);
				updateUseMask(O, newMask);
				off += oWidht;
			}
		}
		return;
	} else if (IsBitRangeGet(C)) {
		VarBitConstraint* base = constraints.findInConstraints(C->getArgOperand(0), true);
		VarBitConstraint* sh = constraints.findInConstraints(C->getArgOperand(1), true);
		if (sh && base && sh->replacements.size() == 1
				&& dyn_cast<ConstantInt>(sh->replacements[0].src)) {
			if (const ConstantInt *shConst = dyn_cast<ConstantInt>(
					sh->replacements[0].src)) {
				auto w = vbc.useMask.getBitWidth();
				auto off = shConst->getLimitedValue();
				APInt m(base->useMask.getBitWidth(), 0);
				m.setBits(off, off + w);
				updateUseMask(C->getArgOperand(0), *base, m);
				return;
			}
		}
	}
	for (const Use &op : C->operands()) {
		updateUseMaskEntirelyUsed(op.get());
	}
}

void BitPartsUseAnalysisContext::propagateUseMaskTrunc(const llvm::CastInst *I,
		const VarBitConstraint &vbc) {
	auto *O = I->getOperand(0);
	updateUseMask(O, vbc.useMask.zext(O->getType()->getIntegerBitWidth()));
}

void BitPartsUseAnalysisContext::propagateUseMaskExt(const llvm::CastInst *I,
		const VarBitConstraint &vbc) {
	auto *O = I->getOperand(0);
	updateUseMask(O, vbc.useMask.trunc(O->getType()->getIntegerBitWidth()));
}

void BitPartsUseAnalysisContext::propagateUseMaskPHINode(const PHINode *I,
		const VarBitConstraint &vbc) {
	// distribute to all operands
	for (const Value *op : I->operand_values()) {
		updateUseMask(op, vbc.useMask);
	}
}

void BitPartsUseAnalysisContext::propageteUseMaskSelect(const SelectInst *I,
		const VarBitConstraint &vbc) {
	// distribute to all operands
	auto C = getKnownBitBoolValue(I->getCondition());
	if (C.has_value()) {
		if (C.value()) {
			updateUseMask(I->getTrueValue(), vbc.useMask);
		} else {
			updateUseMask(I->getFalseValue(), vbc.useMask);
		}
		return;
	}
	updateUseMask(I->getCondition(),
			vbc.useMask.isZero() ? APInt::getZero(1) : APInt::getAllOnes(1));
	updateUseMask(I->getTrueValue(), vbc.useMask);
	updateUseMask(I->getFalseValue(), vbc.useMask);
}

}
