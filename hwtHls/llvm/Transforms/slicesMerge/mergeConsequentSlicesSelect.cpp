#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlicesSelect.h>

#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/concatMemberVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

bool mergeConsequentSlicesSelect(SelectInst &I, DceWorklist::SliceDict &slices,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce) {
	// translate operands then build a new operand with new operands if required
	Value *opCond = I.getCondition();
	bool modified;
	Value *widerOp0;
	Value *widerOp1;
	IRBuilder<> builder(&I);
	ParallelInstVec parallelInstrOnSameVec;
	const auto predicateCondEq = [opCond](Instruction &I) {
		if (auto *_I = dyn_cast<SelectInst>(&I)) {
			return _I->getCondition() == opCond;
		}
		return false;
	};
	std::tie(modified, widerOp0, widerOp1) =
			mergeConsequentSlicesExtractWiderOperads(slices, createSlice, dce,
					builder, parallelInstrOnSameVec, I, predicateCondEq, false,
					1, 2);
	if (widerOp0 && widerOp1) {
		modified = true;
		assert(widerOp0->getType() == widerOp1->getType());
		auto res = builder.CreateSelect(opCond, widerOp0, widerOp1);
		replaceMergedInstructions(parallelInstrOnSameVec, createSlice, builder,
				res, dce, I);
	}
	return modified;
}
}
