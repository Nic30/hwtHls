#include "constBitPartsAnalysis.h"
#include <llvm/IR/IRBuilder.h>
#include "targets/intrinsic/bitrange.h"

using namespace llvm;

namespace hwtHls {

ConstBitPartsAnalysisContext::ConstBitPartsAnalysisContext() {
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitConstantInt(
		const ConstantInt *CI) {
	constraints[CI] = std::make_unique<VarBitConstraint>(CI);
	return *constraints[CI].get();
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitSelectInst(
		const SelectInst *I) {
	// propagate from ops to this, union of masks an known values
	constraints[I] = std::make_unique<VarBitConstraint>(
			I->getType()->getIntegerBitWidth());
	VarBitConstraint &c = *constraints[I];
	bool first = true;
	for (auto op : { I->getTrueValue(), I->getFalseValue() }) {
		auto &_c = visitValue(op);
		if (first) {
			first = false;
			c = _c; // intended copy of _c to c
		} else {
			assert(_c.consystencyCheck());
			c.srcUnionInplace(_c, I);
			assert(c.consystencyCheck());
		}
	}
	return c;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitPHINode(const PHINode *I) {
	// propagate from ops to this, union of masks an known values
	assert(constraints.find(I) == constraints.end());
	constraints[I] = std::make_unique<VarBitConstraint>(I); // Must be initialized to self
	// because there can be cycle in PHI dependencies so if we meet this value when resolving this
	// we will know that it is this PHI.
	VarBitConstraint &c = *constraints[I];
	bool first = true;
	for (auto op : I->operand_values()) {
		auto &_c = visitValue(op);
		if (first) {
			first = false;
			assert(_c.consystencyCheck());
			c = _c; // intended copy of _c to c

		} else {
			assert(c.consystencyCheck());
			c.srcUnionInplace(_c, I);
			assert(c.consystencyCheck());
		}
	}
	return c;
}
VarBitConstraint& ConstBitPartsAnalysisContext::visitAsAllInputBitsUsedAllOutputBitsKnown(
		const Value *V) {
	// this function is called for every element which we do can not dissolve
	auto &cur = constraints[V] = std::make_unique<VarBitConstraint>(V);
	if (auto *I = dyn_cast<Instruction>(V)) {
		for (Value *O : I->operands()) {
			if (O->getType()->isIntegerTy())
				visitValue(O);
			else
				visitAsAllInputBitsUsedAllOutputBitsKnown(O);
		}
	}

	return *cur.get();
}
VarBitConstraint& ConstBitPartsAnalysisContext::visitValue(const Value *V) {
	auto cur = constraints.find(V);
	if (cur != constraints.end()) {
		// already seen return prev record reference
		return *cur->second.get();
	}

	if (auto *CI = dyn_cast<ConstantInt>(V)) {
		return visitConstantInt(CI);
	} else if (auto *I = dyn_cast<Instruction>(V)) {
		return visitInstruction(I);
	} else {
		return visitAsAllInputBitsUsedAllOutputBitsKnown(V);
	}
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
	constraints[I] = std::make_unique<VarBitConstraint>(I);
	VarBitConstraint &cur = *constraints[I];
	auto &op = visitValue(I->getOperand(0));
	IRBuilder<> Builder(const_cast<CastInst*>(I));
	cur = op.slice(&Builder, 0, I->getType()->getIntegerBitWidth());
	assert(cur.consystencyCheck());
	return cur;
}
VarBitConstraint& ConstBitPartsAnalysisContext::visitZExt(const CastInst *I) {
	constraints[I] = std::make_unique<VarBitConstraint>(I);
	VarBitConstraint &cur = *constraints[I];
	auto &op = visitValue(I->getOperand(0));
	unsigned origWidth = op.useMask.getBitWidth();
	unsigned resWidth = cur.useMask.getBitWidth();
	IRBuilder<> b(I->getContext()); // only for ints
	if (origWidth != resWidth) {
		KnownBitRangeInfo r(b.getInt(APInt(resWidth - origWidth, 0)));
		r.srcBeginBitI = 0;
		r.dstBeginBitI = origWidth;
		cur.replacements.pop_back();
		cur.replacements.insert(cur.replacements.begin(),
				op.replacements.begin(), op.replacements.end());
		cur.replacements.push_back(r);
	}
	assert(cur.consystencyCheck());
	return cur;
}
VarBitConstraint& ConstBitPartsAnalysisContext::visitSExt(const CastInst *I) {
	constraints[I] = std::make_unique<VarBitConstraint>(I);
	VarBitConstraint &cur = *constraints[I];
	auto &op = visitValue(I->getOperand(0));
	unsigned origWidth = op.useMask.getBitWidth();
	unsigned resWidth = cur.useMask.getBitWidth();
	IRBuilder<> b(I->getContext()); // only for ints
	if (origWidth != resWidth) {
		assert(op.replacements.size());

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
				r.srcWidth = 1;
				r.srcBeginBitI = msbs.srcBeginBitI + msbs.srcWidth - 1; // orig msb
				r.dstBeginBitI = origWidth + i;
				cur.replacements.push_back(r);
			}
		}
	}

	assert(cur.consystencyCheck());
	return cur;
}

VarBitConstraint& ConstBitPartsAnalysisContext::visitCallInst(
		const CallInst *C) {
	if (IsBitConcat(C)) {
		constraints[C] = std::make_unique<VarBitConstraint>(C);
		VarBitConstraint &cur = *constraints[C];
		std::vector<KnownBitRangeInfo> newParts; // high first
		for (const auto &O : C->args()) {
			auto &op = visitValue(O);
			assert(op.consystencyCheck());
			for (auto opop = op.replacements.rbegin();
					opop != op.replacements.rend(); ++opop) {
				newParts.push_back(*opop);
			}
		}
		cur.replacements.clear();
		unsigned dstOff = 0;
		for (auto opop = newParts.rbegin(); opop != newParts.rend(); ++opop) {
			KnownBitRangeInfo i = *opop;
			i.dstBeginBitI = dstOff;
			cur.replacements.push_back(i); // to lowest first
			dstOff += i.srcWidth;
		}

		assert(cur.consystencyCheck() && "Concat in correct format");
		return cur;
	} else if (IsBitRangeGet(C)) {
		constraints[C] = std::make_unique<VarBitConstraint>(C);
		VarBitConstraint &cur = *constraints[C];
		std::vector<KnownBitRangeInfo> newParts; // high first
		auto &base = visitValue(C->getArgOperand(0));
		auto &sh = visitValue(C->getArgOperand(1));
		if (sh.replacements.size() == 1
				&& dyn_cast<const ConstantInt>(sh.replacements[0].src)) {
			if (const ConstantInt *shConst = dyn_cast<const ConstantInt>(
					sh.replacements[0].src)) {
				auto w = cur.useMask.getBitWidth();
				auto off = shConst->getLimitedValue();
				IRBuilder<> B(const_cast<CallInst*>(C));
				auto res = base.slice(&B, off, w);
				cur.replacements.clear();
				cur.replacements.insert(cur.replacements.begin(),
						res.replacements.begin(), res.replacements.end());
			}
		}

		assert(cur.consystencyCheck() && "Bit range get in correct format");
		return cur;
	} else {
		return visitAsAllInputBitsUsedAllOutputBitsKnown(C);
	}
}
void ConstBitPartsAnalysisContext::visitBinaryOperatorReduceAnd(
		std::vector<KnownBitRangeInfo> &newParts, const BinaryOperator *parentI,
		unsigned width, unsigned dstOffset, const APInt &c,
		const KnownBitRangeInfo &v) {
	// if the bit in c is 0 the output bit should be also 0 else it is bit from v
	IRBuilder<> b(const_cast<BinaryOperator*>(parentI));
	int l_1 = -1; // start of 1 sequence, -1 as invalid value
	int l_0 = -1; // start of 0 sequence, -1 as invalid value
	for (unsigned h = 0; h < c.getBitWidth(); ++h) {
		if (l_1 == -1 && c[h]) {
			l_1 = h; // start of 1 sequence
		} else if (l_0 == -1 && !c[h]) {
			l_0 = h; // start of 0 sequence
		}

		if (l_1 != -1 && (h == c.getBitWidth() - 1 || !c[h + 1])) {
			// end of 1 sequence found
			unsigned w = h - l_1 + 1;
			KnownBitRangeInfo i = v.slice(&b, static_cast<unsigned>(l_1), w);
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i);
			dstOffset += w;
			l_1 = -1; // reset start;
		} else if (l_0 != -1 && (h == c.getBitWidth() - 1 || c[h + 1])) {
			// end of 0 sequence found
			unsigned w = h - l_0 + 1;
			KnownBitRangeInfo i = KnownBitRangeInfo(b.getInt(APInt(w, 0)));
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i);
			dstOffset += w;
			l_0 = -1; // reset start;
		}
	}
}
void ConstBitPartsAnalysisContext::visitBinaryOperatorReduceOr(
		std::vector<KnownBitRangeInfo> &newParts, const BinaryOperator *parentI,
		unsigned width, unsigned dstOffset, const APInt &c,
		const KnownBitRangeInfo &v) {
	// if the bit in c is 0 the output bit should be also 0 else it is bit from v
	IRBuilder<> b(const_cast<BinaryOperator*>(parentI));
	int l_1 = -1; // start of 1 sequence, -1 as invalid value
	int l_0 = -1; // start of 0 sequence, -1 as invalid value
	for (unsigned h = 0; h < c.getBitWidth(); ++h) {
		if (l_1 == -1 && c[h]) {
			l_1 = h; // start of 1 sequence
		} else if (l_0 == -1 && !c[h]) {
			l_0 = h; // start of 0 sequence
		}

		if (l_1 != -1 && (h == c.getBitWidth() - 1 || !c[h + 1])) {
			// end of 1 sequence found
			unsigned w = h - l_1 + 1;
			KnownBitRangeInfo i = KnownBitRangeInfo(
					b.getInt(APInt::getAllOnesValue(w)));
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i);
			dstOffset += w;
			l_1 = -1; // reset start;
		} else if (l_0 != -1 && (h == c.getBitWidth() - 1 || c[h + 1])) {
			// end of 0 sequence found
			unsigned w = h - l_0 + 1;
			KnownBitRangeInfo i = v.slice(&b, static_cast<unsigned>(l_0), w);
			i.dstBeginBitI = dstOffset;
			VarBitConstraint::srcUnionPushBackWithMerge(newParts, i);
			dstOffset += w;
			l_0 = -1; // reset start;
		}
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
	constraints[I] = std::make_unique<VarBitConstraint>(I);
	VarBitConstraint &res = *constraints[I];
	auto &lhs = visitValue(I->getOperand(0));
	auto &rhs = visitValue(I->getOperand(1));
	std::vector<KnownBitRangeInfo> newParts;
	unsigned offset = 0;
	for (const auto &item : (RangeSequenceIterator()).uniqueRanges(
			lhs.replacements, rhs.replacements)) {
		assert(item.v0 && item.v1);
		assert(item.width);

		auto _v0 = dyn_cast<ConstantInt>(item.v0->src);
		auto _v1 = dyn_cast<ConstantInt>(item.v1->src);

		if ((opCode == Instruction::BinaryOps::Or
				|| opCode == Instruction::BinaryOps::And)
				&& ((_v0 && _v1 && _v0 == _v1) || *item.v0 == *item.v1)) {
			// or, and: if segments equal
			newParts.push_back(*item.v0);
		} else if (_v0 && _v1) {
			// if both are constants we just resolve them
			assert(item.begin >= item.v0->dstBeginBitI);
			assert(item.begin >= item.v1->dstBeginBitI);
			auto v0 = _v0->getValue().extractBits(item.width,
					item.v0->srcBeginBitI
							+ (item.begin - item.v0->dstBeginBitI));
			auto v1 = _v1->getValue().extractBits(item.width,
					item.v1->srcBeginBitI
							+ (item.begin - item.v1->dstBeginBitI));
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
		} else if ((_v0 || _v1)
				&& (opCode == Instruction::BinaryOps::Or
						|| opCode == Instruction::BinaryOps::And)) {
			// at least one is const, we can reduce
			if (opCode == Instruction::BinaryOps::Or) {
				// if other is known reduce set bits
				if (_v0) {
					visitBinaryOperatorReduceOr(newParts, I, item.width, offset,
							_v0->getValue(), *item.v1);
				} else {
					visitBinaryOperatorReduceOr(newParts, I, item.width, offset,
							_v1->getValue(), *item.v0);
				}
			} else if (opCode == Instruction::BinaryOps::And) {
				// if other is known reduce cleared bits
				if (_v0) {
					visitBinaryOperatorReduceAnd(newParts, I, item.width,
							offset, _v0->getValue(), *item.v1);
				} else {
					visitBinaryOperatorReduceAnd(newParts, I, item.width,
							offset, _v1->getValue(), *item.v0);
				}
			} else {
				assert(false && "Unknown operator, should never get there");
			}
		} else {
			// nothing to reduce just add as is
			KnownBitRangeInfo kbri(item.width);
			kbri.src = I;
			kbri.srcBeginBitI = kbri.dstBeginBitI = offset;
			kbri.srcWidth = item.width;
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
	//	// if right is constant C mark high C bits to be knonw to C low bits of src
	//	//
	//	visitAShr(BO);
	//}
	return res;
}
VarBitConstraint& ConstBitPartsAnalysisContext::visitCmpInst(const CmpInst *I) {
	constraints[I] = std::make_unique<VarBitConstraint>(I);
	VarBitConstraint &res = *constraints[I];
	assert(res.replacements.size() == 1 && "Must be 1b value");
	auto &lhs = visitValue(I->getOperand(0));
	auto &rhs = visitValue(I->getOperand(1));

	// for == we can evaluate to false if some constant bits not-equal otherwise we cut of constant bits
	// for != we can evaluate to true if some constant bits not-equal otherwise we cut of constant bits

	// for unsigned <, <=, >, >= if the prefix is constant we may be able to evaluate expr otherwise we can drop all constant and equal bits
	//CmpInst::Predicate::ICMP_UGT
	//CmpInst::Predicate::ICMP_UGE
	//CmpInst::Predicate::ICMP_ULT
	//CmpInst::Predicate::ICMP_ULE

	// for signed <, <=, >, >= same as for unsigned but we must not remove sign bit even if it is constant when reducing
	//CmpInst::Predicate::ICMP_SGT
	//CmpInst::Predicate::ICMP_SGE
	//CmpInst::Predicate::ICMP_SLT
	//CmpInst::Predicate::ICMP_SLE

	auto op = I->getPredicate();
	auto w = lhs.useMask.getBitWidth();
	res.addAllSetOperandMask(w);
	res.addAllSetOperandMask(w);
	bool is0 = false;
	bool is1 = false;
	unsigned offset = 0;
	// [todo] if sign_val > -1 -> ~sign_val[MSB]
	// [todo] if sign_val >= 0 -> ~sign_val[MSB]
	// [todo] if sign_val < 0 -> sign_val[MSB]

	// check if it is possible to immediately evaluate based on known const bits
	for (const auto &item : (RangeSequenceIterator()).uniqueRanges(
			lhs.replacements, rhs.replacements)) {
		assert(item.v0 && item.v1);
		assert(item.width);
		auto _v0 = dyn_cast<ConstantInt>(item.v0->src);
		auto _v1 = dyn_cast<ConstantInt>(item.v1->src);
		if (_v0 && _v1) {
			assert(item.begin >= item.v0->dstBeginBitI);
			assert(item.begin >= item.v1->dstBeginBitI);
			auto v0 = _v0->getValue().extractBits(item.width,
					item.v0->srcBeginBitI
							+ (item.begin - item.v0->dstBeginBitI));
			auto v1 = _v1->getValue().extractBits(item.width,
					item.v1->srcBeginBitI
							+ (item.begin - item.v1->dstBeginBitI));
			if (op == CmpInst::Predicate::ICMP_EQ) {
				if (v0 != v1) {
					is0 = true;
				} else {
					res.clearAllOperandMasks(offset, offset + item.width);
				}
			} else if (op == CmpInst::Predicate::ICMP_NE) {
				if (v0 != v1) {
					is1 = true;
				} else {
					res.clearAllOperandMasks(offset, offset + item.width);
				}
			} else {
				// signed/unsigned  <, <=, >, >=
				// if this are top bits and they do not equal we can resolve output value
				if (item.begin + item.width
						== I->getType()->getIntegerBitWidth()) {
					if (v0 == v1) {
						res.clearAllOperandMasks(offset, offset + item.width);
					} else {
						switch (op) {
						case CmpInst::Predicate::ICMP_UGE:
						case CmpInst::Predicate::ICMP_UGT:
							if (v0.ugt(v1)) {
								is1 = true;
							} else {
								is0 = true;
							}
							break;
						case CmpInst::Predicate::ICMP_SGE:
						case CmpInst::Predicate::ICMP_SGT:
							if (v0.sgt(v1)) {
								is1 = true;
							} else {
								is0 = true;
							}
							break;

						case CmpInst::Predicate::ICMP_ULT:
						case CmpInst::Predicate::ICMP_ULE:
							if (v0.ult(v1)) {
								is1 = true;
							} else {
								is0 = true;
							}
							break;
						case CmpInst::Predicate::ICMP_SLT:
						case CmpInst::Predicate::ICMP_SLE:
							if (v0.slt(v1)) {
								is1 = true;
							} else {
								is0 = true;
							}
							break;
						default:
							assert(false && "Unknown compare operator value");
						}
						break;
					}
				}
			}
			if (is0 || is1) {
				for (auto &m : res.operandUseMask)
					m.clearAllBits();
				break;
			}
		}
		offset += item.width;
	}
	assert(res.replacements.size() == 1 && "Must stay 1b value");
	IRBuilder<> builder(I->getContext());
	if (is0) {
		assert(!is1);
		res.replacements.pop_back();
		res.replacements.push_back(KnownBitRangeInfo(builder.getInt1(0)));
	} else if (is1) {
		res.replacements.pop_back();
		res.replacements.push_back(KnownBitRangeInfo(builder.getInt1(1)));
	}

	assert(res.consystencyCheck());
	return res;
}

bool ConstBitPartsAnalysisContext::updateInstruction(const Instruction *I) {
	std::unique_ptr<VarBitConstraint> prev = std::move(constraints[I]);
	constraints.erase(I);
	auto &cur = visitInstruction(I);
	return prev->replacements != cur.replacements;
}

}
