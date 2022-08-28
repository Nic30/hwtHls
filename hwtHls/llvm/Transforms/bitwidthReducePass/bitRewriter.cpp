#include "bitRewriter.h"
#include "../../targets/intrinsic/bitrange.h"

using namespace llvm;
namespace hwtHls {

BitPartsRewriter::BitPartsRewriter(
		ConstBitPartsAnalysisContext::InstructionToVarBitConstraintMap &_constraints) :
		constraints(_constraints) {
}

// @param vbc the slice containers from where to iterate bits, low to high
std::vector<KnownBitRangeInfo> iterUsedBitRanges(IRBuilder<> *Builder,
		const APInt &useMask, const VarBitConstraint &vbc) {
	std::vector<KnownBitRangeInfo> res;

	assert(useMask != 0);
	if (useMask.isAllOnesValue()) {
		return vbc.replacements; // no need for pruning
	}

	// prune values which do not have the specific bit mask set
	int l = -1; // -1 as invalid value
	unsigned dstBeginOffset = 0;
	for (unsigned h = 0; h < useMask.getBitWidth(); ++h) {
		if (l == -1 && useMask[h]) {
			l = h;
		}

		// end of 1 sequence found
		if (l != -1 && (h == useMask.getBitWidth() - 1 || !useMask[h + 1])) {
			// start of 1 sequence, (+1 because [1:0] is 1b)
			unsigned w = h - l + 1;
			for (auto &i : vbc.slice(Builder, l, w).replacements) {
				i.dstBeginBitI = dstBeginOffset;
				VarBitConstraint::srcUnionPushBackWithMerge(res, i);
				dstBeginOffset += i.srcWidth;
			}
			l = -1; // reset start;
		}
	}

	return res;
}

llvm::Value* BitPartsRewriter::rewriteKnownBitRangeInfo(IRBuilder<> *Builder,
		const KnownBitRangeInfo &kbri) {
	auto *T = cast<IntegerType>(kbri.src->getType());
	if (kbri.srcBeginBitI == 0 && kbri.srcWidth == (T ? T->getBitWidth() : 1)) {
		return const_cast<llvm::Value*>(kbri.src);
	} else {
		// must select specific bits
		if (auto *c = dyn_cast<ConstantInt>(kbri.src)) {
			return Builder->getInt(
					c->getValue().shl(kbri.srcBeginBitI).trunc(kbri.srcWidth));
		} else {
			llvm::Value *src = const_cast<Value*>(kbri.src);
			unsigned offset = kbri.srcBeginBitI;
			if (auto *I = dyn_cast<llvm::Instruction>(src)) {
				auto repl = replacementCache.find(I);
				if (repl != replacementCache.end()) {
					// resolve new offset because replacement may have some bits at beginning removed
					auto constr = constraints.find(I);
					assert(constr != constraints.end());
					const auto &useMask = constr->second->useMask;
					auto noOfZerosInUseMaskBeforeThisSlice = (~useMask.trunc(
							offset)).countPopulation();
					offset -= noOfZerosInUseMaskBeforeThisSlice;
					src = repl->second;
				}
			}
			if (kbri.srcWidth != src->getType()->getIntegerBitWidth()) {
				return CreateBitRangeGet(Builder, src,
						Builder->getInt64(offset), kbri.srcWidth);
			} else {
				return src;
			}
		}
	}
}

llvm::Value* BitPartsRewriter::rewriteKnownBitRangeInfoVector(
		IRBuilder<> *Builder, const std::vector<KnownBitRangeInfo> &kbris) {
	if (kbris.size() == 1) {
		// can directly replace, may require slice if src has shift or truncat
		return rewriteKnownBitRangeInfo(Builder, kbris[0]);
	} else {
		std::vector<llvm::Value*> OpsLowFirst;
		for (auto &bi : kbris) {
			auto *res = rewriteKnownBitRangeInfo(Builder, bi);
			OpsLowFirst.push_back(res);
		}

		return CreateBitConcat(Builder, OpsLowFirst);
	}
}

llvm::Value* BitPartsRewriter::rewritePHINode(llvm::PHINode &I,
		const VarBitConstraint &vbc) {
	// rewrite instruction itself, but do not fill the operands, we can not fill operands immediately
	// because this may result in infinite cycle when recursively replacing operands in cyclic SSA.
	IRBuilder<> b(&I);
	llvm::PHINode *res = b.CreatePHI(b.getIntNTy(vbc.useMask.countPopulation()),
			I.getNumOperands(), I.getName());
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::rewriteSelect(llvm::SelectInst &I,
		const VarBitConstraint &vbc) {
	// replace this select with an concatenation of bit which are actually used

	// @note use mask is guaranteed to be 0 for bits which does not require select
	//   so we do not need to check if we can reduce something
	// @note if result is constant this should not be rewritten insteas the constant should be used in every use
	IRBuilder<> b(&I);
	auto &T = constraints[I.getTrueValue()];
	Value *tr = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(&b, vbc.useMask, *T));
	auto &F = constraints[I.getFalseValue()];
	Value *fa = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(&b, vbc.useMask, *F));
	Value *res = b.CreateSelect(rewriteIfRequired(I.getCondition()), tr, fa,
			I.getName());
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::rewriteBinaryOperatorBitwise(
		llvm::BinaryOperator &I, const VarBitConstraint &vbc) {
	IRBuilder<> b(&I);
	auto &lhs = constraints[I.getOperand(0)];
	Value *LHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(&b, vbc.useMask, *lhs));
	auto &rhs = constraints[I.getOperand(1)];
	Value *RHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(&b, vbc.useMask, *rhs));
	Value *res = b.CreateBinOp(I.getOpcode(), LHS, RHS, I.getName());
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::rewriteCmpInst(llvm::CmpInst &I,
		const VarBitConstraint &vbc) {
	IRBuilder<> b(&I);
	auto &lVbc = constraints[I.getOperand(0)];
	Value *LHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(&b, vbc.operandUseMask[0], *lVbc));
	auto &rVbc = constraints[I.getOperand(1)];
	Value *RHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(&b, vbc.operandUseMask[1], *rVbc));
	Value *res = b.CreateCmp(I.getPredicate(), LHS, RHS, I.getName());
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::expandConstBits(IRBuilder<> *b,
		llvm::Value *origVal, llvm::Value *reducedVal,
		const VarBitConstraint &vbc) {
	unsigned reducedValWidth = 0;
	if (reducedVal) {
		reducedValWidth = reducedVal->getType()->getIntegerBitWidth();
	}
	if (origVal->getType()->getIntegerBitWidth() == reducedValWidth) {
		assert(reducedVal);
		return reducedVal; // nothing to pad
	}

	// iterate through the bit ranges, push known bit ranges and reducedVal bit ranges to a concatenation
	// low first
	unsigned reducedValOffset = 0;
	std::vector<llvm::Value*> concatMembers;
	for (const KnownBitRangeInfo &kbri : vbc.replacements) {
		llvm::Value *v;
		if (kbri.src == origVal) {
			if (reducedValOffset == 0 && kbri.srcWidth == reducedValWidth)
				v = const_cast<Value*>(reducedVal);
			else {
				assert(reducedVal);
				v = CreateBitRangeGet(b, reducedVal,
						b->getInt64(reducedValOffset), kbri.srcWidth);
			}
		} else {
			v = rewriteKnownBitRangeInfo(b, kbri);
		}
		concatMembers.push_back(v);
	}
	if (concatMembers.size() == 1)
		return concatMembers[0];

	return CreateBitConcat(b, concatMembers);
}

