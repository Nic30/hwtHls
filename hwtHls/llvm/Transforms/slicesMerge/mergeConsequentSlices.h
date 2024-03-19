#pragma once

#include <llvm/IR/Instructions.h>
#include <hwtHls/llvm/Transforms/slicesMerge/utils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/slicesMerge/parallelInstrVec.h>

// #define DBG_VERIFY_AFTER_EVERY_MODIFICATION

namespace hwtHls {

bool IsBitwiseOperator(const llvm::BinaryOperator &I);
bool IsBitwiseInstruction(const llvm::Instruction &I);

std::pair<llvm::Value*, uint64_t> getSliceOffset(llvm::Value *op0);

bool mergeConsequentSlices(llvm::Instruction &I,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce);


void replaceMergedInstructions(const ParallelInstVec &parallelInstrOnSameVec,
		const CreateBitRangeGetFn &createSlice, llvm::IRBuilder<> &builder,
		llvm::Value *res, DceWorklist &dce);

/*
 * :note: op0 and op1 does no have to be 1st and 2nd operand, they are just 2 operands which are checked
 * :param parallelInstrOnSameVec: :see: ParallelInstVec
 * 		When searching the same width of slices is prioritized but it is not required.
 * :param extraCheck: function to filter found instructions
 * */
bool collectParallelInstructionOnSameVector(DceWorklist::SliceDict &slices,
		ParallelInstVec &parallelInstrOnSameVec, const llvm::Instruction &I,
		std::function<bool(llvm::Instruction&)> &extraCheck, bool commutative,
		llvm::Value *op0BitVec, uint64_t op0Offset, uint64_t op0Width,
		size_t op0Index, llvm::Value *op1BitVec, uint64_t op1Offset,
		uint64_t op1Width, size_t op1Index);

/*
 * :param parallelInstrOnSameVec: :see: collectParallelInstructionOnSameVector
 * :param extraCheck: predicate which must be satisfied for every parallel instruction
 * :returns: tuple {modified, widerOp0, widerOp1}
 * */
std::tuple<bool, llvm::Value*, llvm::Value*> mergeConsequentSlicesExtractWiderOperads(
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		llvm::IRBuilder<> &builder, ParallelInstVec &parallelInstrOnSameVec,
		llvm::Instruction &I,
		std::function<bool(llvm::Instruction&)> extraCheck, bool commutative,
		size_t op0Index, size_t op1Index);
/*
 * Remove all instructions between instructions in parallelInstrOnSameVec and create a concatenation
 * of operands for selected operands
 *
 * :param widerOp0: output of this function, a wider operand generated from operands of parallel instructions
 * :param widerOp1: :see: widerOp0
 * */
bool extractWiderOperandsFromParallelInstructions(
		ParallelInstVec &parallelInstrOnSameVec, DceWorklist &dce,
		const CreateBitRangeGetFn &createSlice, llvm::BasicBlock &ParentBlock,
		size_t op0Index, size_t op1Index, llvm::IRBuilder<> &builder,
		llvm::Value *&widerOp0, llvm::Value *&widerOp1, bool &modified);

}

