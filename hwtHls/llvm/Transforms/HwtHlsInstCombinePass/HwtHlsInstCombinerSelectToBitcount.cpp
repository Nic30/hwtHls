#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <llvm/IR/PatternMatch.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>

// #define DBG_VERIFY_AFTER_MODIFICATION

#ifdef DBG_VERIFY_AFTER_MODIFICATION
#include <llvm/IR/Verifier.h>
#endif

// #undef LLVM_DEBUG
// #define LLVM_DEBUG(x) x

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

// %incrEn = icmp ne i9 %v0, 128 ; add limit, incr enable, rewrite this to operate on top most input v0, in this case umax(ctlz, 128)
// %48 = icmp eq i9 %v0, 127 ; logic unrelated to ctlz, rewrite it to use result of ctlz, in this case (icmp eq (ctlz ), 127) & !And(cur incrEn to last)
// %49 = or i1 %46, %48 ; logic unrelated to ctlz, should be sinked behind ctlz
// %50 = and i1 %47, %49 ; logic unrelated to ctlz, should be sinked behind ctlz
// %v1 = add i9 %v0, 1 ; incr
// %v2 = select i1 %incrEn, i9 %v1, i9 %v0 ; inc select
std::optional<HwtHlsInstCombiner::BitCountExprFragment> HwtHlsInstCombiner::_searchChainOfOptionalPlus1AddersDefUse_matchOne(
		llvm::SelectInst *&SI, Value *&v0,
		bool &allConditionsAreNegated) const {
	std::optional<HwtHlsInstCombiner::BitCountExprFragment> res;
	auto VT = SI->getTrueValue();
	auto VF = SI->getFalseValue();
	auto *BB = SI->getParent();
	// %v1 = add i9 %v0, 1
	if (match(VT, m_Add(m_Specific(VF), m_SpecificInt(1)))) {
		// %v2 = select i1 %c0, i9 %v1, i9 %v0
		allConditionsAreNegated = false;
		res = BitCountExprFragment(dyn_cast<BinaryOperator>(VT), SI, false);
		v0 = VF;
		SI = dyn_cast<SelectInst>(v0);
	} else if (match(VF, m_Add(m_Specific(VT), m_SpecificInt(1)))) {
		// %v2 = select i1 %c0, i9 %v0, i9 %v1
		res = BitCountExprFragment(dyn_cast<BinaryOperator>(VF), SI, true);
		v0 = VT;
		SI = dyn_cast<SelectInst>(v0);
	} else {
		SI = nullptr;
	}
	if (SI) {
		// v2 is now predecessor select of and for original v2
		if (SI->getParent() != BB)
			SI = nullptr; // this searches only in a single block
	}
	return res;
}

bool HwtHlsInstCombiner::_searchChainOfOptionalPlus1AddersDefUse(
		SmallVector<BitCountExprFragment> &adderLevels, llvm::SelectInst &SI,
		bool &allConditionsAreNegated) {
	Value *v0 = nullptr;
	allConditionsAreNegated = true;
	for (SelectInst *v2 = &SI; v2 != nullptr;) {
		if (auto lvl = _searchChainOfOptionalPlus1AddersDefUse_matchOne(v2, v0,
				allConditionsAreNegated)) {
			adderLevels.push_back(lvl.value());
		}
	}

	return v0 != nullptr;
}

std::optional<std::pair<ICmpInst::Predicate, Value*>> HwtHlsInstCombiner::_findLimitInAndFromForBitcount(
		SmallVector<BitCountExprFragment> &adderLevels,
		SmallVector<Value*> &realConditions) {
	std::optional<std::pair<ICmpInst::Predicate, Value*>> limit;
	for (BitCountExprFragment &lvl : adderLevels) {
		// check if every condition is in format: anyVal0 & (icmp v0, anyVal1)
		auto v0 = lvl.getInputVal();
		auto C = lvl.getCondition().first;
		Value *limitVal, *realCond;
		ICmpInst::Predicate Pred;
		if (match(C,
				m_And(m_Value(realCond),
						m_ICmp(Pred, m_Specific(v0), m_Value(limitVal))))) {
			if (limit.has_value()) {
				if (limit.value().first != Pred
						|| limit.value().second != limitVal) {
					return {};
				}
			} else {
				limit = { Pred, limitVal };
			}
			realConditions.push_back(realCond);
		} else if (match(C,
				m_And(m_ICmp(Pred, m_Specific(v0), m_Value(limitVal)),
						m_Value(realCond)))) {
			// match the same pattern but with and operands swapped
			if (limit.has_value()) {
				if (limit.value().first != Pred
						|| limit.value().second != limitVal) {
					return {};
				}
			} else {
				limit = { Pred, limitVal };
			}
			realConditions.push_back(realCond);
		} else {
			return {};
		}
	}
	return limit;
}

