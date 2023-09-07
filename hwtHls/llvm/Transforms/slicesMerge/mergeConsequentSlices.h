#pragma once
#include <llvm/IR/Instructions.h>
#include <hwtHls/llvm/Transforms/slicesMerge/utils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

namespace hwtHls {
#define DBG_VERIFY_AFTER_EVERY_MODIFICATION
std::pair<llvm::Value*, uint64_t> getSliceOffset(llvm::Value *op0);

bool mergeConsequentSlices(llvm::Instruction &I, DceWorklist::SliceDict &slices,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce);

using ParallelInstVec = std::vector<std::pair<bool, llvm::Instruction*>>;

void replaceMergedInstructions(const ParallelInstVec &parallelInstrOnSameVec,
		const CreateBitRangeGetFn &createSlice, llvm::IRBuilder<> &builder,
		llvm::Value *res, DceWorklist &dce, llvm::Instruction &I);

const llvm::Instruction* getInstructionClosesToBlockEnd(
		const ParallelInstVec &vec);
/*
 * Check if any of instructions from vector is used on the rage of instructions specified using begin, end
 * */
bool anyOfInstructionsIsUsed(const ParallelInstVec &vec,
		llvm::BasicBlock::const_iterator begin,
		llvm::BasicBlock::const_iterator end, bool checkAlsoEnd);

/*
 * :note: op0 and op1 does no have to be 1st and 2nd operand, they are just 2 operands which are checked
 * :param parallelInstrOnSameVec: lowest first vector of instructions on same slice which have slices of the same bit vector as operands
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
		DceWorklist::SliceDict &slices, const CreateBitRangeGetFn &createSlice,
		DceWorklist &dce, llvm::IRBuilder<> &builder,
		ParallelInstVec &parallelInstrOnSameVec, llvm::Instruction &I,
		std::function<bool(llvm::Instruction&)> extraCheck, bool commutative,
		size_t op0Index, size_t op1Index);
}

