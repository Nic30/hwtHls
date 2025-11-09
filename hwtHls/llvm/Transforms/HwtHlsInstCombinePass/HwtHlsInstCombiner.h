#pragma once

#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerDebug.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePassOptions.h>

#include <map>

#include <llvm/ADT/PostOrderIterator.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/TargetFolder.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/Analysis/SimplifyQuery.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Metadata.h>
#include <llvm/IR/Dominators.h>

#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>

// :attention: this expects DEBUG_TYPE and DEBUG_TYPE_SHORT to be defined
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerMixin.h>

namespace hwtHls {

class ConcatMemberVector;

class HwtHlsInstCombiner: public HwtHlsInstCombinerMixin<HwtHlsInstCombiner> {
public:
	HwtHlsInstCombinePassOptions Options;

	bool StreamPropsAnalyzed;
	llvm::SmallDenseMap<llvm::Argument*, StreamChannelFormatInfo, 8> StreamProps;
	llvm::SmallDenseSet<llvm::LoadInst*, 8> streamLoadsWithEoFThreadingApplied;

	struct BitcountOpType {
		bool mayBeCtlz; // if each bit is 0 only if previous was 0 (count leading zeros)
		bool mayBeCtlo; // if each bit is 1 only if previous was 1 (count leading ones)
		//bool mayBeCttz; // if each bit is 0 only if next is 0 (count trailing zeros)
		//bool mayBeCtto; // if each bit is 1 only if next is 1 (count trailing ones)
	};

	HwtHlsInstCombiner(BuilderTy &Builder, llvm::SimplifyQuery SQ,
			llvm::InstructionWorklist &Worklist,
			HwtHlsInstCombinePassOptions optConfig, llvm::Function &F);

	// :note: use replaceInstUsesWith to replace instructions
	llvm::Instruction* runOnInstr(llvm::Instruction &I);
	bool runOptimizationsAfterWorklistEmpty();

	// HwtHlsInstComibnerFp.cpp
	llvm::Instruction* tryReduceFDivByPow2_to_HwtHlsFpSh(
			llvm::BinaryOperator &I);
	llvm::Instruction* tryReduceFMulByPow2_to_HwtHlsFpSh(
			llvm::BinaryOperator &I);
	llvm::Instruction* _tryReduceFMulDivByPow2_to_HwtHlsFpSh(
			llvm::BinaryOperator &I, llvm::Value *x, llvm::Value *sh,
			bool isMul);
	llvm::Instruction* _tryReduceFRemByPow2_to_HwtHlsFpCast(llvm::CallInst &I);
	llvm::Instruction* _tryReduceFModByPow2_to_HwtHlsFpCast(llvm::CallInst &I);
	llvm::Instruction* _tryReduceCastHFloatTmpToHFloatTmpRaw(llvm::CallInst &I);

	// reduce casts which are no longer required after values have been specialized
	llvm::Instruction* _tryReduceCastHFloatTmpRaw(llvm::CallInst &I);

	// HwtHlsInstComibnerFpCmp.cpp
	llvm::Instruction* _tryReduceHwtHlsFCmp(llvm::CallInst &I);

	// HwtHlsInstCombinerFpSpecialized.cpp
	llvm::Instruction* _tryReduceHwtHlsFpFAdd(llvm::CallInst &I);
	llvm::Instruction* tryReduceHwtHlsFpSub_to_addNeg(llvm::CallInst & I /*fsub*/);

	// HwtHlsInstCombinerCmp.cpp
	llvm::Value* _rewriteCmpConstOnAddSubOpConst(llvm::BinaryOperator &BI,
			llvm::CmpInst &ICMPI, const llvm::APInt &cmpRhsVal);
	///* The main purpose of this opt. is to remove add/sub trees with icmp on each level and replace them with icmp
	// * of input data and single adder with select for const rhs
	// * */
	llvm::Instruction* tryReduceCmpInst_hoistConstICmpOnConstArithAndSel(
			llvm::CmpInst &I);
	llvm::Instruction* tryReduceCmpInst_cmpOnMaskToBitGet(llvm::CmpInst &I);
	llvm::Instruction* tryReduceSelectInst_unNegate(llvm::SelectInst &SI);
	llvm::Instruction* _tryReduceSelectInst_toAndOr_SelectOfCompares(
			llvm::SelectInst &SI);
	llvm::Instruction* tryReduceSelectInst_toAndOr(llvm::SelectInst &SI);
	llvm::Instruction* tryReduceSelectInst_extractCommonFromOperands(
			llvm::SelectInst &SI);
	llvm::Instruction* tryReduceSelectInst_selectOfImpliedBitsOrZero_toConcat(
			llvm::SelectInst &SI);
	struct BitCountExprFragment {
		llvm::BinaryOperator *add;
		llvm::SelectInst *select;
		bool selectConditionNegated;

