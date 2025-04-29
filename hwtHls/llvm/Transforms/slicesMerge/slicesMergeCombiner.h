#pragma once

#define DEBUG_TYPE "SlicesMergePass"
#define DEBUG_TYPE_SHORT "SlicesMergePass"
// :attention: this expects DEBUG_TYPE and DEBUG_TYPE_SHORT to be defined
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerMixin.h>
#include <hwtHls/llvm/Transforms/slicesMerge/utils.h>
#include <hwtHls/llvm/Transforms/slicesMerge/parallelInstrVec.h>

// #define DBG_VERIFY_AFTER_EVERY_MODIFICATION

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <hwtHls/llvm/Transforms/utils/irConsistencyChecks.h>
#endif

namespace hwtHls {

class SlicesMergeCombiner: public HwtHlsInstCombinerMixin<SlicesMergeCombiner> {
public:
	// (bit vector, offset of slice) to slices of this vector beginning on this offset
	// :note: we do not need reverse dictionary, because instruction can be analyzed by OffsetWidthValue::fromValue and
	//        thus key for slice can be found
	using SliceDict = std::map<std::pair<llvm::Value*, uint64_t>, std::vector<llvm::Instruction*>>;

protected:
	SliceDict &slices; // temporary dictionary to speed up lookup of bit vector slices
public:
	SlicesMergeCombiner(BuilderTy &Builder, llvm::SimplifyQuery SQ,
			llvm::InstructionWorklist &Worklist, llvm::Function &F,
			llvm::Statistic &NumCombined, llvm::Statistic &NumConstProp,
			llvm::Statistic &NumDeadInst, const unsigned VisitCounter,
			SliceDict &slices) :
			HwtHlsInstCombinerMixin<SlicesMergeCombiner>(Builder, SQ, Worklist,
					F, NumCombined, NumConstProp, NumDeadInst, VisitCounter), slices(
					slices) {
	}
	void replaceInstUsesWithBefore(llvm::Instruction &I, llvm::Value *V,
			bool excludeAssumeUsers);
	// :param I: parent concatenation which trigered this merge
	bool mergeInstructionSequenceInPlace(
			llvm::SmallVector<OffsetWidthValue>::iterator mergableInstrSequenceBegin,
			llvm::SmallVector<OffsetWidthValue>::iterator &mergableInstrSequenceEnd,
			llvm::SmallVector<OffsetWidthValue> &members, llvm::CallInst *I);
	// perform 1 level of merge concatenation operands and referenced bitwise, select and phi instructions
	llvm::Instruction* rewriteConcat(llvm::CallInst *I, bool flatten = false);
	void eraseFromSlices(hwtHls::OffsetWidthValue sliceItem,
			llvm::Instruction &I);
	llvm::Instruction* eraseInstFromFunction(llvm::Instruction &I);
	void updateSlicesBeforeReplace(llvm::Instruction &I,
			llvm::Value &replacement);
	void assertSlicesConsistency() const;
	void verifyAfterUpdate(const char *scopeName, llvm::Instruction *I);
	llvm::Value* createSlice(llvm::Value *bitVec, size_t lowBitNo,
			size_t bitWidth);

	std::pair<bool, llvm::Value*> ConcatMemberVector_resolveAndReduce(
			ConcatMemberVector &cmv);
	/*
	 * :note: op0 and op1 does no have to be 1st and 2nd operand, they are just 2 operands which are checked
	 * :param parallelInstrOnSameVec: :see: ParallelInstVec
	 * 		When searching the same width of slices is prioritized but it is not required.
	 * :param extraCheck: function to filter found instructions
	 * */
	bool collectParallelInstructionOnSameVector(
			ParallelInstVec &parallelInstrOnSameVec, const llvm::Instruction &I,
			std::function<bool(llvm::Instruction&)> &extraCheck,
			bool commutative, llvm::Value *op0BitVec, uint64_t op0Offset,
			uint64_t op0Width, size_t op0Index, llvm::Value *op1BitVec,
			uint64_t op1Offset, uint64_t op1Width, size_t op1Index);

