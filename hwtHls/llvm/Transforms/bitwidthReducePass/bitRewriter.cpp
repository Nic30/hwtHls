#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitRewriter.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <iostream>

using namespace llvm;
namespace hwtHls {

BitPartsRewriter::BitPartsRewriter(
		ConstBitPartsAnalysisContext::InstructionToVarBitConstraintMap &_constraints) :
		constraints(_constraints) {
}

std::vector<KnownBitRangeInfo> iterUsedBitRanges(IRBuilder<> *Builder,
		const APInt &useMask, const VarBitConstraint &vbc) {
	std::vector<KnownBitRangeInfo> res;
	unsigned dstBeginOffset = 0;
	iterUsedBitRangeSlices(useMask,
			[Builder, &dstBeginOffset, &vbc, &res](size_t offset,
					size_t width) {
				for (auto &i : vbc.slice(Builder, offset, width).replacements) {
					i.dstBeginBitI = dstBeginOffset;
					VarBitConstraint::srcUnionPushBackWithMerge(res, i);
					dstBeginOffset += i.srcWidth;
				}
			});

	return res;
}

llvm::Value* BitPartsRewriter::rewriteKnownBitRangeInfo(IRBuilder<> *Builder,
		const KnownBitRangeInfo &kbri) {
	auto *T = cast<IntegerType>(kbri.src->getType());
	if (kbri.srcBeginBitI == 0 && kbri.srcWidth == (T ? T->getBitWidth() : 1)) {
		// rewrite to self without change
		return const_cast<llvm::Value*>(kbri.src);
	} else {
		// must select specific bits
		if (auto *c = dyn_cast<ConstantInt>(kbri.src)) {
			return Builder->getInt(
					c->getValue().shl(kbri.srcBeginBitI).trunc(kbri.srcWidth));
		} else {
			llvm::Value *src = const_cast<Value*>(kbri.src);
			unsigned offset = kbri.srcBeginBitI;
			// check for possible replace of src
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
				return CreateBitRangeGetConst(Builder, src, offset,
						kbri.srcWidth);
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
	IRBuilder<> b(&I);
	auto *newTy = b.getIntNTy(vbc.useMask.countPopulation());
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
	//errs() << "\nexpandConstBits: " << origVal << " " << *origVal << "    "
	//		<< reducedVal;
	//if (reducedVal)
	//	errs() << " " << *reducedVal;
	//errs() << "  " << vbc << "\n";
	for (const KnownBitRangeInfo &kbri : vbc.replacements) {
		if (kbri.src == origVal) {
			// cut bits before and after this chunk
			auto useMask = vbc.useMask.lshr(actualWidth).trunc(kbri.srcWidth);
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
							assert(kbri.srcWidth > lastUsedIndex);
							size_t unusedPrefixWidth = kbri.srcWidth
									- lastUsedIndex;
							auto *v = UndefValue::get(
									IntegerType::getIntNTy(b->getContext(),
											unusedPrefixWidth));
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
			if (lastUsedIndex != kbri.srcWidth) {
				assert(kbri.srcWidth > lastUsedIndex);
				size_t remainderWidth = kbri.srcWidth - lastUsedIndex;
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
			if (isa<ConstantInt>(kbri.src) || isa<UndefValue>(kbri.src)) {
				// if it is constant it was removed from reducedVal and thus it should
				// not be used in bit offset computation
				reducedBitCnt += w;
			}
		}
	}

	return CreateBitConcat(b, concatMembers);
}

void BitPartsRewriter::rewriteInstructionOperands(llvm::Instruction *I) {
	unsigned opI = 0;
	//PHINode *phi = dyn_cast<PHINode>(I);
	//assert(!phi);
	for (Value *_val : I->operands()) {
		auto v = constraints.find(_val);
		if (v != constraints.end()) {
			// if operand is a subject for replacement
			// [fixme] phi instructions must always remain at the top of the block
			auto newVal = rewriteIfRequired(_val);
			//if (newVal == nullptr) {
			//	_val->replaceAllUsesWith(UndefValue::get(_val->getType()));
			//} else
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
		if (constr != constraints.end()) {
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
			val = rewriteKnownBitRangeInfoVector(&b,
					iterUsedBitRanges(&b, vbc.useMask, *constr->second));

		}
		newPhi->addIncoming(val, pred);
		opI += 2;
	}
	return newPhi;
}

}
