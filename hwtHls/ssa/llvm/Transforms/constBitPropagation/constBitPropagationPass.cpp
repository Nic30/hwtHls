#include "constBitPropagationPass.h"
#include "utils.h"
#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <algorithm>
#include "constBitPartsAnalysis.h"
#include "bitPartsUseAnalysis.h"
#include "bitRewriter.h"

using namespace llvm;

namespace hwtHls {

static bool runCBP(Function &F) {
	ConstBitPartsAnalysisContext A;
	std::list<Instruction*> Worklist;
	bool didModify = false;
	// discover all value constraints
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			A.visitValue(&I);
			Worklist.push_back(&I);
		}
	}
	// transitively propagate constant bits until something changes (def -> use)
	while (!Worklist.empty()) {
		Instruction *I = Worklist.front();
		Worklist.pop_front();
		if (A.updateInstruction(I)) {
			for (auto user : I->users()) {
				if (auto *u = dyn_cast<Instruction>(user)) {
					if (A.constraints.find(u) != A.constraints.end()
							&& std::find(Worklist.begin(), Worklist.end(), u)
									== Worklist.end()) {
						Worklist.push_back(u);
					}
				}

			}
		}
	}

	// use the knowledge about bits constant values to resolve truly used bits (use -> def)
	BitPartsUseAnalysisContext AU(A.constraints);
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (dyn_cast<StoreInst>(&I)
					|| (dyn_cast<LoadInst>(&I)
							&& dyn_cast<LoadInst>(&I)->isVolatile())
					|| I.isTerminator() || I.isIndirectTerminator()
					|| I.isExceptionalTerminator() || dyn_cast<BranchInst>(&I)
					|| dyn_cast<SwitchInst>(&I)) {
				AU.updateUseMaskEntirelyUsed(&I);
			}
		}
	}
	BitPartsRewriter rew(A.constraints);
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			rew.rewriteIfRequired(&I);
		}
	}
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (auto *PHI = dyn_cast<PHINode>(&I)) {
				rew.rewritePHINodeArgsIfRequired(PHI);
			} else {
				break; // no more PHIs in this block
			}
		}
	}

	return didModify;
}

llvm::PreservedAnalyses ConstantBitPropagationPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	if (!runCBP(F)) {
		return PreservedAnalyses::all();
	}
	auto PA = PreservedAnalyses();
	PA.preserve<GlobalsAA>();
	PA.preserveSet<CFGAnalyses>();
	return PA;
}

}
