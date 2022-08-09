#include "bitPartsUseAnalysis.h"
#include <llvm/IR/IRBuilder.h>
#include "targets/intrinsic/bitrange.h"

using namespace llvm;

namespace hwtHls {

BitPartsUseAnalysisContext::BitPartsUseAnalysisContext(
		ConstBitPartsAnalysisContext::InstructionToVarBitConstraintMap &_constraints) :
		constraints(_constraints) {
}

void BitPartsUseAnalysisContext::updateUseMaskEntirelyUsed(
		const llvm::Value *V) {
	if (auto I = dyn_cast<Instruction>(V)) {
		auto cur = constraints.find(I);
		if (cur != constraints.end()) {
			updateUseMaskEntirelyUsed(I);
		}
	}
}

void BitPartsUseAnalysisContext::updateUseMaskEntirelyUsed(
		const llvm::Instruction *I) {
	auto cur = constraints.find(I);
	if (cur != constraints.end()) {
		// the use mask should be already propagated
		// or will be propagated once the use is found
		APInt ncm = cur->second->getNonConstBitMask();
		if (cur->second->useMask == (ncm | cur->second->useMask))
			return;
		else {
			cur->second->useMask |= ncm;
		}
	}
	for (const Value *op : I->operand_values()) {
		if (auto I2 = dyn_cast<Instruction>(op)) {
			auto cur = constraints.find(I2);
			if (cur != constraints.end()) {
				APInt useAll = APInt::getAllOnesValue(
						cur->second.get()->useMask.getBitWidth());
				updateUseMask(I2, *cur->second, useAll);
			} else {
				updateUseMaskEntirelyUsed(op);
			}
		}
	}
}

void BitPartsUseAnalysisContext::updateUseMask(const llvm::Value *V,
		const APInt &newMask) {
	if (auto I = dyn_cast<Instruction>(V)) {
		auto cur = constraints.find(I);
		if (cur != constraints.end()) {
			updateUseMask(I, *cur->second, newMask);
		} else {
			updateUseMaskEntirelyUsed(I);
		}
	}
}

void BitPartsUseAnalysisContext::updateUseMask(const llvm::Value *V,
		VarBitConstraint &vbc, const APInt &newMask) {
	const APInt &oldMask = vbc.useMask;
	APInt _newMask = newMask & vbc.getNonConstBitMask();
	bool someNewBitsSet = (~oldMask & _newMask) != 0;
	if (someNewBitsSet) {
		vbc.useMask |= _newMask;
		if (auto I = dyn_cast<Instruction>(V))
			propagateUseMaskInstruction(I, vbc);
	}
}

void BitPartsUseAnalysisContext::propagateUseMaskInstruction(
		const Instruction *I, const VarBitConstraint &vbc) {
	assert(vbc.useMask != 0);
	if (auto *SI = dyn_cast<PHINode>(I)) {
		propagateUseMaskPHINode(SI, vbc);
		return;
		// [todo]
		//} else if (auto *SI = dyn_cast<SelectInst>(I)) {
		//	return visitSelectInst(SI);
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
	}
	// unknown instruction propagate with use all
	for (const Use &op : I->operands()) {
		updateUseMaskEntirelyUsed(op.get());
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
		VarBitConstraint &base = *constraints[C->getArgOperand(0)];
		VarBitConstraint &sh = *constraints[C->getArgOperand(1)];
		if (sh.replacements.size() == 1
				&& dyn_cast<ConstantInt>(sh.replacements[0].src)) {
			if (const ConstantInt *shConst = dyn_cast<ConstantInt>(
					sh.replacements[0].src)) {
				auto w = vbc.useMask.getBitWidth();
				auto off = shConst->getLimitedValue();
				APInt m(base.useMask.getBitWidth(), 0);
				m.setBits(off, off + w);
				updateUseMask(C->getArgOperand(0), base, m);
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

}
