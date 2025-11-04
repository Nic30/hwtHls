#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_hoistHoistableAssumes.h>

#include <llvm/IR/IntrinsicInst.h>
#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>

using namespace llvm;

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_hoistHoistableAssumes(llvm::BasicBlock &BB) {
	auto pred = BB.getUniquePredecessor();
	if (!pred)
		return false;
	auto predTerm = pred->getTerminator();
	bool exprChanged = false;
	for (auto &I : llvm::make_early_inc_range(BB)) {
		auto a = dyn_cast<AssumeInst>(&I);
		if (!a)
			break;
		if (hasMetadataSideeffectAllowHoist(I)) {
			a->moveBefore(predTerm->getIterator());
			exprChanged = true;
		}
	}
	return exprChanged;
}

}
