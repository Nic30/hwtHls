#include "Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h"
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_unswitchCheapBlock.h>
#include <llvm-21/llvm/ADT/STLExtras.h>
#include <llvm/ADT/DenseSet.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Cloning.h>
#include <map>

using namespace llvm;

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_unswitchCheapBlock(llvm::DomTreeUpdater &DTU,
											  llvm::BasicBlock &BB0) {

	if (BB0.getSingleSuccessor() == nullptr)
		return false;

	SmallVector<BasicBlock *, 4> Preds(predecessors(&BB0));
	if (Preds.size() <= 1)
		return false; // Nothing to unswitch
	if (BB0.phis().empty()) {
		return false; // nothing to inline
	}
	// Ensure BB0 is phi-only (only phis + terminator)
	for (Instruction &I : BB0) {
		if (isa<PHINode>(&I))
			continue;
		if (I.isTerminator())
			break;
		// Non-phi, non-terminator instruction -> not phi-only
		return false;
	}

	BranchInst *BI = dyn_cast<BranchInst>(BB0.getTerminator());
	if (!BI || !BI->isUnconditional())
		return false;
	BasicBlock *S = BB0.getSingleSuccessor();
	if (S->getUniquePredecessor())
		return false; // this is the case where we should wait until BB0 and S
					  // are merged
	if (DTU.getDomTree().dominates(S, &BB0)) {
		return false; // prevent merging latch phis into header, because
					  // dedicated latch is considered beneficial
	}
	if (S->phis().empty()) {
		// all phis in this BB are useless and this will be
		// removed elsewhere
		return false;
	}

	Function *F = BB0.getParent();
	// dbgs() << "HwtHlsSimplifyCFGPass_unswitchCheapBlock before:\n"
	// 	   << *F << "\n";
	LLVMContext &Ctx = F->getContext();

	// Prepare a list of BB0's phis and their incoming values per predecessor
	SmallVector<PHINode *, 8> BB0Phis;
	for (Instruction &I : BB0) {
		if (auto *phi = dyn_cast<PHINode>(&I)) {
			if (phi->hasNUsesOrMore(1)) {
				BB0Phis.push_back(phi);
				for (auto *U : phi->users()) {
					if (auto userPhi = dyn_cast<PHINode>(U)) {
						if (userPhi->getParent() == S)
							continue;
					}
					llvm_unreachable("The inlined phi has some other uses "
									 "apart from successor phis");
				}
			}
			// else phi will be just errased as it has no use
		} else {
			break; // terminator reached
		}
	}

	// Create copies of BB0 for Preds, except for last
	std::map<BasicBlock *, BasicBlock *> BB0Copies;
	BB0Copies[Preds.back()] = Preds.back();
	for (auto *Pred : Preds) {
		if (BB0Copies.find(Pred) != BB0Copies.end()) {
			continue; // copy already created, (Preds may contain duplicit
					  // values
			// if the predecessor has terminator with multiple jumps to BB0)
		}
		// Create new block BB0_i using BasicBlock::Create
		BasicBlock *BB0Copy =
			BasicBlock::Create(Ctx, BB0.getName(), F, /*InsertBefore=*/&BB0);
		BB0Copies[Pred] = BB0Copy;
		// Clone the terminator from BB0 into BB0Copy
		BI->clone()->insertInto(BB0Copy, BB0Copy->end());
	}

	SmallVector<DominatorTree::UpdateType, 8> Updates;
	DenseSet<BasicBlock *> DTUSeenPred;
	// backup S phis original incoming values
	SmallVector<std::tuple<PHINode *, PHINode *, Value *>> phiMap;
	for (auto &phi : S->phis()) {
		auto v = phi.getIncomingValueForBlock(&BB0);
		if (auto vAsPhi = dyn_cast<PHINode>(v)) {
			if (vAsPhi->getParent() == &BB0) {
				phiMap.push_back({&phi, vAsPhi, vAsPhi});
				continue;
			}
		}
		phiMap.push_back({&phi, nullptr, v});
	}

	// Redirect new predecessors to branch to their corresponding
	// BB0Copy and sink phi operands from BB0 to S.
	for (auto *Pred : Preds) {
		if (Pred == Preds.back()) {
			if (!DTUSeenPred.insert(Pred).second)
				continue; // already updated
			// update uses of pred phis to an incoming value of BB0 phis for
			// Pred
			for (const auto &[phi, bb0phi, val] : phiMap) {
				if (bb0phi) {
					auto v = bb0phi->getIncomingValueForBlock(Pred);
					phi->setIncomingValueForBlock(&BB0, v);
				}
			}
		} else {
			BasicBlock *BB0Copy = BB0Copies[Pred];
			if (DTUSeenPred.insert(Pred).second) {
				Pred->getTerminator()->replaceSuccessorWith(&BB0, BB0Copy);
				Updates.push_back({DominatorTree::Delete, Pred, &BB0});
				Updates.push_back({DominatorTree::Insert, Pred, BB0Copy});
			}
			// add an incoming value of BB0 phis for Pred
			for (const auto &[phi, bb0phi, val] : phiMap) {
				Value *v = val;
				if (bb0phi) {
					v = bb0phi->getIncomingValueForBlock(Pred);
				}
				phi->addIncoming(v, BB0Copy);
			}
		}
	}
	// delete BB0 phis which uses in S should be all replaced, and there should
	// not be any other uses
	for (auto &phi : make_early_inc_range(BB0.phis())) {
		assert(!phi.hasNUsesOrMore(1));
		phi.eraseFromParent();
	}
	DTU.applyUpdates(Updates);
	// dbgs() << "HwtHlsSimplifyCFGPass_unswitchCheapBlock after:\n" << *F << "\n";

	sortPhiOperands(*S);
	return true;
}

}