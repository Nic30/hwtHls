#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlicesSelect.h>

#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

#include <hwtHls/llvm/Transforms/utils/irConsistencyChecks.h>

using namespace llvm;

namespace hwtHls {

bool mergeConsequentSlicesSelect(SelectInst &I,
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
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	auto &F = *I.getParent()->getParent();
#endif
	std::tie(modified, widerOp0, widerOp1) =
			mergeConsequentSlicesExtractWiderOperads(createSlice, dce, builder,
					parallelInstrOnSameVec, I, predicateCondEq, false, 1, 2);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	verifyUsesList(F);
#endif
	if (widerOp0 && widerOp1) {
		modified = true;
		assert(widerOp0->getType() == widerOp1->getType());
		auto res = builder.CreateSelect(opCond, widerOp0, widerOp1);
		assert(
				parallelInstrOnSameVec.size()
						&& parallelInstrOnSameVec[0].I == &I);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		verifyUsesList(F);
#endif
		replaceMergedInstructions(parallelInstrOnSameVec, createSlice, builder,
				res, dce);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		verifyUsesList(F);
#endif
	}
	return modified;
}
}
