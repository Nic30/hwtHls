#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsHoisting.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>
#include <llvm/Analysis/ValueTracking.h>

using namespace llvm;

namespace hwtHls {

bool hoistIntoDominatingBlock(Value &V, Instruction &insertPoint,
		const DominatorTree &DT) {
	if (auto *I = dyn_cast<Instruction>(&V)) {
		if (DT.dominates(I, &insertPoint)) {
			return true;
		}
		if (!isSafeToHoistInstr(I, SkipFlags::NONE, false))
			return false;

		for (auto &O : I->operands()) {
			if (!hoistIntoDominatingBlock(*O.get(), insertPoint, DT)) {
				return false;
			}
		}
		I->moveBefore(insertPoint.getIterator());
	}
	return true;
}
}
