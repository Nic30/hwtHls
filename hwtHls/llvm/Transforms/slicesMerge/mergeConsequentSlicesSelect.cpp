#include <hwtHls/llvm/Transforms/slicesMerge/slicesMergeCombiner.h>

#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>


#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <hwtHls/llvm/Transforms/utils/irConsistencyChecks.h>
#endif

using namespace llvm;

namespace hwtHls {

bool SlicesMergeCombiner::mergeConsequentSlicesSelect(SelectInst &I) {
	// translate operands then build a new operand with new operands if required
	Value *opCond = I.getCondition();
	Value *widerOp0;
	Value *widerOp1;
	Builder.SetInsertPoint(&I);
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
	bool modified;
	std::tie(modified, widerOp0, widerOp1) =
			mergeConsequentSlicesExtractWiderOperads(parallelInstrOnSameVec, I,
					predicateCondEq, false, 1, 2);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	verifyUsesList(F);
#endif
	if (widerOp0 && widerOp1) {
		assert(widerOp0->getType() == widerOp1->getType());
		auto res = Builder.CreateSelect(opCond, widerOp0, widerOp1);
		assert(
				parallelInstrOnSameVec.size()
						&& parallelInstrOnSameVec[0].I == &I);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		verifyUsesList(F);
#endif
		replaceMergedInstructions(parallelInstrOnSameVec, res);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		verifyUsesList(F);
#endif

		return true; // return non null to mark that the instruction was replaced
	}
	return false;
}
}