bool HwtHlsInstCombiner::_sinkAfterInSameBlockRecursively(Instruction &IToMove,
		Instruction &I) {
	if (&IToMove == &I)
		return false; // we would need to move I itself, this happens if I depends on IToMove and in this case sink is not possible

	if (IToMove.getParent() != I.getParent())
		return true; // user outside of block does not need to be sinked behind something in this block
	if (I.comesBefore(&IToMove))
		return true; // already moved
	assert(!isa<PHINode>(I));
	// move users first so then end up after this
	for (auto U : IToMove.users()) {
		if (auto UI = dyn_cast<Instruction>(U)) {
			if (!_sinkAfterInSameBlockRecursively(*UI, I)) {
				return false;
			}
		}
	}
	IToMove.moveAfter(&I);
	return true;
}

void HwtHlsInstCombiner::_replaceTopOfAdderChainWithNewlyAddedLimitCheck(
		MutableArrayRef<BitCountExprFragment> adderLevels,
		MutableArrayRef<Value*> realConditions, Value *replacement) {
	// replace output of adder tree with expression which implements intermediate
	// limit check on the final value only
	// :note: this checks the v0+bitcnt which currently is the select in last level
	//  of adders. This select will be however later replaced with v0+bitcnt.
	assert(replacement);
	Worklist.pushValue(replacement);
	Instruction *res = adderLevels.back().getExitVal();
	auto newC = realConditions.begin();
	for (BitCountExprFragment &lvl : adderLevels) {
		auto C = lvl.select->getCondition();
		replaceOperand(*lvl.select, 0, *newC);
		++newC;
		eraseInstrRecursivelyIfTriviallyDead(*C);
	}
	// newly generated instructions must be excluded from replacement of final value
	// for adder tree, because they are the replacement of it and must remain to use original value
	SmallPtrSet<Instruction*, 16> instructionsImplementingLimitCheck;
	for (auto &I : make_range(res->getIterator(), Builder.GetInsertPoint())) {
		instructionsImplementingLimitCheck.insert(&I);
	}

	SmallVector<const Use*, 16> Uses(make_pointer_range(res->uses()));
	for (const auto &_U : Uses) {
		const Use &U = *_U;
		if (instructionsImplementingLimitCheck.contains(
				dyn_cast<Instruction>(U.getUser())))
			continue;

		replaceOperand(*dyn_cast<Instruction>(U.getUser()), U.getOperandNo(),
				replacement);
	}
}

void HwtHlsInstCombiner::_rewriteAllUsesOfIntermediateValuesInBitcount_collectInternallyUsedInstr(
		Instruction &firstInstr, BasicBlock &BB,
		std::set<Instruction*> &instrUsedInternally, Value &V) {
	if (auto I = dyn_cast<Instruction>(&V)) {
		if (instrUsedInternally.contains(I))
			return; // already collected
		if (I->getParent() == &BB && !isa<PHINode>(I)
				&& firstInstr.comesBefore(I)) {
			instrUsedInternally.insert(I);
			for (auto O : I->operand_values()) {
				_rewriteAllUsesOfIntermediateValuesInBitcount_collectInternallyUsedInstr(
						firstInstr, BB, instrUsedInternally, *O);
			}
		}
	}
}

Value* HwtHlsInstCombiner::_constructLimitExprForBitcnt1_NE_ULT_ULE(
		std::pair<ICmpInst::Predicate, Value*> limit, Value *v0,
		Value *currentBitcountRes) {
	const auto Pred = limit.first;
	Type *Ty = v0->getType();
	Value *limitV = limit.second;

	// all intermediate adds must be performed on +1 bitwidth to prevent overflows
	Type *TmpTy = currentBitcountRes->getType();
	currentBitcountRes = Builder.CreateZExt(currentBitcountRes, TmpTy);
	limitV = Builder.CreateZExt(limitV, TmpTy);

	Value *resWithLimitApplied = nullptr;
	switch (Pred) {
	case ICmpInst::Predicate::ICMP_NE: {
		// ne -> umin(v0+res, limit) // todo overflows, this is true only if and does not overflow
		auto lhs = currentBitcountRes; //Builder.CreateAdd(v0, bitcountRes);
		Worklist.pushValue(lhs);
		auto rhs = limitV; //Builder.CreateSub(limitV, ConstantInt::get(Ty, 1));
		Worklist.pushValue(rhs);
		resWithLimitApplied = Builder.CreateBinaryIntrinsic(Intrinsic::umin,
				lhs, rhs);
		break;
	}
	case ICmpInst::Predicate::ICMP_ULT: {
		// ult -> v0 < limit ? umin(v0+res, limit) : v0
		auto ult = Builder.CreateICmpULT(v0, limitV);
		auto uminLhs = currentBitcountRes; //Builder.CreateAdd(v0, bitcountRes);
		Worklist.pushValue(uminLhs);
		auto uminRhs = limitV; //Builder.CreateSub(limitV, ConstantInt::get(Ty, 1));
		Worklist.pushValue(uminRhs);
		Value *umin = Builder.CreateBinaryIntrinsic(Intrinsic::umin, uminLhs,
				uminRhs);
		Worklist.pushValue(umin);
		resWithLimitApplied = Builder.CreateSelect(ult, umin, v0);
		break;
	}
	case ICmpInst::Predicate::ICMP_ULE: {
		// ule -> v0 <= limit ? umin(v0+res, limit+1) : v0
		auto ult = Builder.CreateICmpULT(v0, limitV);
		auto uminLhs = currentBitcountRes; // Builder.CreateAdd(v0, bitcountRes);
		Worklist.pushValue(uminLhs);
		auto uminRhs = Builder.CreateAdd(limitV, ConstantInt::get(TmpTy, 1));
		Worklist.pushValue(uminRhs);
		Value *umin = Builder.CreateBinaryIntrinsic(Intrinsic::umin, uminLhs,
				uminRhs);
		Worklist.pushValue(umin);
		resWithLimitApplied = Builder.CreateSelect(ult, umin, v0);
		break;
	}
	default:
		llvm_unreachable(
				"This function should be called only for NE, ULT, ULE");
	}
	resWithLimitApplied = Builder.CreateZExtOrTrunc(resWithLimitApplied, Ty);
	return resWithLimitApplied;
}