void BitPartsRewriter::rewriteInstructionOperands(llvm::Instruction *I) {
	// store volatile i16 %val, i16* %ptr, align 2
	unsigned opI = 0;
	//PHINode *phi = dyn_cast<PHINode>(I);
	//assert(!phi);
	for (Value *_val : I->operands()) {
		auto v = constraints.find(_val);
		if (v != constraints.end()) {
			// if operand is a subject for replacement
			// [fixme] phi instructions must always remain at the top of the block
			auto newVal = rewriteIfRequired(_val);
			if (_val != newVal) {
				IRBuilder<> b(I);
				_val = expandConstBits(&b, _val, newVal, *v->second);
				I->setOperand(opI, _val);
			}
		}
		opI++;
	}

}

// @note we can not remove instruction immediately when rewritten because
// it may result in breaking of iterators and would require an update a everywhere where instr. iterator is used
llvm::Value* BitPartsRewriter::rewriteIfRequired(llvm::Value *V) {
	if (auto *I = dyn_cast<llvm::Instruction>(V)) {
		//	if (!dyn_cast<PHINode>(&I))
		//		continue;
		auto repl = replacementCache.find(I);
		if (repl != replacementCache.end())
			return repl->second;
		auto v = constraints.find(I);
		if (v != constraints.end()) {
			VarBitConstraint &vbc = *v->second;
			if (vbc.useMask == 0) {
				return nullptr; // no rewrite required because this will be entirely removed
			}

			if (auto *CI = dyn_cast<llvm::CmpInst>(I)) {
				return rewriteCmpInst(*CI, vbc);
			} else if (auto *PHI = dyn_cast<PHINode>(I)) {
				return rewritePHINode(*PHI, vbc);
			} else if (vbc.useMask.isAllOnesValue()) {
				replacementCache[I] = I;
				rewriteInstructionOperands(I);
				return I;
			} else if (auto *SI = dyn_cast<llvm::SelectInst>(I)) {
				return rewriteSelect(*SI, vbc);
			} else if (auto *BO = dyn_cast<BinaryOperator>(I)) {
				auto o = BO->getOpcode();
				if (o == Instruction::BinaryOps::And
						|| o == Instruction::BinaryOps::Or
						|| o == Instruction::BinaryOps::Xor)
					return rewriteBinaryOperatorBitwise(*BO, vbc);
			}
		}
		replacementCache[I] = I;
		rewriteInstructionOperands(I);
	}
	return V;
}

