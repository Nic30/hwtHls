#include <hwtHls/llvm/Transforms/StripAssumePass.h>
#include <llvm/IR/IntrinsicInst.h>

using namespace llvm;

namespace hwtHls {
llvm::PreservedAnalyses StripAssumePass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	bool MadeIRChange = false;
	for (auto &BB : F) {
		for (auto &I : make_early_inc_range(BB)) {
			if (auto II = dyn_cast<IntrinsicInst>(&I)) {
				if (II->isAssumeLikeIntrinsic()) {
					II->eraseFromParent();
					MadeIRChange = true;
				}
			}
		}
	}
	// Mark all the analyses that instcombine updates as preserved.
	if (MadeIRChange)
		return PreservedAnalyses::all();

	// Mark all the analyses that instcombine updates as preserved.
	PreservedAnalyses PA;
	PA.preserveSet<CFGAnalyses>();
	return PA;
}
}
