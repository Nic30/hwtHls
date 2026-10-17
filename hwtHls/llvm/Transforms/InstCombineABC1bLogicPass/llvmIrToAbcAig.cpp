#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/llvmIrToAbcAig.h>
#include <llvm/IR/Constant.h>
#include <llvm/IR/Instruction.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Instructions.h>

using namespace llvm;

namespace hwtHls {

LlvmIrToAbcAig::LlvmIrToAbcAig() {
	abcFrame = Abc_FrameGetGlobalFrame();
	// Create AIG network: structural hashing (STRASH), AIG functionality
	net = Abc_NtkAlloc(ABC_NTK_STRASH, ABC_FUNC_AIG, 64);
	aig = static_cast<Abc_Aig_t *>(net->pManFunc);
	c1 = Abc_AigConst1(net);
}

LlvmIrToAbcAig::~LlvmIrToAbcAig() {
	if (net) {
		Abc_NtkDelete(net);
	}
	// abcFrame is global; do not delete
}

void LlvmIrToAbcAig::translate(const SetVector<Value *> &inputs,
						  const SetVector<Instruction *> &outputs) {
	if (!net || !aig) {
		llvm_unreachable("LlvmIrToAbcAig: network not initialized");
	}

	translationCache.clear();
	ioMap.clear();
	SetVector<Instruction*> worklist;
	// Create primary inputs
	for (Value *i : inputs) {
		if (!i->getType()->isIntegerTy(1)) {
			llvm_unreachable("LlvmIrToAbcAig: only i1 inputs are supported");
		}
		Abc_Obj_t *pi = Abc_NtkCreatePi(net);
		ioMap[Abc_ObjName(pi)] = i;
		translationCache[i] = pi;
#ifndef NDEBUG
		if (auto I = dyn_cast<Instruction>(i)) {
			assert(!outputs.contains(I));
		}
#endif
	}

	// Translate instructions from begin to end (inclusive)
	while (!worklist.empty()) {
		auto *I = worklist.pop_back_val();
		translateInstruction(I);
	}

	// Create primary outputs
	for (Instruction *v : outputs) {
		if (!v->getType()->isIntegerTy(1)) {
			llvm_unreachable("LlvmIrToAbcAig: only i1 outputs are supported");
		}
		Abc_Obj_t *po = Abc_NtkCreatePo(net);
		ioMap[Abc_ObjName(po)] = v;
		Abc_Obj_t *fanin = getOrTranslateValue(v);
		Abc_ObjAddFanin(po, fanin);
	}

	// Cleanup and check
	Abc_AigCleanup(aig);
	Abc_NtkCheck(net);
}

Abc_Obj_t *LlvmIrToAbcAig::getOrTranslateValue(Value *v) {
	auto it = translationCache.find(v);
	if (it != translationCache.end()) {
		return it->second;
	}

	if (auto *C = dyn_cast<ConstantInt>(v)) {
		if (!C->getType()->isIntegerTy(1)) {
			llvm_unreachable("LlvmIrToAbcAig: only i1 constants are supported");
		}
		Abc_Obj_t *res = c1;
		if (!C->isOne()) {
			res = Abc_ObjNot(res);
		}
		translationCache[v] = res;
		return res;
	}
	if (auto * I = dyn_cast<Instruction>(v)) {
		return translateInstructionImpl(I);
	}
	// undef, poison and alike should have been prefilled translationCache because they should be in inputs
	errs() << *v << "\n";
	llvm_unreachable(
		"LlvmIrToAbcAig: value not in cache and not a supported value");
}

void LlvmIrToAbcAig::translateInstruction(Instruction *I) {
	if (!I) {
		llvm_unreachable("LlvmIrToAbcAig: instruction is null");
	}

	if (!I->getType()->isIntegerTy(1)) {
		llvm_unreachable("LlvmIrToAbcAig: only i1 instructions are supported");
	}

	Abc_Obj_t *abcObj = translateInstructionImpl(I);
	translationCache[I] = abcObj;
}

Abc_Obj_t *LlvmIrToAbcAig::translateInstructionImpl(Instruction *I) {
	if (auto *BO = dyn_cast<BinaryOperator>(I)) {
		Value *lhs = BO->getOperand(0);
		Value *rhs = BO->getOperand(1);

		if (!lhs->getType()->isIntegerTy(1) ||
			!rhs->getType()->isIntegerTy(1)) {
			llvm_unreachable(
				"LlvmIrToAbcAig: binary operator operands must be i1");
		}

		Abc_Obj_t *l = getOrTranslateValue(lhs);
		Abc_Obj_t *r = getOrTranslateValue(rhs);

		switch (BO->getOpcode()) {
		case Instruction::And:
			return Abc_AigAnd(aig, l, r);
		case Instruction::Or:
			return Abc_AigOr(aig, l, r);
		case Instruction::Xor:
			return Abc_AigXor(aig, l, r);
		default:
			llvm_unreachable("LlvmIrToAbcAig: unsupported binary operator");
		}
	} else if (auto *sel = dyn_cast<SelectInst>(I)) {
		Value *cond = sel->getCondition();
		Value *vTrue = sel->getTrueValue();
		Value *vFalse = sel->getFalseValue();

		if (!cond->getType()->isIntegerTy(1) ||
			!vTrue->getType()->isIntegerTy(1) ||
			!vFalse->getType()->isIntegerTy(1)) {
			llvm_unreachable("LlvmIrToAbcAig: select operands must be i1");
		}

		Abc_Obj_t *c = getOrTranslateValue(cond);
		Abc_Obj_t *t = getOrTranslateValue(vTrue);
		Abc_Obj_t *f = getOrTranslateValue(vFalse);

		// Mux(c, t, f) = (c & t) | (~c & f)
		Abc_Obj_t *nt = Abc_AigAnd(aig, c, t);
		Abc_Obj_t *nf = Abc_AigAnd(aig, Abc_ObjNot(c), f);
		return Abc_AigOr(aig, nt, nf);
	} else if (auto *icmp = dyn_cast<ICmpInst>(I)) {
		Value *lhs = icmp->getOperand(0);
		Value *rhs = icmp->getOperand(1);

		if (!lhs->getType()->isIntegerTy(1) ||
			!rhs->getType()->isIntegerTy(1)) {
			llvm_unreachable(
				"LlvmIrToAbcAig: only i1 comparisons are supported");
		}

		Abc_Obj_t *l = getOrTranslateValue(lhs);
		Abc_Obj_t *r = getOrTranslateValue(rhs);

		switch (icmp->getPredicate()) {
		case CmpInst::ICMP_EQ: {
			// eq = (l & r) | (~l & ~r)
			Abc_Obj_t *and1 = Abc_AigAnd(aig, l, r);
			Abc_Obj_t *and2 = Abc_AigAnd(aig, Abc_ObjNot(l), Abc_ObjNot(r));
			return Abc_AigOr(aig, and1, and2);
		}
		case CmpInst::ICMP_NE:
			// ne = l ^ r
			return Abc_AigXor(aig, l, r);
		default:
			llvm_unreachable("LlvmIrToAbcAig: unsupported ICMP predicate");
		}
	}

	llvm_unreachable("LlvmIrToAbcAig: not a supported instruction class");
}
}