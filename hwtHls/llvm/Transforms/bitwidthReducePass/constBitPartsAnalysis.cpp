#include <hwtHls/llvm/Transforms/bitwidthReducePass/constBitPartsAnalysis.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/phiValueProver.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PatternMatch.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/Transforms/utils/bitWidthInfo.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

VarBitConstraint* BitPartsConstraints::findInConstraints(const llvm::Value *V,
		bool copyFromParent) {
	auto ctx = this;
	while (ctx) {
		auto cur = ctx->constraints.find(V);
		if (cur != ctx->constraints.end()) {
			if (copyFromParent && ctx != this) {
				return &initConstraintMember(V, *cur->second.get());
			}

			return cur->second.get();
		}
		ctx = ctx->parent;
	}
	return nullptr;
}
const VarBitConstraint* BitPartsConstraints::findInConstraints(
		const llvm::Value *V) {
	return findInConstraints(V, false);
}

std::optional<bool> BitPartsConstraints::getKnownBitBoolValue(
		const llvm::Value *V) {
	assert(V->getType()->getIntegerBitWidth() == 1);
	if (auto *VC = dyn_cast<ConstantInt>(V)) {
		if (VC->getZExtValue()) {
			return true;
		} else {
			return false;
		}
	} else {
		auto kb = findInConstraints(V, false);
		if (!kb)
			return {};
		auto &replacement = kb->replacements[0];
		if (auto replacementV = dyn_cast<ConstantInt>(replacement.src)) {
			assert(replacement.srcBeginBitI == 0);
			assert(replacement.width == 1);
			return replacementV->getZExtValue();
		}
		return {};
	}
}

std::unique_ptr<VarBitConstraint> BitPartsConstraints::setKnownBitBoolValue(
		const llvm::Value *V, bool newV) {
	auto kb = constraints.find(V);
	std::unique_ptr<VarBitConstraint> current;
	auto newVbc = std::make_unique<VarBitConstraint>(
			ConstantInt::get(V->getType(), newV));
	if (kb != constraints.end()) {
		current = std::move(kb->second);
		kb->second = std::move(newVbc);
	} else {
		constraints[V] = std::move(newVbc);
	}
	return current;
}

void BitPartsConstraints::dumpConstraints() const {
	for (const auto &c : constraints) {
		if (c.first->getType()->isIntegerTy() && !isa<ConstantInt>(c.first)) {
			dbgs() << c.first << " " << *c.first << "\n";
			dbgs() << "    " << *c.second << "\n";
		}
	}
}

ConstBitPartsAnalysisContext::ConstBitPartsAnalysisContext(
		ConstBitPartsAnalysisContext *parent,
		std::optional<std::function<bool(const llvm::Instruction&)>> analysisPredicate) :
		BitPartsConstraints(parent), analysisPredicate(analysisPredicate), resolvePhiValues(
				false), tryAnalyzeOperandsOfUnsupportedInstructions(true) {
}

