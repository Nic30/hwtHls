#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitRewriter.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <iostream>

using namespace llvm;
namespace hwtHls {

BitPartsRewriter::BitPartsRewriter(BitPartsConstraints &_constraints,
		std::function<bool(llvm::Instruction&)> mayModifyExistingInstr) :
		constraints(_constraints), mayModifyExistingInstr(
				mayModifyExistingInstr) {
}

std::vector<KnownBitRangeInfo> iterUsedBitRanges(const APInt &useMask,
		const VarBitConstraint &vbc) {
	std::vector<KnownBitRangeInfo> res;
	unsigned dstBeginOffset = 0;
	iterUsedBitRangeSlices(useMask,
			[&dstBeginOffset, &vbc, &res](size_t offset, size_t width) {
				for (auto &i : vbc.slice(offset, width).replacements) {
					i.dstBeginBitI = dstBeginOffset;
					VarBitConstraint::srcUnionPushBackWithMerge(res, i, 0,
							i.width);
					dstBeginOffset += i.width;
				}
			});

	return res;
}

llvm::Value* BitPartsRewriter::rewriteKnownBitRangeInfo(IRBuilder<> *Builder,
		const KnownBitRangeInfo &kbri) {
	auto *T = cast<IntegerType>(kbri.src->getType());
	if (kbri.srcBeginBitI == 0 && kbri.width == (T ? T->getBitWidth() : 1)) {
		// rewrite to self without change
		return const_cast<llvm::Value*>(kbri.src);
	} else {
		// must select specific bits
		if (auto *c = dyn_cast<ConstantInt>(kbri.src)) {
			return Builder->getInt(
					c->getValue().shl(kbri.srcBeginBitI).trunc(kbri.width));
		} else {
			llvm::Value *src = const_cast<Value*>(kbri.src);
			unsigned offset = kbri.srcBeginBitI;
			// check for possible replace of src
			if (auto *I = dyn_cast<llvm::Instruction>(src)) {
				auto repl = replacementCache.find(I);
				if (repl != replacementCache.end()) {
					// if I is truly replaced
					if (repl->second != I) {
						// resolve new offset because replacement may have some bits at beginning removed
						auto constr = constraints.findInConstraints(I);
						assert(constr);
						const auto &useMask = constr->useMask;
						auto noOfZerosInUseMaskBeforeThisSlice =
								(~useMask.trunc(offset)).popcount();
						assert(offset >= noOfZerosInUseMaskBeforeThisSlice);
						offset -= noOfZerosInUseMaskBeforeThisSlice;
						src = repl->second;
					}
				}
			}
			return CreateBitRangeGetConst(Builder, src, offset, kbri.width);
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
	assert(
			!vbc.useMask.isAllOnes()
					&& "If this was the case it should not be required to rewrite this PHINode (only its incomming values)");
	IRBuilder<> b(&I);
	auto *newTy = b.getIntNTy(vbc.useMask.popcount());
	auto *res = b.CreatePHI(newTy, I.getNumOperands(), I.getName());
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::rewriteSelect(llvm::SelectInst &I,
		const VarBitConstraint &vbc) {
	// @note use mask is guaranteed to be 0 for bits which does not require select
	//   so we do not need to check if we can reduce something
	// @note if result is constant this should not be rewritten instead the constant should be used in every use
	IRBuilder<> b(&I);

	auto T = constraints.findInConstraints(I.getTrueValue());
	Value *tVal = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(vbc.useMask, *T));
	assert(tVal && "This can not be null because it has use (this one)");
	auto F = constraints.findInConstraints(I.getFalseValue());
	Value *fVal = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(vbc.useMask, *F));
	assert(fVal && "This can not be null because it has use (this one)");
	Value *c = rewriteIfRequired(I.getCondition());
	assert(c && "This can not be null because it has use (this one)");
	Value *res;
	if (c == I.getCondition() && tVal == I.getTrueValue()
			&& fVal == I.getFalseValue()) {
		res = &I;
	} else {
		res = b.CreateSelect(c, tVal, fVal, I.getName());
	}
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::rewriteBinaryOperatorBitwise(
		llvm::BinaryOperator &I, const VarBitConstraint &vbc) {
	IRBuilder<> b(&I);
	auto lhs = constraints.findInConstraints(I.getOperand(0));
	Value *LHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(vbc.useMask, *lhs));
	auto rhs = constraints.findInConstraints(I.getOperand(1));
	Value *RHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(vbc.useMask, *rhs));
	Value *res;
	if (LHS == I.getOperand(0) && RHS == I.getOperand(1)) {
		res = &I;
	} else {
		res = b.CreateBinOp(I.getOpcode(), LHS, RHS, I.getName());
	}
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::rewriteCmpInst(llvm::CmpInst &I,
		const VarBitConstraint &vbc) {
	IRBuilder<> b(&I);
	auto lVbc = constraints.findInConstraints(I.getOperand(0));
	Value *LHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(vbc.operandUseMask[0], *lVbc));
	auto rVbc = constraints.findInConstraints(I.getOperand(1));
	Value *RHS = rewriteKnownBitRangeInfoVector(&b,
			iterUsedBitRanges(vbc.operandUseMask[1], *rVbc));
	Value *res;
	if (LHS == I.getOperand(0) && RHS == I.getOperand(1)) {
		res = &I;
	} else {
		res = b.CreateCmp(I.getPredicate(), LHS, RHS, I.getName());
	}
	replacementCache[&I] = res;
	return res;
}

llvm::Value* BitPartsRewriter::expandConstBits(IRBuilder<> *b,
		llvm::Value *origVal, llvm::Value *reducedVal,
		const VarBitConstraint &vbc) {
	unsigned reducedValWidth = 0;
	if (reducedVal && origVal->getType()->isIntegerTy()) {
		assert(
				reducedVal->getType()->getIntegerBitWidth()
						<= origVal->getType()->getIntegerBitWidth());
		reducedValWidth = reducedVal->getType()->getIntegerBitWidth();
	}
	if (origVal->getType()->getIntegerBitWidth() == reducedValWidth) {
		assert(reducedVal);
		return reducedVal; // nothing to pad
	}
	size_t reducedBitCnt = 0; // iterate through the bit ranges, push known bit ranges and reducedVal bit ranges to a concatenation
	// low first
	size_t actualWidth = 0;
	// this is used because we potentially cut off bits from the origVal vector
	// and we want to update information for reducedVal vector
	std::vector<llvm::Value*> concatMembers;
	// reduced bits are those for which useMask is 0
	// those and constants are removed from value and must be put back as constant or undef when expanding value

	for (const KnownBitRangeInfo &kbri : vbc.replacements) {
		if (kbri.src == origVal) {
			// cut bits before and after this chunk
			auto useMask = vbc.useMask.lshr(actualWidth).trunc(kbri.width);
			// value uses itself as a replacement = this was not replaced but may have some bits cut off
			// :note: this is common for PHIs
			assert(kbri.srcBeginBitI >= reducedBitCnt);
			size_t chunkOffset = actualWidth;
			size_t lastUsedIndex = 0;
			// translate bit positions to reducedVal and select only those bits which really do exists, fill rest with undef
			iterUsedBitRangeSlices(useMask,
					[&lastUsedIndex, &kbri, &actualWidth, &reducedBitCnt,
							&concatMembers, chunkOffset, b, reducedVal](
							size_t offset, size_t chunkWidth) {
						if (offset > lastUsedIndex) {
							// add padding before this segment
							assert(kbri.width > lastUsedIndex);
							size_t unusedPrefixWidth = offset - lastUsedIndex;
							assert(unusedPrefixWidth > 0);
							auto *Ty = IntegerType::getIntNTy(b->getContext(),
									unusedPrefixWidth);
							auto *v = UndefValue::get(Ty);
							concatMembers.push_back(v);
							actualWidth += unusedPrefixWidth;
							reducedBitCnt += unusedPrefixWidth;
						}
						assert(chunkOffset + offset >= reducedBitCnt);
						assert(reducedVal != nullptr);
						auto *v = CreateBitRangeGetConst(b, reducedVal,
								chunkOffset + offset - reducedBitCnt,
								chunkWidth);
						concatMembers.push_back(v);
						actualWidth += chunkWidth;
						lastUsedIndex = offset + chunkWidth;
					});
			if (lastUsedIndex != kbri.width) {
				assert(kbri.width > lastUsedIndex);
				size_t remainderWidth = kbri.width - lastUsedIndex;
				auto *v = UndefValue::get(
						IntegerType::getIntNTy(b->getContext(),
								remainderWidth));
				concatMembers.push_back(v);
				actualWidth += remainderWidth;
				reducedBitCnt += remainderWidth;
			}

		} else {
			auto *v = rewriteKnownBitRangeInfo(b, kbri);
			concatMembers.push_back(v);
			size_t w = v->getType()->getIntegerBitWidth();
			actualWidth += w;
			// if it is of some known value other than itself it is not computed by this instruction and thus reduced
			reducedBitCnt += w;
		}
	}
	return CreateBitConcat(b, concatMembers);
}

llvm::Instruction* BitPartsRewriter::rewriteInstructionOperands(
		llvm::Instruction *I) {
	unsigned opI = 0;
	llvm::Instruction *IToUpdate = I;
	for (Value *_val : I->operands()) {
		auto v = constraints.findInConstraints(_val);
		if (v) {
			// if operand is a subject for replacement
			// [fixme] phi instructions must always remain at the top of the block
			auto newVal = rewriteIfRequired(_val);
			if (_val != newVal) {
				IRBuilder<> b(I);
				auto newValExpanded = expandConstBits(&b, _val, newVal, *v);
				if (!mayModifyExistingInstr(*I) && IToUpdate == I) {
					// lazy construction of copy of instruction
					IToUpdate = I->clone();
					IToUpdate->setName(I->getName());
					IToUpdate->insertAfter(I);
					replacementCache[I] = IToUpdate;
				}
				assert(newValExpanded);
				IToUpdate->setOperand(opI, newValExpanded);
			}
		}
		opI++;
	}
	return IToUpdate;
}

// @note we can not remove instruction immediately when rewritten because
// it may result in breaking of iterators and would require an update everywhere where instr. iterator is used
llvm::Value* BitPartsRewriter::rewriteIfRequired(llvm::Value *V) {
	if (auto *I = dyn_cast<llvm::Instruction>(V)) {
		//	if (!dyn_cast<PHINode>(&I))
		//		continue;
		auto repl = replacementCache.find(I);
		if (repl != replacementCache.end())
			return repl->second;
		auto v = constraints.findInConstraints(I);
		if (v) {
			VarBitConstraint &vbc = *v;
			if (vbc.useMask == 0) {
				return nullptr; // no rewrite required because this will be entirely removed
			}
			// rewrite instructions which may have some bits reduced and are not bit concat/slice
			if (auto *CI = dyn_cast<llvm::CmpInst>(I)) {
				return rewriteCmpInst(*CI, vbc);
			} else if (vbc.useMask.isAllOnes()) {
				// case where no bits are discarded and instruction is used as is, with potentially updated operands
				replacementCache[I] = I;
				if (!isa<PHINode>(I)) {
					// if it is PHINode it will be done later in rewritePHINodeArgsIfRequired
					// because phi argument values must be constructed in predecessor block.
					return rewriteInstructionOperands(I);
				}
				return I;
			} else if (auto *PHI = dyn_cast<PHINode>(I)) {
				return rewritePHINode(*PHI, vbc);
			} else if (auto *SI = dyn_cast<llvm::SelectInst>(I)) {
				return rewriteSelect(*SI, vbc);
			} else if (auto *BO = dyn_cast<BinaryOperator>(I)) {
				auto o = BO->getOpcode();
				if (o == Instruction::BinaryOps::And
						|| o == Instruction::BinaryOps::Or
						|| o == Instruction::BinaryOps::Xor)
					return rewriteBinaryOperatorBitwise(*BO, vbc);
			} else if (auto *C = dyn_cast<CallInst>(I)) {
				if (IsBitConcat(C) || IsBitRangeGet(C)) {
					// original will be used instead
					replacementCache[I] = nullptr;
					return nullptr;
				}
			} else if (isa<CastInst>(I)) {
				// original will be used instead
				replacementCache[I] = nullptr;
				return nullptr;
			} else {
				assert(
						vbc.replacements.size() == 1
								&& vbc.replacements.back().src == I
								&& "If this is not reducible instruction it should not be modified");
			}
		}
		replacementCache[I] = I;
		V = rewriteInstructionOperands(I);
	}
	return V;
}

llvm::Value* BitPartsRewriter::rewriteIfRequiredAndExpand(llvm::Value *V) {
	auto *replacement = rewriteIfRequired(V);
	if (auto *I = dyn_cast<Instruction>(V)) {
		auto v = constraints.findInConstraints(I);
		if (v) {
			IRBuilder<> b(I);
			VarBitConstraint &vbc = *v;
			return expandConstBits(&b, V, replacement, vbc);
		}
	}
	assert(replacement == V);
	return replacement;
}

llvm::Value* BitPartsRewriter::rewritePHINodeArgsIfRequired(
		llvm::PHINode *phi) {
	APInt phiUseMask = APInt::getAllOnes(phi->getType()->getIntegerBitWidth());
	auto phiConstr = constraints.findInConstraints(phi);
	if (phiConstr) {
		VarBitConstraint &vbc = *phiConstr;
		phiUseMask = vbc.useMask;
		if (phiUseMask.isZero()) {
			for (auto &v : phi->incoming_values()) {
				// clear values of PHI which is entirely replaced to allow DCE
				v.set(UndefValue::get(v.get()->getType()));
			}
			return phi; // no rewrite required because this is not used
		}
	}
	auto _newPhi = replacementCache.find(phi);
	if (_newPhi == replacementCache.end()) {
		// The replacement value should be already generated from BitPartsRewriter::rewritePHINode
		// This must be one of newly generated PHINodes.
		replacementCache[phi] = phi;
		_newPhi = replacementCache.find(phi);
	}

	llvm::PHINode *newPhi = dyn_cast<PHINode>(_newPhi->second);
	assert(newPhi != nullptr);
	assert(phi != newPhi || phiUseMask.isAllOnes());

	IRBuilder<> b(phi);
	unsigned opI = 0;
	for (BasicBlock *pred : phi->blocks()) {
		Value *val = phi->getIncomingValueForBlock(pred);
		auto constr = constraints.findInConstraints(val);
		if (constr) {
			// if operand is a subject for replacement

			// [fixme]  phi instructions must always remain at the top of the block
			// at the end of the block where this value comes from

			// resolve where value for phi node should be materialized
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
				//assert(
				//		BasicBlock::iterator(insertPoint) == insertPoint->getParent()->begin()
				//				|| isa<PHINode>(insertPoint->getPrevNode()));
				b.SetInsertPoint(insertPoint);
			}
			// materialize phi operand
			auto *_val = rewriteKnownBitRangeInfoVector(&b,
					iterUsedBitRanges(phiUseMask, *constr));
			if (!_val->hasName() && val->hasName() && isa<Instruction>(_val)) {
				_val->setName(val->getName());
			}
			val = _val;
		}
		if (newPhi == phi) {
			phi->setIncomingValueForBlock(pred, val);
		} else {
			newPhi->addIncoming(val, pred);
		}
		opI += 2;
	}
	if (newPhi != phi && newPhi->isSameOperationAs(phi)) {
		_newPhi->second = phi;
		newPhi->replaceAllUsesWith(phi);
		newPhi->eraseFromParent();
		newPhi = phi;
	}
	if (newPhi != phi) {
		for (auto &v : phi->incoming_values()) {
			// clear values of PHI which is entirely replaced to allow DCE
			v.set(UndefValue::get(v.get()->getType()));
		}
	}
	return newPhi;
}

void BitPartsRewriter::addReplacement(llvm::Value *_I,
		llvm::Value *replacement) {
	if (auto *I = dyn_cast<Instruction>(_I))
		replacementCache[I] = replacement;
}

}