Value* HwtHlsInstCombiner::_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_applyLimit(
		MutableArrayRef<BitCountExprFragment> adderLevels,
		MutableArrayRef<Value*> realConditions,
		std::optional<std::pair<ICmpInst::Predicate, Value*>> limit,
		Value *currentBitcountRes) {
	// try rewrite limit check to operate on final value instead of operating on every intermediate result
	const auto Pred = limit.value().first;
	Value *replacement = nullptr;
	Value *v0 = adderLevels.front().getInputVal();
	Type *Ty = v0->getType();
	Value *limitV = limit.value().second;

	switch (Pred) {
	case ICmpInst::Predicate::ICMP_EQ: {
		// incremented only once if any equals limit and any condition bit is 1
		// eq -> finalBitcountRes = (v0==limit && or(*cond)) ? 1: 0
		auto eqLimit = Builder.CreateICmpEQ(v0, limitV);
		Worklist.pushValue(eqLimit);
		Value *anyCond = realConditions[0];
		for (unsigned i = 1; i < realConditions.size(); i++) {
			anyCond = Builder.CreateOr(anyCond, realConditions[i]);
			Worklist.pushValue(anyCond);
		}
		auto C = Builder.CreateAnd(eqLimit, anyCond);
		Worklist.pushValue(C);
		replacement = Builder.CreateSelect(C, ConstantInt::get(Ty, 1),
				ConstantInt::get(Ty, 0));
		Worklist.pushValue(replacement);
		replacement->takeName(currentBitcountRes);
		break;
	}
	case ICmpInst::Predicate::ICMP_NE:
	case ICmpInst::Predicate::ICMP_ULT:
	case ICmpInst::Predicate::ICMP_ULE: {
		replacement = _constructLimitExprForBitcnt1_NE_ULT_ULE(limit.value(),
				v0, currentBitcountRes);
		replacement->takeName(currentBitcountRes);
		break;
	}
	default:
		// unknown limit predicate, do not know how to replace
		replacement = nullptr;
	}

	return replacement;
}

Value* HwtHlsInstCombiner::_rewriteAllUsesOfIntermediateValuesInBitcount_CTLO_applyLimit(
		MutableArrayRef<BitCountExprFragment> adderLevels,
		MutableArrayRef<Value*> realConditions,
		std::optional<std::pair<ICmpInst::Predicate, Value*>> limit,
		Value *currentBitcountRes) {

	// try rewrite limit check to operate on final value instead of operating on every intermediate result
	const auto Pred = limit.value().first;
	Builder.SetInsertPoint(adderLevels.back().getExitVal()->getNextNode());
	Value *replacement = nullptr;
	Value *v0 = adderLevels.front().getInputVal();
	Type *Ty = v0->getType();
	Type*TmpTy = currentBitcountRes->getType();
	assert(TmpTy->getIntegerBitWidth() >= Ty->getIntegerBitWidth());
	Instruction *originalBitcoutRes = adderLevels.back().getExitVal();

	switch (Pred) {
	case ICmpInst::Predicate::ICMP_EQ: {
		v0 = Builder.CreateZExtOrTrunc(currentBitcountRes, TmpTy);
		Value *limitV = Builder.CreateZExtOrTrunc(limit.value().second, TmpTy);
		// eq -> (v0==limit && cond[0]) ? 1: 0
		auto eqLimit = Builder.CreateICmpEQ(v0, limitV);
		Worklist.pushValue(eqLimit);
		auto c = Builder.CreateAnd(eqLimit, realConditions[0]);
		Worklist.pushValue(c);
		replacement = Builder.CreateSelect(c, ConstantInt::get(Ty, 1),
				ConstantInt::get(Ty, 0));
		replacement->takeName(originalBitcoutRes);
		break;
	}
	case ICmpInst::Predicate::ICMP_NE:
	case ICmpInst::Predicate::ICMP_ULT:
	case ICmpInst::Predicate::ICMP_ULE: {
		replacement = _constructLimitExprForBitcnt1_NE_ULT_ULE(limit.value(),
				v0, currentBitcountRes);
		replacement->takeName(originalBitcoutRes);
		break;
	}
	default:
		replacement = nullptr;
	}
	return replacement;
}