		BitCountExprFragment(llvm::BinaryOperator *add,
				llvm::SelectInst *select, bool selectConditionNegated) :
				add(add), select(select), selectConditionNegated(
						selectConditionNegated) {
		}
		std::pair<llvm::Value*, bool> getCondition() {
			return {select->getCondition(), selectConditionNegated};
		}
		llvm::Value* getInputVal() {
			return add->getOperand(0);
		}
		llvm::SelectInst* getExitVal() {
			return select;
		}
	};
	// search x_n+1 = c ? x_n + 1 : x_n pattern
	std::optional<BitCountExprFragment> _searchChainOfOptionalPlus1AddersDefUse_matchOne(
			llvm::SelectInst *&SI, llvm::Value *&v0,
			bool &allConditionsAreNegated) const;
	// search x_n+1 = c ? x_n + 1 : x_n pattern in def->use direction
	bool _searchChainOfOptionalPlus1AddersDefUse(
			llvm::SmallVector<BitCountExprFragment> &adderLevels,
			llvm::SelectInst &SI, bool &allConditionsAreNegated);
	bool _sinkAfterInSameBlockRecursively(llvm::Instruction &IToMove,
			llvm::Instruction &I);
	void _rewriteAllUsesOfIntermediateValuesInBitcount_collectInternallyUsedInstr(
			llvm::Instruction &firstInstr, llvm::BasicBlock &BB,
			std::set<llvm::Instruction*> &instrUsedInternally, llvm::Value &V);
	/*
	 * :attention: Builder is expected to have insertion point directly after last instruction implementing
	 * 	ctpop final value. Because rewritten instructions will use it.
	 * */
	void _rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_externalUserOfSelect(
			llvm::MutableArrayRef<BitCountExprFragment> adderLevels,
			llvm::MutableArrayRef<llvm::Value*> realCondtions,
			std::optional<std::pair<llvm::ICmpInst::Predicate, llvm::Value*>> limit,
			size_t lvlIndex, llvm::Value *topMostBitcountRes,
			bool allConditionsAreNegated, const ConcatMemberVector &srcOpBits,
			const BitcountOpType bitCntOpTy, llvm::Value *&bitcntForThisPart,
			const llvm::Use *U);
	// :param: hasInvertedInput if true the meaning of input to bitcount is inverted (e.g. ctlz now counting ones instead of zeros (is ctlo))
	enum BITCOUNT_REWIRTE_RES {
		COMPLETLY_REWRITTEN, // the value of top select was already replaced and no rewrite is required
		NO_INTERMEDIATE_USE, // there was no use of any intermediate value and value of top select was not updated
		NOT_REWRITABLE, // some intermediate user can not be rewritten
	};
	BITCOUNT_REWIRTE_RES _rewriteAllUsesOfIntermediateValuesInBitcount(
			llvm::Intrinsic::IndependentIntrinsics intrinsicOpc,
			bool hasInvertedInput,
			llvm::SmallVector<BitCountExprFragment> &adderLevels,
			bool allConditionsAreNegated, const ConcatMemberVector &srcOpBits,
			const BitcountOpType bitCntOpTy);
	std::optional<std::pair<llvm::ICmpInst::Predicate, llvm::Value*>> _findLimitInAndFromForBitcount(
			llvm::SmallVector<BitCountExprFragment> &adderLevels,
			llvm::SmallVector<llvm::Value*> &realConditions);
	/*
	 * :attention: this only creates replacement instruction but it does not perform actual replace
	 * */
	llvm::Value* _rewriteAllUsesOfIntermediateValuesInBitcount_CTLO_applyLimit(
			llvm::MutableArrayRef<BitCountExprFragment> adderLevels,
			llvm::MutableArrayRef<llvm::Value*> realCondtions,
			std::optional<std::pair<llvm::ICmpInst::Predicate, llvm::Value*>> limit,
			llvm::Value *currentBitcountRes);
	/*
	 * Convert conditions of selects and optional limit value to a bitcount instruction
	 * :attention: this only creates replacement instruction but it does not perform actual replace
	 * :param bitcountRes: v0 + bitcount
	 * */
	llvm::Value* _rewriteAllUsesOfIntermediateValuesInBitcount_CTPOP_applyLimit(
			llvm::MutableArrayRef<BitCountExprFragment> adderLevels,
			llvm::MutableArrayRef<llvm::Value*> realConditions,
			std::optional<std::pair<llvm::ICmpInst::Predicate, llvm::Value*>> limit,
			llvm::Value *bitcountRes);
	/**
	 * construct the limit check expression at the top of bitcount optional adder chain,
	 * :note: the purpose of this expression is to replace limit check which were
	 *  originally operating on intermediate values inside of bitcount expression
	 * :note: this is suitable for ctlo, ctto, ctpop which are incrementing value if bit is 1
	 * :param bitcountRes: v0 + bitcount
	 * */
	llvm::Value* _constructLimitExprForBitcnt1_NE_ULT_ULE(
			std::pair<llvm::ICmpInst::Predicate, llvm::Value*> limit,
			llvm::Value *v0, llvm::Value *bitcountRes);
	/*
	 * :attention: Builder is expected to have insertion point directly after last instruction which implements
	 *   the limit check, this information is used to avoid replacing top of adder chain in limit check implementing
	 *   instructions.
	 * :note: also immediately erases trivially dead instructions referenced from original conditions
	 * 	to make check of intermediate values possible
	 * */
	void _replaceTopOfAdderChainWithNewlyAddedLimitCheck(
			llvm::MutableArrayRef<BitCountExprFragment> adderLevels,
			llvm::MutableArrayRef<llvm::Value*> realConditions,
			llvm::Value *replacement);

