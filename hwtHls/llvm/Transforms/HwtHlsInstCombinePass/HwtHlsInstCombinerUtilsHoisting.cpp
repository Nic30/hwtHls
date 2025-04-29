#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsHoisting.h>
#include <llvm/Analysis/ValueTracking.h>

using namespace llvm;
namespace hwtHls {

bool hoistIntoDominatingBlock(Value &V, Instruction &insertPoint,
		const DominatorTree &DT) {
	if (auto *I = dyn_cast<Instruction>(&V)) {
		if (DT.dominates(I, &insertPoint)) {
			return true;
		}
		if (I->mayWriteToMemory() || I->mayReadFromMemory()
				|| I->mayHaveSideEffects() || !isSafeToSpeculativelyExecute(I))
			return false;

		for (auto &O : I->operands()) {
			if (!hoistIntoDominatingBlock(*O.get(), insertPoint, DT)) {
				return false;
			}
		}
		I->moveBefore(&insertPoint);
	}
	return true;
}
}