void HwtHlsInstCombiner::_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_externalUserOfSelect(
		MutableArrayRef<BitCountExprFragment> adderLevels,
		MutableArrayRef<Value*> realCondtions,
		std::optional<std::pair<ICmpInst::Predicate, Value*>> limit,
		size_t lvlIndex, Value *topMostBitcountRes,
		bool allConditionsAreNegated, const ConcatMemberVector &srcOpBits,
		const BitcountOpType bitCntOpTy, Value *&bitcntForThisPart,
		const Use *U) {
	assert(topMostBitcountRes);
	using Predicate = CmpInst::Predicate;
	Predicate Pred;
	Value *RHS;
	auto lvl = adderLevels.begin() + lvlIndex;
	if (match(U->getUser(),
			m_ICmp(Pred, m_Specific(lvl->select), m_Value(RHS)))) {
		switch (Pred) {
		case Predicate::ICMP_EQ: {
			// res == RHS && all successor conditions 0
			auto eqRhs = Builder.CreateICmpEQ(topMostBitcountRes, RHS);
			Worklist.pushValue(eqRhs);
			Value *C;
			if (lvl + 1 == adderLevels.end()) {
				// last, there is no successor condition
				C = topMostBitcountRes;
			} else {
				Value *anyCond = nullptr;
				auto CIt = realCondtions.begin() + (lvlIndex + 1);
				for (auto l : make_range((lvl + 1), adderLevels.end())) {
					assert(
							!l.getCondition().second
									&& "Implemented only for non-negated conditions");
					Value *LvlC = *CIt;
					if (anyCond) {
						anyCond = Builder.CreateOr(anyCond, LvlC);
						Worklist.pushValue(anyCond);
					} else {
						anyCond = LvlC;
					}
					++CIt;
				}
				auto anyCondN = Builder.CreateNot(anyCond);
				Worklist.pushValue(anyCondN);
				C = Builder.CreateAnd(eqRhs, anyCondN);
				Worklist.pushValue(C);
			}
			auto &cmpI = *dyn_cast<ICmpInst>(U->getUser());
			if (auto resI = dyn_cast<Instruction>(topMostBitcountRes))
				assert(_sinkAfterInSameBlockRecursively(cmpI, *resI));
			replaceInstUsesWith(cmpI, C);
			return;
		}
		default:
			break;
		}
	}

	if (!bitcntForThisPart) {
		// create a smaller ctpop for prefix bits only and use it instead of this
		auto predLevels = MutableArrayRef(adderLevels.begin(), lvl);
		auto predConditions = MutableArrayRef(realCondtions.begin(),
				realCondtions.begin() + lvlIndex);
		Builder.SetInsertPoint(lvl->select->getNextNode());
		Value *bitcountRes = _createBitcountFromAdderSelectTreeConditions(
				predLevels, predConditions, allConditionsAreNegated, srcOpBits,
				adderLevels[0].getInputVal(), bitCntOpTy, true);
		bitcntForThisPart =
				_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_applyLimit(
						predLevels, predConditions, limit, bitcountRes);
		assert(bitcntForThisPart);
#ifdef DBG_VERIFY_AFTER_MODIFICATION
		if (verifyFunction(F, &errs())) {
			F.dump();
			throw std::runtime_error(
					"_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_conditions broke function");
		}
#endif
		//ConcatMemberVector srcOpBits;
		//Value *partCtpopSrc = _createBitcountConditionConcatenation(predLevels,
		//		predConditions, false, srcOpBits);
		//
		//Worklist.addValue(partCtpopSrc);
		//auto name = adderLevels.back().select->getName();
		//Value *partCtpop = Builder.CreateIntrinsic(Intrinsic::ctpop, {
		//		partCtpopSrc->getType() }, { partCtpopSrc }, nullptr,
		//		name + ".partCtpopSrc." + Twine(lvlIndex));
		//Worklist.addValue(partCtpop);
		//partCtpop = Builder.CreateZExtOrTrunc(partCtpop, res->getType());
		//Worklist.addValue(partCtpop);
		// bitcntForThisPart = Builder.CreateAdd(adderLevels.front().getInputVal(),
		// 		partCtpop, name + "partCtpop." + Twine(lvlIndex) + ".res");
	}
	auto userI = dyn_cast<Instruction>(U->getUser());
	assert(userI);
	replaceOperand(*userI, U->getOperandNo(), bitcntForThisPart);
	if (auto resI = dyn_cast<Instruction>(topMostBitcountRes))
		assert(_sinkAfterInSameBlockRecursively(*userI, *resI));
}