llvm::Value* BitPartsRewriter::rewritePHINodeArgsIfRequired(
		llvm::PHINode *phi) {
	auto _newPhi = replacementCache.find(phi);
	if (_newPhi == replacementCache.end()) {
		// The replacement value should be already generated from BitPartsRewriter::rewritePHINode
		// This must be one of newly generated PHINodes
		return phi;
	}
	llvm::PHINode *newPhi = dyn_cast<PHINode>(_newPhi->second);

	auto phiConstr = constraints.find(phi);
	if (phiConstr == constraints.end()) {
		return phi;
	}
	VarBitConstraint &vbc = *phiConstr->second;
	assert(newPhi != nullptr);
	IRBuilder<> b(phi);

	unsigned opI = 0;
	for (BasicBlock *pred : phi->blocks()) {
		Value *val = phi->getIncomingValueForBlock(pred);
		auto constr = constraints.find(val);
		if (constr != constraints.end()) { // if operand is a subject for replacement
				// [fixme] phi instructions must always remain at the top of the block
				// at the end of the block where this value comes from
			Instruction *insertPoint = nullptr;
			for (BasicBlock::reverse_iterator pi = pred->rbegin();
					pi != pred->rend(); ++pi) {
				BasicBlock::reverse_iterator predI = pi;
				++predI;
				if (pi == pred->rend() || predI == pred->rend()
						|| !predI->isTerminator()) {
					// if is first terminator
					insertPoint = &*pi;
					break;
				}
			}
			if (insertPoint == nullptr) {
				b.SetInsertPoint(&*pred->getFirstInsertionPt());
			} else {
				b.SetInsertPoint(insertPoint);
			}

			val = rewriteKnownBitRangeInfoVector(&b,
					iterUsedBitRanges(&b, vbc.useMask, *constr->second));

		}
		newPhi->addIncoming(val, pred);
		opI += 2;
	}
	return newPhi;
}

}