	BitcountOpType _getBitcountOpType(
			llvm::SmallVector<BitCountExprFragment> &addLevels,
			bool allConditionsAreNegated);

	/*
	 * :param addLevels: levels of adder-select for this bitcount instruction
	 * :param realConditions: bits of bitcount src operand
	 * :param srcOpBits: vector to inject some prefix/suffix bits in src operand
	 * 		to implement merging with other bitcount during creation of his from realConditions
	 * */
	llvm::Value* _createBitcountConditionConcatenation(
			llvm::MutableArrayRef<BitCountExprFragment> addLevels,
			llvm::MutableArrayRef<llvm::Value*> realConditions,
			bool allConditionsAreNegated, ConcatMemberVector srcOpBits);
	bool _isTopOfBitCountSelectTree(llvm::SelectInst &SI);
	llvm::Instruction* tryReduceSelectInst_deepAdderChainToBitCounts(
			llvm::SelectInst &SI, size_t extractionTreshold);
	llvm::Value* _createBitcountFromAdderSelectTreeConditions(
			llvm::MutableArrayRef<BitCountExprFragment> addLevels,
			llvm::MutableArrayRef<llvm::Value*> conditions,
			bool allConditionsAreNegated, const ConcatMemberVector &srcOpBits,
			llvm::Value *v0, const BitcountOpType bitCntOpTy,
			bool hasLimitCheck);
	static llvm::CallInst* _createPopcntIntrinsic(
			llvm::IRBuilderBase &IRBuilder, llvm::Value *Val);
	llvm::Instruction* tryReduceIntrinsicInst_ctpopReduceBitwidth(
			llvm::IntrinsicInst &I);
	llvm::Instruction* tryReduceIntrinsicInst_ctpopToCtlz(
			llvm::IntrinsicInst &I);

	bool pruneInvertedCmpDuplicatesInBlock(llvm::BasicBlock &BB);
	bool pruneInvertedCmpDuplicatesInBlocks(llvm::Function &F);

	llvm::Instruction* tryReduceIntrinsicInst_fshlConstSh(llvm::IntrinsicInst &I);
	llvm::Instruction* tryReduceIntrinsicInst_fshrConstSh(llvm::IntrinsicInst &I);

	llvm::Instruction* tryReduceMergableFunctionInSequence(llvm::CallInst &I);
	//llvm::Instruction* _tryReduceMergableFunctionInSelect_optinalToMasked(
	//		llvm::SelectInst &SI, llvm::CallInst *T,
	//		std::optional<llvm::CallInst*> _F);