HwtHlsInstCombiner::BITCOUNT_REWIRTE_RES HwtHlsInstCombiner::_rewriteAllUsesOfIntermediateValuesInBitcount(
		Intrinsic::IndependentIntrinsics intrinsicOpc, bool hasInvertedInput,
		SmallVector<BitCountExprFragment> &adderLevels,
		bool allConditionsAreNegated, const ConcatMemberVector &srcOpBits,
		const BitcountOpType bitCntOpTy) {
	// %v1 = add i9 %v0, 1
	// %v2 = select i1 %c0, i9 %v1, i9 %v0
	// if v1 has only v2 as a user and v2 is used only by next adder and next select this does not need any further checks
	auto hasIntermediateUses = [&]() {
		for (auto _lvl = adderLevels.begin(); _lvl != adderLevels.end();
				++_lvl) {
			if (!_lvl->add->hasNUndroppableUses(1)) {
				return true;
			}
			bool isLast = _lvl == adderLevels.end() - 1;
			if (!isLast && !_lvl->select->hasNUndroppableUses(2)) {
				return true;
			}
		}
		return false;
	};
	if (!hasIntermediateUses())
		return BITCOUNT_REWIRTE_RES::NO_INTERMEDIATE_USE; // no hoisting/sinking is required because this do not have any uses of intermediate values

	std::set<Instruction*> instrUsedInternally;
	auto &firstInstr = *adderLevels.front().add;
	auto &BB = *firstInstr.getParent();
	bool resReplaced = false;
	switch (intrinsicOpc) {
	case Intrinsic::ctpop: {
		if (hasInvertedInput)
			return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE; // NotImplemented (popcnt(~x))
		else if (!all_of(adderLevels, [](BitCountExprFragment &lvl) {
			return !lvl.selectConditionNegated;
		})
			)
			// NotImplemented (matching of limit is not aware of condition negations)
			return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE;
		break;
	}
	case Intrinsic::ctlz: {
		if (!hasInvertedInput)
			return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE; // NotImplemented (ctlz(x))
		else if (!all_of(adderLevels, [](BitCountExprFragment &lvl) {
			return !lvl.selectConditionNegated;
		})
			)
			// NotImplemented (matching of limit is not aware of that)
			return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE;
		break;
	}
	case Intrinsic::cttz: {
		return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE; // NotImplemented (cttz(x))
	}
	default:
		llvm_unreachable("Unexpected bitcount instruction");
	}

	// rm result limit checks from conditions of select tree implementing bitcount
	SmallVector<Value*> realConditions;
	std::optional<std::pair<ICmpInst::Predicate, Value*>> limit =
			_findLimitInAndFromForBitcount(adderLevels, realConditions);
	if (!limit.has_value()) {
		// intermediate uses do not implement recognizable limit check
		return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE;
	}

	Builder.SetInsertPoint(adderLevels.back().getExitVal()->getNextNode());
	Value *bitcountRes = _createBitcountFromAdderSelectTreeConditions(
			adderLevels, realConditions, allConditionsAreNegated, srcOpBits,
			adderLevels[0].getInputVal(), bitCntOpTy, true);
	switch (intrinsicOpc) {
	case Intrinsic::ctpop: {
		Value *topMostBitcountResWithLimit =
				_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_applyLimit(
						adderLevels, realConditions, limit, bitcountRes);
		if (topMostBitcountResWithLimit) {
			_replaceTopOfAdderChainWithNewlyAddedLimitCheck(adderLevels,
					realConditions, topMostBitcountResWithLimit);
			resReplaced = true;
		}
#ifdef DBG_VERIFY_AFTER_MODIFICATION
		if (verifyFunction(F, &errs())) {
			F.dump();
			throw std::runtime_error(
					"_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_conditions broke function");
		}
#endif

		if (!hasIntermediateUses())
			return BITCOUNT_REWIRTE_RES::COMPLETLY_REWRITTEN;

		if (topMostBitcountResWithLimit == nullptr) {
			topMostBitcountResWithLimit = adderLevels.back().getExitVal();
		}
		auto resI = dyn_cast<Instruction>(topMostBitcountResWithLimit);
		_rewriteAllUsesOfIntermediateValuesInBitcount_collectInternallyUsedInstr(
				firstInstr, BB, instrUsedInternally,
				*adderLevels.back().getExitVal());

		// rewrite all potential users of intermediate values,
		// iterate adders from back, to hoist lower layers first
		for (auto lvl = adderLevels.rbegin(); lvl != adderLevels.rend();
				++lvl) {
			if (!lvl->add->hasNUndroppableUses(1)) {
				// only sinking of uses of select are implemented
				return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE;
			}
			bool isLast = lvl == adderLevels.rbegin();
			if (isLast) {
				// limit to last level select was already added in _rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_resolveFinalValue
				continue;
			}

			SmallVector<const Use*> addUses(
					make_pointer_range(lvl->select->uses()));
			auto predecLevel = (lvl - 1);
			Value *bitcntForThisLevel = nullptr;
			for (auto U : addUses) {
				if (U->getUser() == predecLevel->select
						|| U->getUser() == predecLevel->add) {
					continue;
				} else if (instrUsedInternally.contains(
						dyn_cast<Instruction>(U->getUser()))) {
					LLVM_DEBUG(
							dbgs()
									<< "_rewriteAllUsesOfIntermediateValuesInBitcount can not sink user because it is used internally: "
									<< *U->getUser() << "\n");
					return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE;
					// can not hoist because because we would need to create a specific ctpop just for prefix condition bits
					// can not sink because it is still used in some later condition for some select
				} else {
					size_t lvlIndex = std::distance(lvl, adderLevels.rend());
					assert(lvlIndex < adderLevels.size());
					LLVM_DEBUG(
							dbgs()
									<< "_rewriteAllUsesOfIntermediateValuesInBitcount rewriting user: "
									<< *U->getUser() << "\n");
					if (resI)
						Builder.SetInsertPoint(resI);
					_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_externalUserOfSelect(
							adderLevels, realConditions, limit, lvlIndex,
							topMostBitcountResWithLimit,
							allConditionsAreNegated, srcOpBits, bitCntOpTy,
							bitcntForThisLevel, U);
#ifdef DBG_VERIFY_AFTER_MODIFICATION
					if (verifyFunction(F, &errs())) {
						F.dump();
						throw std::runtime_error(
								"_rewriteAllUsesOfIntermediateValuesInBitcount_ctpop_externalUserOfSelect broke function");
					}
#endif
				}
			}
		}

		break;
	}
	case Intrinsic::ctlz: {
		auto replacement = _rewriteAllUsesOfIntermediateValuesInBitcount_CTLO_applyLimit(
				adderLevels, realConditions, limit, bitcountRes);
#ifdef DBG_VERIFY_AFTER_MODIFICATION
		if (verifyFunction(F, &errs())) {
			F.dump();
			throw std::runtime_error(
					"_rewriteAllUsesOfIntermediateValuesInBitcount_CTLO broke function");
		}
#endif
		if (replacement) {
			_replaceTopOfAdderChainWithNewlyAddedLimitCheck(adderLevels,
					realConditions, replacement);
			resReplaced = true;
		}
		// [todo] rewrite all intermediate users with max(bitcountRes, i)
		break;
	}
	case Intrinsic::cttz: {
		return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE; // NotImplemented (cttz(x))
	}
	default:
		llvm_unreachable("Unexpected bitcount instruction");
	}
	if (hasIntermediateUses()) {
		// it was not possible to remove intermediate uses
		return BITCOUNT_REWIRTE_RES::NOT_REWRITABLE;
	} else {
		if (!resReplaced) {
			_replaceTopOfAdderChainWithNewlyAddedLimitCheck(adderLevels,
					realConditions, bitcountRes);
			resReplaced = true;
#ifdef DBG_VERIFY_AFTER_MODIFICATION
			if (verifyFunction(F, &errs())) {
				F.dump();
				throw std::runtime_error(
						"_rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_conditions broke function");
			}
#endif
		}
		return BITCOUNT_REWIRTE_RES::COMPLETLY_REWRITTEN;
	}
}

