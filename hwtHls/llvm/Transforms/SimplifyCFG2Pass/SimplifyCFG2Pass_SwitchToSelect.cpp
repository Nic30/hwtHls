#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchToSelect.h>

#include <algorithm>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFGUtils.h>

#define DEBUG_TYPE "simplifycfg2"
using namespace llvm;

namespace hwtHls {

bool trySwitchToSelect(llvm::SwitchInst *SI, IRBuilder<> &Builder, DomTreeUpdater &DTU) {
	// if every successor has only PHIs (and terminator) or there is one which post dominates others and begins with phis
	// this SwitchInst does not have true effect on control flow and it only drives PHIs which are selecting values
	// To simplify CFG it is beneficial to rewrite this pattern. Remove all tmp blocks and keep only parent of SI with
	// updated terminator.

	// find simple diamond CFG pattern
	BasicBlock *BBTop = SI->getParent();
	BasicBlock *BBBottom = nullptr;
	auto BBTopSuccessors = successors(BBTop);
	for (BasicBlock *Succ : BBTopSuccessors) {
		if (Succ->hasAddressTaken()) {
			return false;
		}
		if (Succ->getUniquePredecessor() == BBTop) {
			auto _SucSuc = Succ->getUniqueSuccessor();
			if (_SucSuc == nullptr)
				return false; // there must be unconditional jump to bottom block
			else if (BBBottom == nullptr) {
				BBBottom = _SucSuc;
				continue;
			} else if (BBBottom == _SucSuc) {
				continue;
			} else {
				return false; // successor is not BBBottom -> this is not recognized pattern
			}
		}
		bool allSucPredecessorsAreDominatedByBB = true;
		for (auto *SuccPred : predecessors(Succ)) {
			if (SuccPred != BBTop
					&& std::find(BBTopSuccessors.begin(), BBTopSuccessors.end(),
							SuccPred) == BBTopSuccessors.end()) {
				return false;
			} else if (BBBottom != nullptr && BBBottom != Succ) {
				return false; // this should not happen as there can be only one BBBottom
			}
		}
		if (allSucPredecessorsAreDominatedByBB) {
			BBBottom = Succ;
			continue;
		}
		return false;
	}
	assert(
			BBBottom
					&& "If there were successors there must be BBBottom or this function would already return");

	// check that every successor has compatible instructions
	for (BasicBlock *Succ : BBTopSuccessors) {
		if (Succ != BBBottom) {
			auto *Ter = Succ->getTerminator();
			// block must contain only br to BBBottom
			if (&*Succ->begin() != Ter) {
				return false;
			}
			auto *Br = dyn_cast<BranchInst>(Ter);
			if (!Br || Br->isConditional())
				return false;
		}
	}

	// rewrite PHIs in BBBottom as selects
	// insert at the end of BBTop because we merge BBTop to BBBottom

	// construct conditions first then selects for every PHI separately
	// so all select for some PHI are uninterrupted sequence of selects
	Value *Cond = SI->getCondition();
	auto *DefDst = SI->getDefaultDest();
	SmallVector<std::pair<BasicBlock*, Value*>> Conditions;

	if (DefDst) {
		Conditions.push_back( { DefDst == BBBottom ? BBTop: DefDst, nullptr });
	}
	for (auto C : SI->cases()) {
		auto * Succ = C.getCaseSuccessor();
		Conditions.push_back(
				{ Succ == BBBottom ? BBTop: Succ, Builder.CreateICmpEQ(Cond,
						C.getCaseValue()) });
	}
	for (PHINode &PHI : make_early_inc_range(BBBottom->phis())) {
		Value * V = nullptr;
		for (auto &Cond : Conditions) {
			auto _V = PHI.getIncomingValueForBlock(Cond.first);
			if (V == nullptr) {
				V = _V;
			} else {
				assert(Cond.second && "nullptr is used only for default value");
				V = Builder.CreateSelect(Cond.second, _V, V);
			}
		}
		if (!V->hasName() && PHI.hasName())
			V->setName(PHI.getName());
		PHI.replaceAllUsesWith(V);
		PHI.eraseFromParent();
	}
	SmallVector<BasicBlock*> _BBTopSuccessors(BBTopSuccessors);
	for (BasicBlock *Succ : _BBTopSuccessors) {
		DTU.applyUpdates(
					{ { DominatorTree::Delete, BBTop, Succ } });
	}
	SI->eraseFromParent();

	Builder.SetInsertPoint(BBTop, BBTop->end());
	Builder.CreateBr(BBBottom);
	DTU.applyUpdates(
				{ { DominatorTree::Insert, BBTop, BBBottom} });
	for (BasicBlock *Succ : _BBTopSuccessors) {
		if (Succ != BBBottom) {
			assert(Succ->use_empty());
			DeleteDeadBlock(Succ, &DTU); // :attention: can not directly erase because of iterator in caller
		}
	}
	if (BBTop != BBBottom) {
		MergeBlockIntoPredecessor(BBBottom, &DTU);
	}
	// :attention: DTU.flush() can not be applied there because it would break parent iteration if next block gets removed
	return true;
}

}