	struct MergableFunctionChainItem {
		llvm::CallInst *mergableFnCall;
		llvm::Value *enCondition; // if enConditionNegated==false and enCondition==true the mergableFnCall is executed
		bool enConditionNegated;
		MergableFunctionChainItem() :
				mergableFnCall(nullptr), enCondition(nullptr), enConditionNegated(
						false) {
		}
	};

	// result[0] is a top of the tree
	bool _tryReduceMergableFunctionInSelect_detect(llvm::SelectInst &topSI,
			llvm::SmallVector<MergableFunctionChainItem> &result,
			llvm::Value *&stateIn);

	// if this is applied to a sequence of (fn, select)+ it reduces only the first select
	llvm::Instruction* tryReduceMergableFunctionInSelect(llvm::SelectInst &SI);

	llvm::Instruction* tryReduceAndAndWithCommon(llvm::BinaryOperator &I);
	llvm::Instruction* tryReduceOrOnBits_toNE(llvm::BinaryOperator &I);

	llvm::Instruction* tryReduceAndOfAssumedPredicates(llvm::BinaryOperator &I);
	llvm::Instruction* tryReduceOrOfAssumedPredicates(llvm::BinaryOperator &I);
	llvm::Instruction* tryReduceAndWithEq_to_widerEq(llvm::BinaryOperator &I);

	llvm::Instruction* tryReduceZExt_onTurncUMin(llvm::ZExtInst &I);
	llvm::Instruction* tryReduceICmp_onTurncUMin(llvm::ICmpInst &I);
	llvm::Instruction* tryReduceUMinNe_to_ULT(llvm::CmpInst &I);
	// optionally create new assumptions about value range if it is more specific than current assumptions
	void _setAssumeRangeIfisBetterRange(llvm::Value *V,
			const llvm::ConstantRange &newAssumedRange, bool UseInstrInfo,
			llvm::Instruction *CtxI);

	// llvm::computeConstantRange does not support ZExt and Trunc
	//  to compensate for that this function pre-computes MD_Range for them
	//  so llvm::computeConstantRange can analyze expressions containing them
	void _precomputeRangeAssumptionForZExtAndTrunc(llvm::Value *V,
			bool ForSigned, bool UseInstrInfo, size_t Depth);
	// this optimization is beneficial when there is an induction variable
	// which has some limit value and this value is a rhs of this cmp C,
	// in this case it it better to rewrite to x < C or X > C
	// because it defines only 1 range where the result is 1 (x < C) instead of 2 for NE (x < C || C < x)
	// This later enables us to infer subsumed conditions and implications.
	llvm::Instruction* tryReduceICmpNEonPHI_to_UGT_or_ULT(llvm::ICmpInst &I);

	/*
	 * This function is called once the speculated value for instruction was resolved
	 * to create speculated versions of users which should be speculated and to create
	 * SelectInst which select between speculated and not speculated variant for users
	 * which are not speculable.
	 *
	 * :param speculationCondition: a condition for which we creating the speculative version of this expression
	 * :param speculationConditionVal: a value of speculationCondition for this expression
	 * :param I: speculated expression
	 * :param ISpeculated: speculated value for I
	 * :param speculatedExprMap: map which maps original non-speculated value to a new value with speculation applied
	 * :param speculatedExprExitMap: map of SelectInst and alike instruction on boundary of speculated subgraph
	 * :param exprUsedByAssumes: instructions which are driving llvm.assume in specified depth
	 * :note: exprUsedByAssumes is required because without it
	 * 	the assumes are reduced to true or are broken as they are simplified
	 * 	with values assumed from eof/not-eof
	 * */
	void _duplicateExprForEoFandNotEoFVariant(
			const std::set<llvm::Instruction*> &speculableExprs,
			llvm::Value *speculationCondition, bool speculationConditionVal,
			llvm::Instruction *I, llvm::Value *ISpeculated,
			std::map<llvm::Value*, llvm::Value*> &speculatedExprMap,
			std::map<llvm::Value*, llvm::Value*> &speculatedExprExitMap,
			std::set<llvm::Instruction*> &exprUsedByAssumes);
	bool tryImplementStreamReadEoFThreading(llvm::BranchInst &I);
};

}
