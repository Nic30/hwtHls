#include <hwtHls/llvm/Transforms/LoopAddLatchPass.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

using namespace llvm;

namespace hwtHls {

llvm::PreservedAnalyses LoopAddLatchPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	bool Changed = false;
	for (BasicBlock &BB : F) {
		for (BasicBlock * suc: successors(&BB)) {
			if (&BB == suc) {
				auto * origTI = suc->getTerminator();
				auto * loopMD = origTI->getMetadata(LLVMContext::MD_loop);
				auto *latchBB = SplitEdge(&BB, &BB);
				if (loopMD) {
					latchBB->getTerminator()->setMetadata(LLVMContext::MD_loop, loopMD);
					origTI->setMetadata(LLVMContext::MD_loop, nullptr);
				}
				Changed = true;
			}
		}
	}

	if (Changed) {
		PreservedAnalyses PA;
		return PA;
	} else {
		return PreservedAnalyses::all();
	}

}

}