	/// Search another instructions of same type in same block which has consequent slice on same bit vector as reference instruction I
	/// search continues while there is compatible instruction of followng bits of probed bitvector
	///
	/// :param op0Suc: following slice on op0BitVec
	/// :param requireWidthToMatch: allow to match instruction which does not have same operand width as op0Suc
	/// :return: true if something was found
	bool collectParallelInstructionOnSameVectorFindFollowingInstr(
			ParallelInstVec &parallelInstrOnSameVec, const llvm::Instruction &I,
			std::function<bool(llvm::Instruction&)> &extraCheck,
			bool commutative, llvm::Value *op0BitVec, uint64_t op0Offset,
			uint64_t op0Width, size_t op0Index, llvm::Value *op1BitVec,
			uint64_t op1Offset, uint64_t op1Width, size_t op1Index,
			llvm::Instruction *op0Suc, bool requireWidthToMatch,
			SlicesMergeCombiner::SliceDict::iterator op1SucSlices);

	/*
	 * Remove all instructions between instructions in parallelInstrOnSameVec and create a concatenation
	 * of operands for selected operands
	 *
	 * :param widerOp0: output of this function, a wider operand generated from operands of parallel instructions
	 * :param widerOp1: :see: widerOp0
	 * */
	bool extractWiderOperandsFromParallelInstructions(
			ParallelInstVec &parallelInstrOnSameVec,
			llvm::BasicBlock &ParentBlock, size_t op0Index, size_t op1Index,
			llvm::Value *&widerOp0, llvm::Value *&widerOp1, bool &modified);

	/*
	 * :param paralle,
	 lInstrOnSameVec: :see: collectParallelInstructionOnSameVector
	 * :param extraCheck: predicate which must be satisfied for every parallel instruction
	 * :returns: tuple {modified, widerOp0, widerOp1}
	 * */
	std::tuple<bool, llvm::Value*, llvm::Value*> mergeConsequentSlicesExtractWiderOperads(
			ParallelInstVec &parallelInstrOnSameVec, llvm::Instruction &I,
			std::function<bool(llvm::Instruction&)> extraCheck,
			bool commutative, size_t op0Index, size_t op1Index);
	/*
	 * Merge instructions which are parallel to instruction I and are performed on a consequent slice of same bit vector
	 * */
	llvm::Instruction* mergeConsequentSlices(llvm::Instruction &I);
	void replaceMergedInstructions(
			const ParallelInstVec &parallelInstrOnSameVec, llvm::Value *res);

	llvm::Instruction* mergeConsequentSlicesBinOp(llvm::BinaryOperator &I);
	llvm::Instruction* mergeConsequentSlicesSelect(llvm::SelectInst &I);

	/*
	 * Rewrite chained PHIs as a phi of shifted values
	 *
	 * bb0:
	 *    %1 = phi i1 [ %2, %bb0 ], [ false, %bb1 ],  ...
	 *    %2 = phi i1 [ %3, %bb0 ], [ false, %bb1 ],  ...
	 *    %3 = phi i1 [ true, %bb0 ], [ false, %bb1 ],  ...
	 *    br i1 %3, label bb0, label bb1
	 * bb1:
	 *    br label bb0
	 *
	 * to
	 *
	 * bb0:
	 *  %"1,2,3" = phi i3 [%"bb0:1,2,3", %bb0], [i3 0, %bb1], ...
	 *  %1 = call i1 @hwtHls.bitRangeGet.i3.i64.i1.0(i3 %"1,2,3", i64 0)
	 *  %2 = call i1 @hwtHls.bitRangeGet.i3.i64.i1.1(i3 %"1,2,3", i64 1)
	 *  %3 = call i1 @hwtHls.bitRangeGet.i3.i64.i1.2(i3 %"1,2,3", i64 2)
	 *  %"shiftPhi<1,2,3>" = call i3 @hwtHls.bitConcat.i1.i1.i1(%1, %2, true)
	 *  br i1 %3, label bb0, label bb1
	 * bb1:
	 *    br label bb0
	 *
	 *
	 * collect PHIs which are chained
	 * * PHIs may implement multiple shifts and non shift operations at once
	 *   we must extract all PHIs which are chained together because
	 *   bitRangeGet and concat can not be inserted between PHIs
	 * */
	bool phiShiftPatternRewrite(llvm::BasicBlock &BB);

	llvm::Instruction* runOnInstr(llvm::Instruction &I);
};

}
