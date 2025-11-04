#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>

#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/AssumptionCache.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/intrinsic/metadataWithBitrange.h>

using namespace llvm;
using namespace llvm::PatternMatch;

//#define DEBUG_TRACE_isImpliedCondition

namespace hwtHls {

//size_t getNumOfPrefixZerosInWriteEntryBlockPhiIncommingValues(
//		const PHINode &PHI, BasicBlock *writeSectionEntryBB) {
//	if (PHI.getParent() != writeSectionEntryBB)
//		return 0;
//	size_t cnt = 0;
//	for (Value *V : PHI.incoming_values()) {
//		if (auto VC = dyn_cast<ConstantInt>(V)) {
//			if (VC->getZExtValue()) {
//				break;
//			}
//		} else {
//			break;
//		}
//		cnt++;
//	}
//	return cnt;
//}

//// :attention: this is dangerous, see other attentions notes in function body
//// :returns: true if LHS implies RHS, false if not implied or unknown
//bool isImpliedConditionWithPHISupport(const Value *LHS, const Value *RHS,
//		const DataLayout &DL, BasicBlock *writeSectionEntryBB) {
//	auto impl = isImpliedCondition(LHS, RHS, DL);
//	if (impl.has_value())
//		return impl.value();
//
//	// if this is a phi from same block check all cases separately
//	// else probe all incoming value combinations
//	if (const PHINode *LHSPhi = dyn_cast<PHINode>(LHS)) {
//		if (const PHINode *RHSPhi = dyn_cast<PHINode>(RHS)) {
//			if (LHSPhi->getParent() == RHSPhi->getParent()) {
//				// :attention: this expects predecessors to be ordered the most dominating first
//				auto lZeros =
//						getNumOfPrefixZerosInWriteEntryBlockPhiIncommingValues(
//								*LHSPhi, writeSectionEntryBB);
//				auto rZeros =
//						getNumOfPrefixZerosInWriteEntryBlockPhiIncommingValues(
//								*RHSPhi, writeSectionEntryBB);
//				if (lZeros > rZeros)
//					return true; // the lhs may be 1 only after rhs have become 1
//				// phis of the same block
//				for (auto &BB : LHSPhi->blocks()) {
//					auto LHSV = LHSPhi->getIncomingValueForBlock(BB);
//					auto RHSV = RHSPhi->getIncomingValueForBlock(BB);
//					if (!isImpliedConditionWithPHISupport(LHSV, RHSV, DL,
//							writeSectionEntryBB)) {
//						return false;
//					}
//				}
//			} else {
//				// phis of a different block, cross-product of all possible values
//				for (auto &LHSV : LHSPhi->incoming_values()) {
//					for (auto &RHSV : RHSPhi->incoming_values()) {
//						if (!isImpliedConditionWithPHISupport(LHSV, RHSV, DL,
//								writeSectionEntryBB)) {
//							return false;
//						}
//					}
//				}
//				return true;
//			}
//		} else {
//			// right is not a phi
//			if (getNumOfPrefixZerosInWriteEntryBlockPhiIncommingValues(*LHSPhi,
//					writeSectionEntryBB) == 1)
//				return true;
//			auto RHSV = RHS;
//			for (auto &LHSV : LHSPhi->incoming_values()) {
//				if (!isImpliedConditionWithPHISupport(LHSV, RHSV, DL,
//						writeSectionEntryBB)) {
//					return false;
//				}
//			}
//		}
//		return true;
//	} else if (const PHINode *RHSPhi = dyn_cast<PHINode>(RHS)) {
//		// left is not a phi
//		auto LHSV = LHS;
//		for (auto &RHSV : RHSPhi->incoming_values()) {
//			if (!isImpliedConditionWithPHISupport(LHSV, RHSV, DL,
//					writeSectionEntryBB)) {
//				return false;
//			}
//		}
//		return true;
//	} else if (auto LHSC = dyn_cast<ConstantInt>(LHS)) {
//		if (LHSC->getZExtValue()) {
//			return false; // 1 => x
//		} else {
//			return true; // 0 => x
//		}
//	} else {
//		return false;
//	}
//}

void collectAndTerms(Value &V, SmallPtrSet<Value*, 16> &andTerms) {
	if (andTerms.contains(&V))
		return; // no need to discover again
	Value *V0, *V1;
	if (match(&V, m_LogicalAnd(m_Value(V0), m_Value(V1)))) {
		// recursively collect all members of AND tree
		collectAndTerms(*V0, andTerms);
		collectAndTerms(*V1, andTerms);
	} else {
		andTerms.insert(&V);
	}
}

void collectOrTerms(Value &V, SmallPtrSet<Value*, 16> &orTerms) {
	if (orTerms.contains(&V))
		return; // no need to discover again
	Value *V0, *V1;
	if (match(&V, m_LogicalOr(m_Value(V0), m_Value(V1)))) {
		// recursively collect all members of AND tree
		collectOrTerms(*V0, orTerms);
		collectOrTerms(*V1, orTerms);
	} else {
		orTerms.insert(&V);
	}
}

std::optional<bool> isImpliedConditionByAssume(const Value *LHS,
		const Value *RHS, AssumptionCache &AC, const DominatorTree *DT,
		const Instruction *CtxI) {
	assert(LHS->getType()->getIntegerBitWidth() == 1);
	assert(RHS->getType()->getIntegerBitWidth() == 1);
	if (LHS == RHS)
		return true;
	const OffsetWidthValue RHS_slice = OffsetWidthValue::fromValue(
			const_cast<Value*>(RHS));

	if (!RHS_slice.isIdentity()) {
		const OffsetWidthValue LHS_slice = OffsetWidthValue::fromValue(
				const_cast<Value*>(RHS));
		auto baseBitVector = dyn_cast<Instruction>(LHS_slice.value);
		if (baseBitVector && LHS_slice.value == RHS_slice.value && LHS_slice.offset > RHS_slice.offset) {
			assert(LHS_slice.width == 1);
			assert(RHS_slice.width == 1);
			assert(!LHS_slice.isIdentity());
			auto maskMdId = LHS->getContext().getMDKindID(HwtHlsInstCombinePass::metadataName_expr_maskContinuosFromLsb);
			// bit closer to MSB implies all bits closer to LSB are set
			size_t l = RHS_slice.offset;
			size_t h = LHS_slice.offset + 1;
			if (MetadataBitRanges::isSelected(*baseBitVector, maskMdId, {l, h}))
				return true;

		}

	}

	// Try to restrict the range based on information from assumptions.
	for (auto &AssumeVH : AC.assumptionsFor(LHS)) {
		if (!AssumeVH)
			continue;
		CallInst *I = cast<CallInst>(AssumeVH);
		assert(
				I->getParent()->getParent() == CtxI->getParent()->getParent()
						&& "Got assumption for the wrong function!");
		assert(
				I->getCalledFunction()->getIntrinsicID() == Intrinsic::assume
						&& "must be an assume intrinsic");

		if (!isValidAssumeForContext(I, CtxI, DT))
			continue;

		Value *Arg = I->getArgOperand(0);
		/*
		 * L R  <= (L ==> R)
		 * 0 0  1
		 * 0 1  1
		 * 1 0  0
		 * 1 1  1
		 * */
		using Predicate = ICmpInst::Predicate;
		CmpPredicate Pred;
		// :note: llvm::findAffectedValues does not update cache for ULE
		if (match(Arg, m_ICmp(Pred, m_Specific(LHS), m_Specific(RHS)))
				&& Pred == Predicate::ICMP_ULE) {
			// check for implication in for of a ULE b
			return true; // implied true
		} else if (match(Arg, m_c_Or(m_Specific(LHS), m_Specific(RHS)))) {
			// :attention: llvm-18 AssumptionCache findAffectedValues caches only "not" and CmpInst
			//             llvm-19+  findAffectedValues uses findValuesAffectedByCondition which handles this case
			// ~L ==> R == L | R
			return false;
		} else if (match(Arg,
				m_c_Or(m_Not(m_Specific(LHS)), m_Specific(RHS)))) {
			// :attention: llvm-19+
			// L ==> R in ~L|R form
			return true;
		}
		if (!RHS_slice.isIdentity()) {
			// check for LHS ==> more bits from RHS src bitvector at once
			// implemented as LHS ==> RHS.src[n:m] == C
			CmpPredicate Pred2;
			ConstantInt *CI;
			Value *RHS_src;
			if (match(Arg,
					m_ICmp(Pred, m_Specific(LHS),
							m_ICmp(Pred2, m_Value(RHS_src), m_ConstantInt(CI))))
					&& Pred == Predicate::ICMP_ULE
					&& Pred == Predicate::ICMP_EQ) {
				// matched LHS ==> RHS_src == CI
				if (RHS_src == RHS_slice.value) {
					// case without any slice in RHS
					return CI->getValue().extractBits(1, RHS_slice.offset).getZExtValue();
				} else if (auto *RHS_src_Call = dyn_cast<CallInst>(RHS_src)) {
					const OffsetWidthValue RHS_slice2 =
							OffsetWidthValue::fromValue(
									const_cast<CallInst*>(RHS_src_Call));
					if (RHS_slice2.value == RHS_slice.value) {
						// check if the bit addressed by RHS is also in RHS_src_Call
						if (RHS_slice2.contains(RHS_slice)) {
							assert(RHS_slice2.offset >= RHS_slice.offset);
							return CI->getValue().extractBits(1,
									RHS_slice2.offset - RHS_slice.offset).getZExtValue();
						}
					}
				}
			}
		}
	}
	Value *LHS_n;
	if (match(LHS, m_Not(m_Value(LHS_n)))) {
		for (auto &AssumeVH : concat<llvm::AssumptionCache::ResultElem>(AC.assumptionsFor(LHS_n), AC.assumptionsFor(RHS))) {
			if (!AssumeVH)
				continue;
			CallInst *I = cast<CallInst>(AssumeVH);
			assert(
					I->getParent()->getParent()
							== CtxI->getParent()->getParent()
							&& "Got assumption for the wrong function!");
			assert(
					I->getCalledFunction()->getIntrinsicID()
							== Intrinsic::assume
							&& "must be an assume intrinsic");

			if (!isValidAssumeForContext(I, CtxI, DT))
				continue;

			// :attention: llvm-19+
			Value *Arg = I->getArgOperand(0);
			if (match(Arg, m_c_Or(m_Specific(LHS_n), m_Specific(RHS)))) {
				// L ==> R == ~L | R
				return true;
			}
		}
	}

	return {};
}

const std::string IMPLICATION_CACHE_INSTR_NAME_PREFIX = "impCache";
// :param isImpliedTrue: if true cache that the LHS==>RHS else !(LHS==>RHS)
bool addImplicationAssume(IRBuilderBase &Builder, Value *LHS, Value *RHS,
		bool isImpliedTrue) {
	using Predicate = ICmpInst::Predicate;
	Value *Cond;
	if (isImpliedTrue) {
		/*
		 * L R  <= (L ==> R)
		 * 0 0  1
		 * 0 1  1
		 * 1 0  0
		 * 1 1  1
		 * */
		Cond = Builder.CreateICmp(Predicate::ICMP_ULE, LHS, RHS, IMPLICATION_CACHE_INSTR_NAME_PREFIX);
		Builder.CreateAssumption(Cond);
	} else {
		// currently can not cache that the L & !R is possible because
		// it would mean that L and R may have any value and thus assume would have no meaning
		// and would be immediately removed
	}
	return isImpliedTrue;
}

std::optional<bool> _isImplidConditionAndOrTree(IRBuilderBase &Builder,
		Value *LHS, Value *RHS, const DataLayout &DL, AssumptionCache *AC,
		const DominatorTree *DT, const Instruction *CtxI) {
	Value *LHS0, *LHS1;
	// (a&b==>x) == ((a==>x) | (b==>x))
	if (match(LHS, m_LogicalAnd(m_Value(LHS0), m_Value(LHS1)))) {
		// check for the case where LHS and RHS are both AND trees and LHS has all RHS terms
		// thus is always satisfied if RHS=1
		SmallPtrSet<Value*, 16> LHSandTerms;
		SmallPtrSet<Value*, 16> RHSandTerms;
		collectAndTerms(*LHS, LHSandTerms);
		collectAndTerms(*RHS, RHSandTerms);
		auto isImpliedRHS = [&Builder, &LHSandTerms, AC, &DL, DT, CtxI](
				Value *RHSTerm) -> bool {
			if (LHSandTerms.contains(RHSTerm)) {
				return true;
			}
			for (auto *LHSTerm : LHSandTerms) {
				if (auto impl = isImpliedConditionAndOrTree(Builder, LHSTerm,
						RHSTerm, DL, AC, DT, CtxI)) {
					if (impl.value())
						return true;
				}
			}
			return false;
		};

		if (LHSandTerms.size() >= RHSandTerms.size()
				&& all_of(RHSandTerms, isImpliedRHS)) {
			//RHSandTerms is subset of LHSandTerms
#ifdef DEBUG_TRACE_isImpliedCondition
			dbgs() << "1 (RHSandTerms is subset of LHSandTerms)\n";
#endif
			return addImplicationAssume(Builder, LHS, RHS, true);
		}

		return {};
	}
	// (a|b==>x) == ((a==>x) & (b==>x))
	if (match(LHS, m_LogicalOr(m_Value(LHS0), m_Value(LHS1)))) {
		SmallPtrSet<Value*, 16> LHSorTerms;
		collectOrTerms(*LHS, LHSorTerms);
		for (auto LHSOrTerm : LHSorTerms) {
			std::optional<bool> impl = isImpliedConditionAndOrTree(Builder,
					LHSOrTerm, RHS, DL, AC, DT, CtxI);
			if (!impl.has_value()) {
#ifdef DEBUG_TRACE_isImpliedCondition
				dbgs() << "{} unknown for LHSOrTerm==>RHS\n";
#endif
				return {};
			}
			if (!impl.value()) {
#ifdef DEBUG_TRACE_isImpliedCondition
				dbgs() << "0 LHSOrTerm=/=>RHS\n";
#endif
				return addImplicationAssume(Builder, LHS, RHS, false);
			}
		}
#ifdef DEBUG_TRACE_isImpliedCondition
		dbgs() << "1 all LHSOrTerm==>RHS\n";
#endif
		return addImplicationAssume(Builder, LHS, RHS, true);
	}

//	Value *RHS0, *RHS1;
//	// (x==>a|b) == ((x==>a)|(x==>b))
//	if (match(RHS, m_LogicalOr(m_Value(RHS0), m_Value(RHS1)))) {
//		SmallPtrSet<Value*, 16> RHSorTerms;
//		collectOrTerms(*RHS, RHSorTerms);
//		for (auto RHSorTerm : RHSorTerms) {
//			std::optional<bool> impl = isImpliedConditionAndOrTree(Builder, LHS,
//					RHSorTerm, DL, AC, DT, CtxI);
//			if (impl.has_value() && impl.value()) {
//#ifdef DEBUG_TRACE_isImpliedCondition
//			dbgs() << "1 some LHS==>RHSorTerm\n";
//#endif
//				return addImplicationAssume(Builder, LHS, RHS, true);
//			}
//		}
//#ifdef DEBUG_TRACE_isImpliedCondition
//			dbgs() << "{} LHS=/=> all RHSorTerm\n";
//#endif
//		return {};
//	}
//
//	// (x==>a&b) == ((x==>a)&(x==>b))
//	if (match(RHS, m_LogicalAnd(m_Value(RHS0), m_Value(RHS1)))) {
//		SmallPtrSet<Value*, 16> RHSandTerms;
//		collectAndTerms(*RHS, RHSandTerms);
//		for (auto RHSAndTerm : RHSandTerms) {
//			std::optional<bool> impl = isImpliedConditionAndOrTree(Builder, LHS,
//					RHSAndTerm, DL, AC, DT, CtxI);
//			if (!impl.has_value()) {
//#ifdef DEBUG_TRACE_isImpliedCondition
//			dbgs() << "(x==>a&b) {} unknown LHS ==> any RHSandTerm\n";
//#endif
//				return {};
//			}
//			if (!impl.value()) {
//#ifdef DEBUG_TRACE_isImpliedCondition
//			dbgs() << "(x==>a&b) 0 LHS=/=> any RHSandTerm\n";
//#endif
//				return addImplicationAssume(Builder, LHS, RHS, false);
//			}
//		}
//#ifdef DEBUG_TRACE_isImpliedCondition
//			dbgs() << "(x==>a&b) 1 LHS==> all RHSandTerm\n";
//#endif
//		return addImplicationAssume(Builder, LHS, RHS, true);
//	}
#ifdef DEBUG_TRACE_isImpliedCondition
	dbgs()
			<< "unknown, not in format of a&b==>x, a|b==>x, x==>a&b, x==>a|b (&| is allowed to be variadic)\n";
#endif
	return {};
}
std::optional<bool> isImpliedConditionAndOrTree(IRBuilderBase &Builder,
		Value *LHS, Value *RHS, const DataLayout &DL, AssumptionCache *AC,
		const DominatorTree *DT, const Instruction *CtxI) {
	// llvm::isImpliedCondition check for and/or/select/icmp in LHS only if RHS is ICMP,
	// this means cases like: (a&b==>x)==((a==>x)|(b==>x)) are not checked
#ifdef DEBUG_TRACE_isImpliedCondition
	errs() << "isImpliedConditionAndOrTree " << *LHS << " ==> " << *RHS << "\n";
#endif
	if (auto RHSC = dyn_cast<ConstantInt>(RHS)) {
		if (RHSC->isAllOnesValue()) {
			// x==>1 -> 1
#ifdef DEBUG_TRACE_isImpliedCondition
			dbgs() << "x==>1\n";
#endif
			return true;
		}
	}
	if (auto impl = isImpliedConditionByAssume(LHS, RHS, *AC, DT, CtxI)) {
#ifdef DEBUG_TRACE_isImpliedCondition
		dbgs() << impl.value() << " (cached)\n";
#endif
		return impl.value();
	}
	if (auto impl = isImpliedCondition(LHS, RHS, DL)) {
#ifdef DEBUG_TRACE_isImpliedCondition
		dbgs() << impl.value() << " (llvm::isImpliedCondition)\n";
#endif
		return addImplicationAssume(Builder, LHS, RHS, impl.value());
	}

	// cover case of ult with non overflowing add,
	// v0 cmp C, and (v0 + nuw x) cmp C; (because if the value increase it can not get smaller)
	//  %RHS = icmp ult i9 %v0, 128
	//  %1 = zext i9 %v0 to i10
	//  %2 = add nuw i10 %1, %x
	//  %LHS = icmp ult i10 %2, 128
	ConstantInt *RHS_C;
	ConstantInt *LHS_C;
	Value *v0, *x;
	using Predicate= ICmpInst::Predicate;
	CmpPredicate RHS_Pred, LHS_Pred;
	auto getConstants = [&RHS_C, &LHS_C]() -> std::pair<APInt, APInt> {
		size_t width = std::max(LHS_C->getType()->getIntegerBitWidth(),
				RHS_C->getType()->getIntegerBitWidth());
		return {LHS_C->getValue().zext(width), RHS_C->getValue().zext(width)};
	};
	auto addSubHasNoUnsignedWrap =
			[LHS]() {
				return dyn_cast<Instruction>(
						dyn_cast<Instruction>(LHS)->getOperand(0))->hasNoUnsignedWrap();
			};
	APInt CL, CR;
	if (match(RHS, m_ICmp(RHS_Pred, m_Value(v0), m_ConstantInt(RHS_C)))) {
		// case for <, <=
		if (match(LHS,
				m_ICmp(LHS_Pred,
						m_c_Add(m_ZExtOrSelf(m_Specific(v0)), m_Value(x)),
						m_ConstantInt(LHS_C))) && addSubHasNoUnsignedWrap()) {
			if (CmpPredicate::getMatching(RHS_Pred, LHS_Pred).has_value()
					&& (RHS_Pred == Predicate::ICMP_ULT
							|| RHS_Pred == Predicate::ICMP_ULE)) {
				// if LHS_C <= RHS_C, RHS is always 1 if LHS is 1, LHS ==> RHS
				std::tie(CL, CR) = getConstants();
				if (CL.ule(CR)) {
#ifdef DEBUG_TRACE_isImpliedCondition
					errs() << " non-wrap add cmp proven" << *LHS << " ==> "
							<< *RHS << "   " << CL << "   " << CR << "\n";
#endif
					return true;
				}
			}
		} else if (match(LHS,
				m_ICmp(LHS_Pred,
						m_Sub(m_ZExtOrSelf(m_Specific(v0)), m_Value(x)),
						m_ConstantInt(LHS_C))) && addSubHasNoUnsignedWrap()) {
			// same thing just for >, >=
			if (CmpPredicate::getMatching(RHS_Pred, LHS_Pred).has_value()
					&& (RHS_Pred == Predicate::ICMP_UGT
							|| RHS_Pred == Predicate::ICMP_UGE)) {
				// if LHS_C >= RHS_C it is more constraining thus LHS ==> RHS
				std::tie(CL, CR) = getConstants();
				if (CL.uge(CR)) {
#ifdef DEBUG_TRACE_isImpliedCondition
					errs() << " non-wrap sub cmp proven" << *LHS << " ==> "
							<< *RHS << "   " << CL << "   " << CR << "\n";
#endif
					return true;
				}
			}

		}
	}
	return _isImplidConditionAndOrTree(Builder, LHS, RHS, DL, AC, DT, CtxI);
}

void pruneImpliedConditionsAndLastLikelyMostSpecific(
		llvm::SmallVector<llvm::Value*> &conditionsForAnd,
		llvm::IRBuilderBase &Builder, const llvm::DataLayout &DL,
		llvm::AssumptionCache *AC, const llvm::DominatorTree *DT,
		const llvm::Instruction *CtxI) {
	bool change = false;
	for (auto VIt = conditionsForAnd.begin(); VIt != conditionsForAnd.end();
			VIt++) {
		if (VIt != conditionsForAnd.begin()) {
			auto *cur = *VIt;
			auto *prev = *(VIt - 1);
			if (isImpliedConditionAndOrTree(Builder, cur, prev, DL, AC, DT,
					CtxI)) {
				*(VIt - 1) = nullptr; // if current implies that the prev==1 prev is useless in and
				// because it is always 1 if current==1
				change = true;
			}
		}
	}
	if (change) {
		conditionsForAnd.erase(
				std::remove_if(conditionsForAnd.begin(), conditionsForAnd.end(),
						[](const auto *V) {
							return V == nullptr;
						}), conditionsForAnd.end());
	}
}

}