Value* HwtHlsInstCombiner::_createBitcountConditionConcatenation(
		MutableArrayRef<BitCountExprFragment> addLevels,
		MutableArrayRef<Value*> realConditions, bool allConditionsAreNegated,
		ConcatMemberVector srcOpBits) {
	auto CIt = realConditions.begin();
	for (BitCountExprFragment &addLvl : addLevels) { // top most condition bit as last
		auto [_, cNegated] = addLvl.getCondition();
		assert(CIt != realConditions.end());
		Value *C = *CIt;
		if (!allConditionsAreNegated && cNegated) {
			C = Builder.CreateNot(C);
			Worklist.pushValue(C);
		}
		srcOpBits.push_back_Value(C);
		++CIt;
	}
	assert(!srcOpBits.members.empty());
	Value *C = srcOpBits.resolveValue(Builder, nullptr,
			&*Builder.GetInsertPoint());
	Worklist.addValue(C);
	return C;
}

HwtHlsInstCombiner::BitcountOpType HwtHlsInstCombiner::_getBitcountOpType(
		SmallVector<BitCountExprFragment> &addLevels,
		bool allConditionsAreNegated) {
	BitcountOpType res = { true, true };
	Value *PrevC = nullptr;
	bool PrevCNegated = false;
	for (BitCountExprFragment &addLvl : addLevels) { // top most condition bit as last
		// skip the first bit because it has no predecessor bit
		auto [C, cNegated] = addLvl.getCondition();
		if (PrevC) {
			// bool isGoingToBeNegated =!allConditionsAreNegated && cNegated;
			if (auto CI = dyn_cast<Instruction>(C)) {
				Builder.SetInsertPoint(CI->getNextNode());
			}
			if (allConditionsAreNegated) {
				res.mayBeCtlo = false; // count is incremented if if bit value is 0
				if (res.mayBeCtlz && cNegated && PrevCNegated) {
					if (auto impl = isImpliedConditionAndOrTree(Builder, C,
							PrevC, DL, &AC, &DT, addLvl.select)) {
						res.mayBeCtlz &= impl.value();
					} else {
						res.mayBeCtlz = false;
					}
				} else {
					res.mayBeCtlz = false;
				}
			} else {
				res.mayBeCtlz = false; // count is incremented if if bit value is 1
				if (res.mayBeCtlo && !cNegated && !PrevCNegated) {
					// count leading zero needs this bit to be zero only if previous bit was zero
					if (auto impl = isImpliedConditionAndOrTree(Builder, C,
							PrevC, DL, &AC, &DT, addLvl.select)) {
						res.mayBeCtlo &= impl.value();
					} else {
						res.mayBeCtlo = false;
					}
				} else {
					res.mayBeCtlo = false;
				}
			}
		}
		PrevC = C;
		PrevCNegated = cNegated;
	}
	//if (!mayBeCtlz && !mayBeCtlo) {
	//	for (auto& [C, cNegated]: conditions) { // top most condition bit as lsb
	//		if (!allConditionsAreNegated && cNegated) {
	//			//mayBeCttz
	//			//mayBeCtto
	//		}
	//	}
	//}
	return res;
}