void ConstBitPartsAnalysisContext::setShouldResolvePhiValues() {
	resolvePhiValues = true;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitConstantInt(
		const ConstantInt *CI) {
	return initConstraintMember(CI);
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitSelectInst(
		const SelectInst *I) {
	// propagate from ops to this, union of masks an known values
	VarBitConstraint &c = initConstraintMember(I, getIntegerBitWidthOr1(I));
	auto CurC = I->getCondition();
	auto CknownBits = getKnownBitBoolValue(CurC);
	if (CknownBits.has_value()) {
		// condition is known to be constant
		const Value *V;
		if (CknownBits.value()) {
			V = I->getTrueValue();
		} else {
			V = I->getFalseValue();
		}
		c = visitValue(V); // intended copy to c
	} else {
		assert(I->getType() == I->getTrueValue()->getType());
		assert(I->getType() == I->getFalseValue()->getType());

		c = visitValue(I->getTrueValue()); // intended copy to c
		VarBitConstraint &_cF = visitValue(I->getFalseValue());
		assert(_cF.consistencyCheck());
		Instruction *CurCInsr = const_cast<Instruction*>(dyn_cast<Instruction>(
				CurC));
		SmallVector<VarBitConstraint::DetectBitsDrivenByConditionResultItem> bitsDrivenByC;
		if (CurCInsr) {
			// if condition is result of instruction we may potentially use it some output directly
			// without the need for SelectInst
			auto C_VBC = findInConstraints(CurC, true);
			assert(!C_VBC || C_VBC->replacements.size() == 1);
			if (C_VBC && isa<Instruction>(C_VBC->replacements[0].src)) {
				IRBuilder<> Builder(CurCInsr);
				auto &r = C_VBC->replacements[0];
				CurCInsr = dyn_cast<Instruction>(const_cast<Value*>(r.src));
				if (r.srcBeginBitI == 0 && r.width == 1
						&& r.src->getType()->isIntegerTy(1)) {
				} else {
					assert(CurCInsr);
					Builder.SetInsertPoint(CurCInsr);
					CurCInsr = dyn_cast<Instruction>(
							CreateBitRangeGetConst(&Builder,
									const_cast<Value*>(r.src), r.srcBeginBitI,
									r.width));
				}
				// errs() << "Analyzing " << *I << " with C: " << *CurCInsr << "\n";
				VarBitConstraint::detectBitsDrivenByCondition(*C_VBC, c, _cF,
						bitsDrivenByC);
				c.srcUnionInplace(_cF, I, true);
				assert(c.consistencyCheck());
				KnownBitRangeInfo Cond_n(1);
				bool usesCond_n =
						any_of(bitsDrivenByC,
								[](
										VarBitConstraint::DetectBitsDrivenByConditionResultItem &v) {
									return v.isDrivenByCondWithPolarity.has_value()
											&& !v.isDrivenByCondWithPolarity.value();
								});
				if (usesCond_n) {
					// create Cond_n if required by any bit
					auto IP = GetAfterSlicesInsertPoint(*CurCInsr);
					assert(
							&*IP
									&& "There always should be a terminator at least");
					Instruction *_Cond_n;
					if (match(&*IP, m_Not(m_Specific(CurCInsr)))) {
						_Cond_n = &*IP; // avoid creating of new not if it already exits
					} else {
						Builder.SetInsertPoint(&*IP);
						_Cond_n = dyn_cast<Instruction>(Builder.CreateNot(CurCInsr));
						assert(_Cond_n);
					}
					Cond_n = visitInstruction(_Cond_n).replacements[0];
				}
				c.mergeWithBitsDrivenByCondition(I->getContext(), bitsDrivenByC,
						C_VBC->replacements[0],
						usesCond_n ? &Cond_n : (KnownBitRangeInfo*) nullptr);
				assert(c.consistencyCheck());
			} else {
				c.srcUnionInplace(_cF, I, true);
				assert(c.consistencyCheck());
			}
		} else {
			c.srcUnionInplace(_cF, I, true);
			assert(c.consistencyCheck());
		}
	}
	return c;
}
/*
 * RAII style context manager which sets provided reference to specified value
 * when deallocated.
 * */
template<typename T>
struct SetOnExitAction {
	SetOnExitAction(T &valToSet, T enterVal, T exitVal) :
			valToSet(valToSet), exitVal(exitVal) {
		valToSet = enterVal;
	}
	~SetOnExitAction() {
		valToSet = exitVal;
	}
private:
	T &valToSet;
	T exitVal;
};

VarBitConstraint& ConstBitPartsAnalysisContext::visitPHINode(const PHINode *I) {
	// propagate from ops to this, union of masks an known values
	assert(constraints.find(I) == constraints.end());
	VarBitConstraint &origC = initConstraintMember(I); // Must be initialized to self
	// because there can be cycle in PHI dependencies so if we meet this value when resolving this
	// we will know that it is this PHI.

	if (resolvePhiValues) {
		PHIValueProver valProover(I);
		SetOnExitAction<bool> setBackResolvePhiValues(resolvePhiValues, false,
				true);
		SetVector<const Value*> uniqueOperandValues;
		for (auto *op: I->operand_values()) {
			uniqueOperandValues.insert(op);
		}
		for (auto *op : uniqueOperandValues) {
			const auto &_c = visitValue(op);
			valProover.addOperandConstraint(_c);
		}

		origC = valProover.resolve();
	}
	return origC;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitAsAllInputBitsUsedAllOutputBitsKnown(
		const Value *V) {
	bool tryAnalize = tryAnalyzeOperandsOfUnsupportedInstructions
			&& constraints.find(V) == constraints.end();
	VarBitConstraint &cur = initConstraintMember(V);
	if (tryAnalize) {
		if (auto *I = dyn_cast<Instruction>(V)) {
			for (Value *O : I->operands()) {
				if (O->getType()->isIntegerTy())
					visitValue(O);
				else
					visitAsAllInputBitsUsedAllOutputBitsKnown(O);
			}
		}
	}
	return cur;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitValue(const Value *V) {
	auto C = findInConstraints(V, true);
	if (C) {
		// already seen return prev record reference
		assert(C->consistencyCheck());

		return *C;
	}

	if (auto *CI = dyn_cast<ConstantInt>(V)) {
		return visitConstantInt(CI);
	} else if (auto *I = dyn_cast<Instruction>(V)) {
		if (analysisPredicate.has_value() && !analysisPredicate.value()(*I)) {
			return visitAsAllInputBitsUsedAllOutputBitsKnown(V);
		}
		return visitInstruction(I);
	}

	return visitAsAllInputBitsUsedAllOutputBitsKnown(V);
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitInstruction(
		const Instruction *I) {
	if (auto *SI = dyn_cast<PHINode>(I)) {
		return visitPHINode(SI);
	} else if (auto *SI = dyn_cast<SelectInst>(I)) {
		return visitSelectInst(SI);
	} else if (auto *CMP = dyn_cast<CmpInst>(I)) {
		return visitCmpInst(CMP);
	} else if (auto *C = dyn_cast<CallInst>(I)) {
		return visitCallInst(C);
	} else if (auto *BO = dyn_cast<BinaryOperator>(I)) {
		return visitBinaryOperator(BO);
	} else if (auto *CI = dyn_cast<CastInst>(I)) {
		auto op = CI->getOpcode();
		if (op == Instruction::CastOps::Trunc) {
			// mark C high bits unused in src
			return visitTrunc(CI);
		} else if (op == Instruction::CastOps::ZExt) {
			// mark C high bits to be known 0
			return visitZExt(CI);
		} else if (op == Instruction::CastOps::SExt) {
			// mark C high bits to be known high bit of src
			return visitSExt(CI);
		}
	}
	return visitAsAllInputBitsUsedAllOutputBitsKnown(I);
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitTrunc(const CastInst *I) {
	VarBitConstraint &cur = initConstraintMember(I);

	auto &op = visitValue(I->getOperand(0));
	cur = op.slice(0, I->getType()->getIntegerBitWidth());
	assert(cur.consistencyCheck());
	return cur;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitZExt(const CastInst *I) {
	VarBitConstraint &cur = initConstraintMember(I);

	auto &op = visitValue(I->getOperand(0));
	unsigned origWidth = op.useMask.getBitWidth();
	unsigned resWidth = cur.useMask.getBitWidth();
	if (origWidth != resWidth) {
		KnownBitRangeInfo r(
				ConstantInt::get(I->getContext(),
						APInt(resWidth - origWidth, 0)));
		r.srcBeginBitI = 0;
		r.dstBeginBitI = origWidth;
		cur.replacements.pop_back();
		cur.replacements.insert(cur.replacements.begin(),
				op.replacements.begin(), op.replacements.end());
		cur.replacements.push_back(r);
	}
	assert(cur.consistencyCheck());
	return cur;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitSExt(const CastInst *I) {
	VarBitConstraint &cur = initConstraintMember(I);
	auto &op = visitValue(I->getOperand(0));
	unsigned origWidth = op.useMask.getBitWidth();
	unsigned resWidth = cur.useMask.getBitWidth();
	IRBuilder<> b(I->getContext()); // only for ints
	if (origWidth != resWidth) {
		assert(op.replacements.size());
		cur.replacements.clear();
		cur.replacements.insert(cur.replacements.begin(),
				op.replacements.begin(), op.replacements.end());
		APInt v(resWidth - origWidth, 0);
		KnownBitRangeInfo &msbs = op.replacements.back();
		if (const ConstantInt *msb = dyn_cast<ConstantInt>(msbs.src)) {
			if (msb->isNegative()) {
				v.setAllBits();
			}
			KnownBitRangeInfo r(b.getInt(v));
			r.dstBeginBitI = origWidth;
			r.srcBeginBitI = 0;
			cur.replacements.push_back(r);
		} else {
			for (unsigned i = 0; i < v.getBitWidth(); i++) {
				KnownBitRangeInfo r(msbs.src);
				r.width = 1;
				r.srcBeginBitI = msbs.srcBeginBitI + msbs.width - 1; // orig msb
				r.dstBeginBitI = origWidth + i;
				cur.replacements.push_back(r);
			}
		}
	}
	assert(cur.consistencyCheck());
	return cur;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitCallInst(
		const CallInst *C) {
	if (IsBitConcat(C)) {
		VarBitConstraint &cur = initConstraintMember(C);
		std::vector<KnownBitRangeInfo> newParts; // high first
		for (const auto &O : C->args()) {
			auto &op = visitValue(O);
			assert(op.consistencyCheck());
			for (auto &opop : op.replacements) {
				newParts.push_back(opop);
			}
		}
		cur.replacements.clear();
		// to lowest first
		unsigned dstOff = 0;
		for (auto &i : newParts) {
			i.dstBeginBitI = dstOff;
			cur.replacements.push_back(i);
			dstOff += i.width;
		}
#ifndef NDEBUG
		if (!cur.consistencyCheck()) {
			errs() << *C << "\n" << cur << "\n";
			llvm_unreachable("Concat in incorrect format ");
		}
#endif
		return cur;

	} else if (IsBitRangeGet(C)) {
		VarBitConstraint &cur = initConstraintMember(C);

		std::vector<KnownBitRangeInfo> newParts; // high first
		auto &sh = visitValue(C->getArgOperand(1));
		// if shift offset is resolved to a constant int
		if (sh.replacements.size() == 1
				&& dyn_cast<const ConstantInt>(sh.replacements[0].src)) {
			if (const ConstantInt *shConst = dyn_cast<const ConstantInt>(
					sh.replacements[0].src)) {
				auto &base = visitValue(C->getArgOperand(0));
				auto w = cur.useMask.getBitWidth();
				auto off = shConst->getLimitedValue();
				auto res = base.slice(off, w);
				cur.replacements.clear();
				cur.replacements.insert(cur.replacements.begin(),
						res.replacements.begin(), res.replacements.end());
			}
		}

		assert(cur.consistencyCheck() && "Bit range get in correct format");
		return cur;
	} else {
		return visitAsAllInputBitsUsedAllOutputBitsKnown(C);
	}
}

void ConstBitPartsAnalysisContext::visitBinaryOperatorReduceAnd(
		std::vector<KnownBitRangeInfo> &newParts, const BinaryOperator *parentI,
		unsigned width, unsigned vSrcOffset, unsigned cSrcOffset,
		unsigned dstOffset, const APInt &c, const KnownBitRangeInfo &v) {
	auto &Context = parentI->getContext();
	for (const auto& [bitVal, w] : iter1and0sequences(c, cSrcOffset, width)) {
		if (bitVal) {
			// 1 sequence found
			KnownBitRangeInfo i = v.slice(vSrcOffset, w);
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i, 0,
					i.width);
		} else {
			// 0 sequence found
			KnownBitRangeInfo i = KnownBitRangeInfo(
					ConstantInt::get(Context, APInt(w, 0)));
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i, 0,
					i.width);
		}
		dstOffset += w;
		cSrcOffset += w;
		vSrcOffset += w;
	}
}

void ConstBitPartsAnalysisContext::visitBinaryOperatorReduceOr(
		std::vector<KnownBitRangeInfo> &newParts, const BinaryOperator *parentI,
		unsigned width, unsigned vSrcOffset, unsigned cSrcOffset,
		unsigned dstOffset, const APInt &c, const KnownBitRangeInfo &v) {
	auto &Context = parentI->getContext();
	for (auto seq : iter1and0sequences(c, cSrcOffset, width)) {
		unsigned w = seq.second;
		if (seq.first) {
			// end of 1 sequence found
			KnownBitRangeInfo i = KnownBitRangeInfo(
					ConstantInt::get(Context, APInt::getAllOnes(w)));
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i, 0,
					i.width);
		} else {
			// end of 0 sequence found
			KnownBitRangeInfo i = v.slice(vSrcOffset, w);
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i, 0,
					i.width);
		}

		dstOffset += w;
		cSrcOffset += w;
		vSrcOffset += w;
	}
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitBinaryOperator(
		const BinaryOperator *I) {
	auto opCode = I->getOpcode();
	if (!(opCode == Instruction::BinaryOps::Or
			|| opCode == Instruction::BinaryOps::And
			|| opCode == Instruction::BinaryOps::Xor)) {
		return visitAsAllInputBitsUsedAllOutputBitsKnown(I);
	}
	// else if (op == Instruction::BinaryOps::Shl) {
	//	// if right is constant C mark high C bits unused in src
	//	// and C low bits to be known 0
	//	visitShl(BO);
	//} else if (op == Instruction::BinaryOps::LShr) {
	//	// if right is constant C mark high C bits to be known 0
	//	// and C low bits to be unused 0 in src
	//	visitLShr(BO);
	//} else if (op == Instruction::BinaryOps::AShr) {
	//	// if right is constant C mark high C bits to be knonw to C low bits of src
	//	//
	//	visitAShr(BO);
	//}
	VarBitConstraint &res = initConstraintMember(I);

	auto &lhs = visitValue(I->getOperand(0));
	auto &rhs = visitValue(I->getOperand(1));
	std::vector<KnownBitRangeInfo> newParts;
	unsigned offset = 0;
	for (const auto &item : (RangeSequenceIterator()).uniqueRanges(
			lhs.replacements, rhs.replacements)) {
		assert(item.v0 && item.v1);
		assert(item.width > 0);
		assert(item.begin == offset);

		auto v0asC = dyn_cast<ConstantInt>(item.v0->src);
		auto v1asC = dyn_cast<ConstantInt>(item.v1->src);
		unsigned v0srcOffset = item.v0->srcBeginBitI
				+ (item.begin - item.v0->dstBeginBitI);
		unsigned v1srcOffset = item.v1->srcBeginBitI
				+ (item.begin - item.v1->dstBeginBitI);

		if (offset == 0)
			assert(newParts.size() == 0);
		else
			assert(newParts.back().dstEndBitI() == offset);

		if ((opCode == Instruction::BinaryOps::Or
				|| opCode == Instruction::BinaryOps::And)
				&& (*item.v0 == *item.v1)) {
			// or, and: if segments equal
			// nothing to reduce just add as is
			KnownBitRangeInfo kbri(item.width);
			kbri.src = item.v0->src;
			kbri.srcBeginBitI = v0srcOffset;
			kbri.dstBeginBitI = offset;
			kbri.width = item.width;
			newParts.push_back(kbri);
		} else if (v0asC && v1asC) {
			// if both are constants we just resolve them
			assert(item.begin >= item.v0->dstBeginBitI);
			assert(item.begin >= item.v1->dstBeginBitI);
			auto v0 = v0asC->getValue().extractBits(item.width, v0srcOffset);
			auto v1 = v1asC->getValue().extractBits(item.width, v1srcOffset);
			IRBuilder<> b(const_cast<BinaryOperator*>(I));
			if (opCode == Instruction::BinaryOps::Or) {
				newParts.push_back(KnownBitRangeInfo(b.getInt(v0 | v1)));
			} else if (opCode == Instruction::BinaryOps::And) {
				newParts.push_back(KnownBitRangeInfo(b.getInt(v0 & v1)));
			} else if (opCode == Instruction::BinaryOps::Xor) {
				newParts.push_back(KnownBitRangeInfo(b.getInt(v0 ^ v1)));
			} else {
				assert(false && "Unknown operator, should never get there");
			}
			newParts.back().dstBeginBitI = offset;
		} else if ((v0asC || v1asC)
				&& (opCode == Instruction::BinaryOps::Or
						|| opCode == Instruction::BinaryOps::And)) {

			// at least one is const, we can reduce
			// if other is known reduce set bits
			// commutativity handling
			void (ConstBitPartsAnalysisContext::*reduceFn)(
					std::vector<KnownBitRangeInfo>&, const BinaryOperator*,
					unsigned, unsigned, unsigned, unsigned, const APInt&,
					const KnownBitRangeInfo&) = nullptr;
			unsigned vSrcOffset;
			unsigned cSrcOffset;
			const APInt *c;
			const KnownBitRangeInfo *v;
			if (v0asC) {
				assert(v1srcOffset >= item.v1->srcBeginBitI && "sanity check");
				vSrcOffset = v1srcOffset - item.v1->srcBeginBitI;
				cSrcOffset = v0srcOffset;
				c = &v0asC->getValue();
				v = item.v1;
			} else {
				assert(v0srcOffset >= item.v0->srcBeginBitI && "sanity check");
				vSrcOffset = v0srcOffset - item.v0->srcBeginBitI;
				cSrcOffset = v1srcOffset;
				c = &v1asC->getValue();
				v = item.v0;
			}
			switch (opCode) {
			case Instruction::BinaryOps::Or:
				reduceFn =
						&ConstBitPartsAnalysisContext::visitBinaryOperatorReduceOr;
				break;
			case Instruction::BinaryOps::And:
				reduceFn =
						&ConstBitPartsAnalysisContext::visitBinaryOperatorReduceAnd;
				break;
			default:
				llvm_unreachable("Unknown operator, should never get there");
			}
			(*this.*reduceFn)(newParts, I, item.width, vSrcOffset, cSrcOffset,
					offset, *c, *v);
		} else {
			// nothing to reduce just add this instruction value as is
			KnownBitRangeInfo kbri(item.width);
			kbri.src = I;
			kbri.srcBeginBitI = kbri.dstBeginBitI = offset;
			kbri.width = item.width;
			newParts.push_back(kbri);
		}
		offset += item.width;
	}
	res.replacements = newParts;
	//if (op == Instruction::BinaryOps::Shl) {
	//	// if right is constant C mark high C bits unused in src
	//	// and C low bits to be known 0
	//	visitShl(BO);
	//} else if (op == Instruction::BinaryOps::LShr) {
	//	// if right is constant C mark high C bits to be known 0
	//	// and C low bits to be unused 0 in src
	//	visitLShr(BO);
	//} else if (op == Instruction::BinaryOps::AShr) {
	//	// if right is constant C mark high C bits to be known to C low bits of src
	//	//
	//	visitAShr(BO);
	//}
	return res;
}

std::tuple<const ConstantInt*, APInt, bool, bool> analyzeKnowBitsInfoForCmpInstPart(
		const UniqRangeSequence &item, const KnownBitRangeInfo *v) {
	assert(v == item.v0 || v == item.v1);
	const ConstantInt *_v = dyn_cast<ConstantInt>(v->src);
	bool vIsUMin = false;
	bool vIsUMax = false;

	APInt vAsInt;
	if (_v) {
		assert(item.begin >= v->dstBeginBitI);
		vAsInt = _v->getValue().extractBits(item.width,
				v->srcBeginBitI + (item.begin - v->dstBeginBitI));
		vIsUMin = vAsInt.isZero();
		vIsUMax = vAsInt.isAllOnes();
	}
	return {_v, vAsInt, vIsUMin, vIsUMax};
}

void VarBitConstraint_discardCommonPrefixAndUselessSuffix(VarBitConstraint &res,
		size_t bitOffset, const APInt &v0, const APInt &v1) {
	size_t commonPrefixLen = (v0 ^ v1).countLeadingZeros();
	size_t width = v0.getBitWidth();
	assert(
			commonPrefixLen != width
					&& "Case where both values were equal should have been handled before call of this fn.");
	if (commonPrefixLen) {
		// clear common bits from msb side
		res.clearAllOperandMasks(bitOffset + width - commonPrefixLen,
				bitOffset + width);
	}
	if (commonPrefixLen + 1 < width) {
		// clear bits after first different bit on lsb side
		res.clearAllOperandMasks(bitOffset, bitOffset + commonPrefixLen + 1);
	}
}

bool visitCmpInst_trivialCases(CmpInst::Predicate op,
							   const VarBitConstraint &lhs,
							   const VarBitConstraint &rhs, bool &is0,
							   bool &is1) {

	// const ConstantInt *c0 = lhs.tryGetConstantInt();
	const ConstantInt *c1 = rhs.tryGetConstantInt();

		// cover trivial cases
	switch (op) {
	case CmpInst::Predicate::ICMP_EQ: {
		if (lhs.replacementValuesEqual(rhs)) {
			is1 = true;
		} else if (lhs.replacementValuesKnownNonEqualFast(rhs)) {
			is0 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_NE: {
		if (lhs.replacementValuesEqual(rhs)) {
			is0 = true;
		} else if (lhs.replacementValuesKnownNonEqualFast(rhs)) {
			is1 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_UGT: 	{
		if (c1 && c1->isMaxValue(false)) {
			// x > max -> 0
			is0 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_UGE: {
		if (c1 && c1->isMinValue(false)) {
			// x >= min -> 1
			is1 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_ULT:	{
		if (c1 && c1->isMinValue(false)) {
			// x < min -> 0
			is0 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_ULE: {
		if (c1 && c1->isMaxValue(false)) {
			// x <= max -> 1
			is1 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_SGT:	{
		if (c1 && c1->isMaxValue(true)) {
			// x > max -> 0
			is0 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_SGE: {
		if (c1 && c1->isMinValue(true)) {
			// x >= min -> 1
			is1 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_SLT: {
		if (c1 && c1->isMinValue(true)) {
			// x < min -> 0
			is0 = true;
		}
		break;
	}
	case CmpInst::Predicate::ICMP_SLE: {
		if (c1 && c1->isMaxValue(true)) {
			// x <= max -> 1
			is1 = true;
		}
		break;
	}
	default: {
		// not implemented predicate
		return false;
	}
	}
	return true;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitCmpInst(const CmpInst *I) {
	VarBitConstraint &res = initConstraintMember(I);

	assert(res.replacements.size() == 1 && "Must be 1b value");
	auto &lhs = visitValue(I->getOperand(0));
	auto &rhs = visitValue(I->getOperand(1));

	auto op = I->getPredicate();
	auto w = lhs.useMask.getBitWidth();
	res.addAllSetOperandMask(w);
	res.addAllSetOperandMask(w);
	bool is0 = false; // result of cmp is known to be 0
	bool is1 = false; // result of cmp is known to be 1
	//bool hasKnownUnequalPart = false; // some cons part of operands is known to be unequal
	//// this is used for final resolution  of ugt, ult and alike
	if (!visitCmpInst_trivialCases(op, lhs, rhs, is0, is1)) {
		// not implemented predicate
		assert(res.replacements.size() == 1 && "Must stay 1b value");
		assert(res.consistencyCheck());
		return res;
	}

	// :note: there is a limitation that we can not create new instruction during this analysis phase
	//        this result in inability to resolve that this cmp can be simplified to other predicate
	//        From this reason BitPartsRewriter::rewriteCmpInst implements additional optimization rules
	bool needToCheckBitwise = !(is0 || is1);	
	if (needToCheckBitwise) {
		bool msbsEqual = true; // currently seen bits from msb side are known to equal
		unsigned lastBitEnd = w; // bit position in operands
	
		// check if it is possible to immediately evaluate based on known const bits
		auto sequences = RangeSequenceIterator().uniqueRanges(lhs.replacements,
				rhs.replacements);
		for (auto _item = sequences.rbegin(); _item != sequences.rend(); ++_item) {
			// :note: iterating msb->lsb
			const auto &item = *_item;
			assert(item.v0 && item.v1);
			assert(item.width);
			assert(lastBitEnd >= item.width);
			const ConstantInt *_v0;
			const ConstantInt *_v1;
			bool v0IsUMin;
			bool v0IsUMax;
			bool v1IsUMin;
			bool v1IsUMax;
			APInt v0;
			APInt v1;
			std::tie(_v0, v0, v0IsUMin, v0IsUMax) =
					analyzeKnowBitsInfoForCmpInstPart(item, item.v0);
			std::tie(_v1, v1, v1IsUMin, v1IsUMax) =
					analyzeKnowBitsInfoForCmpInstPart(item, item.v1);
			bool bothOpPartsConst = _v0 && _v1;
			bool eq = item.v0 == item.v1 || (bothOpPartsConst && v0 == v1);
			// :note: 
			//   for x UGE 0 the term can be removed only if it is not followed by 
			//   other non cost compares because if top bits are equal
			//   we need to check successor bits, but if not we know the result
			//   For example {x, y} UGE {0, z} (MSB...LSB) we can not discard
			//   x UGE 0 part because  ({1, 0} UGE {0, 2}) == 1 but 0 UGE 2 == 0
			//   (and x UGE 0 alone is always satisfied)
			bool isNotMsbOrAllIsConst = msbsEqual && _item == (sequences.rend()-1);
			
			bool doesAffectResult = true;
			switch (op) {
			case CmpInst::Predicate::ICMP_EQ: {
				// for == we can evaluate to false if some constant bits not-equal
				// otherwise we cut of constant bits
				if (eq) {
					doesAffectResult = false;
				} else if (bothOpPartsConst) {
					is0 = true;
				}
				break;
			}
			case CmpInst::Predicate::ICMP_NE: {
				// for != we can evaluate to true if some constant bits not-equal
				// otherwise we cut of constant bits
				if (eq) {
					doesAffectResult = false;
				} else if (bothOpPartsConst) {
					is1 = true;
				}
				break;
			}
	
				// for unsigned <, <=, >, >= if the prefix is constant we may be able to evaluate expr
				// otherwise we can drop all constant and equal bits
			case CmpInst::Predicate::ICMP_UGT:
			case CmpInst::Predicate::ICMP_UGE:
				if (eq) {
					doesAffectResult = false;
				} else if (bothOpPartsConst) {
					if (msbsEqual && !v0.ugt(v1)) {
						is0 = true;
					} else {
						VarBitConstraint_discardCommonPrefixAndUselessSuffix(res,
								item.begin, v0, v1);
					}
				} else if (op == CmpInst::Predicate::ICMP_UGE) {
					if (isNotMsbOrAllIsConst && (v0IsUMax || v1IsUMin)) {
						// max >= o1 -> 1 (if prefix msb equal)
						// o0 >= min -> 1 (if prefix msb equal)
						doesAffectResult = false;
					}
				}
				break;
			case CmpInst::Predicate::ICMP_ULT:
			case CmpInst::Predicate::ICMP_ULE:
				if (eq) {
					doesAffectResult = false;
				} else if (bothOpPartsConst) {
					if (msbsEqual && !v0.ult(v1)) {
						is0 = true;
					} else {
						VarBitConstraint_discardCommonPrefixAndUselessSuffix(res,
								item.begin, v0, v1);
					}
				} else if (op == CmpInst::Predicate::ICMP_ULE) {
					if (isNotMsbOrAllIsConst && (v0IsUMin || v1IsUMax)) {
						// min <= o1 -> 1 (if prefix msb equal)
						// o0 <= max -> 1 (if prefix msb equal)
						doesAffectResult = false;
					}
				}
				break;
	
				// for signed <, <=, >, >= same as for unsigned but we must not remove sign bit
				// even if it is constant when reducing
			case CmpInst::Predicate::ICMP_SGT:
			case CmpInst::Predicate::ICMP_SGE:
				// 	if (v0.sgt(v1)) {
				// 		is1 = true;
				// 	} else if (eq && op == CmpInst::Predicate::ICMP_SGE) {
				// 		doesAffectResult = false;
				// 	} else {
				// 		is0 = true;
				// 	}
			case CmpInst::Predicate::ICMP_SLT:
			case CmpInst::Predicate::ICMP_SLE:
				//		if (v0.slt(v1)) {
				//			is1 = true;
				//		} else if (eq && op == CmpInst::Predicate::ICMP_SLE) {
				//			doesAffectResult = false;
				//		} else {
				//			is0 = true;
				//		}
	
				//{
				//	// o0 < min -> 0
				//	// max < o1 -> 0
				//	if (v1IsMin || v0IsMax) {
				//		if (msbsEqual) {
				//			is0 = true;
				//		} else {
				//			doesAffectResult = false;
				//		}
				//	}
				//	break;
				//}
				break;
	
			default:
				assert(false && "Unknown compare operator value");
			}
	
			if (doesAffectResult) {
				// we just found something different, for same values there would be doesAffectResult==true
				msbsEqual = false;
			} else {
				// (clear because operands are constants and do not affect result)
				res.clearAllOperandMasks(lastBitEnd - item.width, lastBitEnd);
			}
			lastBitEnd -= item.width;
	
			// if this are top bits and they do not equal we can resolve output value
			if (is0 || is1) {
				break;
			}
		}
		assert(res.replacements.size() == 1 && "Must stay 1b value");
		if (msbsEqual) {
			// whole value is equal
			switch (op) {
			case CmpInst::Predicate::ICMP_EQ:
			case CmpInst::Predicate::ICMP_UGE:
			case CmpInst::Predicate::ICMP_SGE:
			case CmpInst::Predicate::ICMP_ULE:
			case CmpInst::Predicate::ICMP_SLE:
				assert(!is0);
				is1 = true;  // every part equals so result is 1
				break;
	
			case CmpInst::Predicate::ICMP_NE:
			case CmpInst::Predicate::ICMP_UGT:
			case CmpInst::Predicate::ICMP_SGT:
			case CmpInst::Predicate::ICMP_ULT:
			case CmpInst::Predicate::ICMP_SLT:
				assert(!is1);
				is0 = true; // every part equals so result is 0
				break;
	
			default:
				assert(false && "Unknown compare operator value");
			}
		}
	}
	if (is0 || is1) {
		res.clearAllOperandMasks();

		IRBuilder<> builder(I->getContext());
		if (is0) {
			assert(!is1);
			res.replacements.pop_back(); // pop self
			res.replacements.push_back(KnownBitRangeInfo(builder.getInt1(0)));
		} else if (is1) {
			res.replacements.pop_back(); // pop self
			res.replacements.push_back(KnownBitRangeInfo(builder.getInt1(1)));
		}
	}
	assert(res.replacements.size() == 1 && "Must stay 1b value");
	assert(res.consistencyCheck());
	return res;
}

bool ConstBitPartsAnalysisContext::updateInstruction(const Instruction *I) {
	if (!resolvePhiValues && isa<PHINode>(I))
		return false;
	std::unique_ptr<VarBitConstraint> prev = std::move(constraints[I]);
	constraints.erase(I);
	auto &cur = visitInstruction(I);
	assert(constraints[I].get() == &cur);
	return prev->replacements != cur.replacements;
}

std::unique_ptr<ConstBitPartsAnalysisContext> ConstBitPartsAnalysisContext::createChild() {
	auto res = std::make_unique<ConstBitPartsAnalysisContext>(this,
			this->analysisPredicate);
	if (resolvePhiValues)
		res->setShouldResolvePhiValues();
	res->tryAnalyzeOperandsOfUnsupportedInstructions =
			tryAnalyzeOperandsOfUnsupportedInstructions;
	return res;
}

}
