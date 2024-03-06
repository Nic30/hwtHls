#include <hwtHls/llvm/Transforms/LoopAddLatchPass.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

using namespace llvm;

namespace hwtHls {

llvm::PreservedAnalyses LoopAddLatchPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	bool Changed = false;
	for (BasicBlock &BB : F) {
		for (BasicBlock *suc : successors(&BB)) {
			if (&BB == suc) {
				auto *origTI = suc->getTerminator();
				SmallVector<std::pair<unsigned, MDNode*>> MDs;
				origTI->getAllMetadata(MDs);
				auto *latchBB = SplitEdge(&BB, &BB);
				auto *newTerm = latchBB->getTerminator();
				if (origTI != newTerm && MDs.size()) {
					for (const auto& [KindID, Node] : MDs) {
						newTerm->setMetadata(KindID, Node);
					}
					for (const auto& [KindID, Node] : MDs) {
						origTI->setMetadata(KindID, nullptr);
					}
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