bool HwtHlsInstCombiner::_isTopOfBitCountSelectTree(llvm::SelectInst &SI) {
	auto *_SI = &SI;
	Value *v0 = nullptr;
	bool allConditionsAreNegated = false;
	if (!_searchChainOfOptionalPlus1AddersDefUse_matchOne(_SI, v0,
			allConditionsAreNegated)) {
		return false; // this is not a level of an adder tree
	}
	// check if this is a top of adder tree
	if (SI.hasNUndroppableUsesOrMore(2)) {
		// optionally execute this on parent select, so we convert the largest possible bit count at once
		auto topSI = &SI;
		for (;;) {
			bool newTopFound = false;
			for (auto *U : topSI->users()) {
				if (SelectInst *USI = dyn_cast<SelectInst>(U)) {
					_SI = USI;
					if (_searchChainOfOptionalPlus1AddersDefUse_matchOne(_SI,
							v0, allConditionsAreNegated)) {
						topSI = USI; // this is not a top of adder tree
						newTopFound = true;
						break;
					}
				}
			}
			if (!newTopFound) {
				if (topSI != &SI) {
					Worklist.push(topSI);
					return false; // run this later on topSI and do nothing now
				} else {
					break;
				}
			}
		}
	}
	return true;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceSelectInst_deepAdderChainToBitCounts(
		llvm::SelectInst &SI, size_t extractionTreshold) {
	// collect adder pattern like this
	// %v1 = add i9 %v0, 1
	// %v2 = select i1 %c0, i9 %v1, i9 %v0 ; v2=SI, this is where this function starts and searches only up (to defs)
	// :note: the bool marks if the condition is in negated form (v0 is trueValue of select)
	// :note: top most condition first
	if (!Options.extractBitcounts)
		return nullptr;
	if (!_isTopOfBitCountSelectTree(SI))
		return nullptr;

	// search for chained optional adders
	bool allConditionsAreNegated;
	SmallVector<BitCountExprFragment> addLevels;
	if (!_searchChainOfOptionalPlus1AddersDefUse(addLevels, SI,
			allConditionsAreNegated))
		return nullptr; // nothing was found at all

	std::reverse(addLevels.begin(), addLevels.end()); // top most condition bit as last

	/*
	 * Problems:
	 * * There may be users of intermediate values in bitcount expression pattern. We need to hoist them before or sink them behind
	 *   because it is not possible to extract this pattern if something if we would let original instructions in place.
	 *   * In this case it is more beneficial to hoist if this is ctlz/ctlo/cttz/ctto because we can check that all predecessors/successors conditions
	 *     are 0/1 and the value can be replaced with extracted expression plus/minus some fixed offset.
	 * * Conditions depend on some intermediate value as well, for them only option is to hoist.
	 *   * if condition is always dependent on same type of ICmp of prev v0 with same rhs it means that it implements some
	 *     limit (min, max) on final value which can be extracted.
	 * */

	// reduce found pattern to
	// c = concat(c0, ..., cn) // lower bit first, :note: every bit can be negated depending on order of SelectInst operands
	// vn = v0 + ctpop(c)
	// later optionally try to prove cn+1 ===> cn for every c and if this is the case use ctlz/ctlo
	ConcatMemberVector srcOpBits;
	// if v0 itself is a ctpop or other bitcount we can potentially merge it with this
	// %otherBitCnt = call i4 @llvm.ctpop.i4(i4 %c0)
	// %v0.1 = zext i4 %otherBitCnt to i9
	// %v0 = add i9 %v0.0, %v0.1
	Value *v0 = addLevels[0].getInputVal();
	Value *v0_0, *v0_1, *otherBitCnt;
	bool hasCtpopPredecessor = false;
	if (match(v0, m_Add(m_Value(v0_0), m_Value(v0_1)))
			&& (match(v0_1, m_ZExt(m_Value(otherBitCnt)))
					|| match(v0_1, m_TruncOrSelf(m_Value(otherBitCnt))))) {
		if (auto *II = dyn_cast<IntrinsicInst>(otherBitCnt)) {
			Intrinsic::ID IID = II->getIntrinsicID();
			switch (IID) {
			case Intrinsic::ctpop: {
				auto SrcOp = II->getArgOperand(0);
				if (allConditionsAreNegated) {
					SrcOp = Builder.CreateNot(SrcOp);
				}
				srcOpBits.push_back_flattened(SrcOp); // add as least significant bits
				v0 = v0_0;
				hasCtpopPredecessor = true;
				break;
			}
			default:
				otherBitCnt = nullptr;
			}
		}
	}

	if (!hasCtpopPredecessor && addLevels.size() < extractionTreshold) {
#ifdef DBG_VERIFY_AFTER_MODIFICATION
		if (verifyFunction(*SI.getFunction(), &errs())) {
			F.dump();
			throw std::runtime_error(
					"tryReduceSelectInst_deepAdderChainToBitCounts broke function 0");
		}
#endif
		return nullptr;
	}
	auto bitCntOpTy = _getBitcountOpType(addLevels, allConditionsAreNegated);
	Intrinsic::IndependentIntrinsics intrinsicOpc;
	if (bitCntOpTy.mayBeCtlz || bitCntOpTy.mayBeCtlo) {
		intrinsicOpc = Intrinsic::ctlz;
	}
	//else if (bitCntOpTy.mayBeCtto || bitCntOpTy.mayBeCttz) {
	//}
	else {
		intrinsicOpc = Intrinsic::ctpop;
	}

	Builder.SetInsertPoint(&SI);
	bool hasInvertedInput = bitCntOpTy.mayBeCtlo; // || mayBeCtto;

	switch (_rewriteAllUsesOfIntermediateValuesInBitcount(intrinsicOpc,
			hasInvertedInput, addLevels, allConditionsAreNegated, srcOpBits,
			bitCntOpTy)) {
	case BITCOUNT_REWIRTE_RES::NOT_REWRITABLE: {
		// some intermediate value uses can not be hoisted or sinked and thus remains between
		// bitcount expressions which means we can not extract this pattern as a bitcount instruction.
#ifdef DBG_VERIFY_AFTER_MODIFICATION
		if (verifyFunction(*SI.getFunction(), &errs())) {
			F.dump();
			throw std::runtime_error(
					"tryReduceSelectInst_deepAdderChainToBitCounts broke function 1");
		}
#endif
		return nullptr;
	}
	case BITCOUNT_REWIRTE_RES::COMPLETLY_REWRITTEN:
		return nullptr;
	case BITCOUNT_REWIRTE_RES::NO_INTERMEDIATE_USE:
		break;
	default:
		llvm_unreachable("All case values should be checked");
	}

	// rewrite basic case of pure ctlz/ctlo/cttz/ctto/ctpop without any intermediate value use or limit check
	assert(
			!SI.user_empty()
					&& "The final replacement should be performed there");
	Builder.SetInsertPoint(&SI);
	SmallVector<Value*> conditions;
	for (BitCountExprFragment &addLvl : addLevels) {
		auto [_C, cNegated] = addLvl.getCondition();
		conditions.push_back(_C);
	}
	Value *res = _createBitcountFromAdderSelectTreeConditions(addLevels,
			conditions, allConditionsAreNegated, srcOpBits, v0, bitCntOpTy, false);
#ifdef DBG_VERIFY_AFTER_MODIFICATION
	if (verifyFunction(*SI.getFunction(), &errs())) {
		F.dump();
		throw std::runtime_error(
				"tryReduceSelectInst_deepAdderChainToBitCounts broke function 2");
	}
#endif
	assert(
			!SI.user_empty()
					&& "The final replacement should be performed there");
	assert(&SI == addLevels.back().select);
	return replaceInstUsesWith(SI, res);
}

Value* HwtHlsInstCombiner::_createBitcountFromAdderSelectTreeConditions(
		MutableArrayRef<BitCountExprFragment> addLevels,
		MutableArrayRef<Value*> conditions, bool allConditionsAreNegated,
		const ConcatMemberVector &srcOpBits, Value *v0,
		const BitcountOpType bitCntOpTy,
		bool hasLimitCheck) {
	Value *C = _createBitcountConditionConcatenation(addLevels, conditions,
			allConditionsAreNegated, srcOpBits);
	Value *bitCnt;
	//replaceOperand(*addLevels.front().add, 0, ConstantInt::get(SI.getType(), 0));
	if (bitCntOpTy.mayBeCtlo) {
		if (allConditionsAreNegated) {
			C = Builder.CreateNot(C);
		}
		bitCnt = Builder.CreateIntrinsic(Intrinsic::ctlz, { C->getType() }, { C, /*isZeroPoisonous*/
		Builder.getFalse() });
	} else if (bitCntOpTy.mayBeCtlz) {
		if (!allConditionsAreNegated) {
			C = Builder.CreateNot(C);
		}
		bitCnt = Builder.CreateIntrinsic(Intrinsic::ctlz, { C->getType() }, { C, /*isZeroPoisonous*/
		Builder.getFalse() });
	} else {
		if (allConditionsAreNegated) {
			C = Builder.CreateNot(C);
		}
		bitCnt = _createPopcntIntrinsic(Builder, C);
	}
	Worklist.addValue(bitCnt);
	Type* resTy = v0->getType();
	if (hasLimitCheck) {
		size_t TmpTyBitWidth = std::max(v0->getType()->getIntegerBitWidth() + 1,
				bitCnt->getType()->getIntegerBitWidth());
		resTy = IntegerType::get(v0->getContext(), TmpTyBitWidth);
	}
	bitCnt = Builder.CreateZExtOrTrunc(bitCnt, resTy);
	Worklist.addValue(bitCnt);
	auto _v0 = Builder.CreateZExtOrTrunc(v0, resTy);
	if (v0 != _v0) {
		Worklist.addValue(_v0);
	}
	bool hasNSW = true;
	bool hasNUW = true;
	for (const auto& lvl: addLevels) {
		hasNSW &= lvl.add->hasNoSignedWrap();
		hasNUW &= lvl.add->hasNoUnsignedWrap();
	}
	auto res = Builder.CreateAdd(_v0, bitCnt, "", hasNUW, hasNSW);
	Worklist.addValue(res);
	return res;
}
}
