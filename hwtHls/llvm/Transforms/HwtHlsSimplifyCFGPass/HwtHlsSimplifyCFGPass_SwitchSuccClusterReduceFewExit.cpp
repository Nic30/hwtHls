#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/InstructionSimplify.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;

namespace hwtHls {

// construct an expression which is true if the DstBB is reached from SrcBB
// :note: ignoreCheckForDstAndHandle is useful when we start at the block which is dst or handle
//        but we want to probe successors
Value* constructBranchConditionToBB(llvm::IRBuilderBase &Builder, BasicBlock &SrcBB, BasicBlock &DstBB,
		BasicBlock &handleBB, bool ignoreCheckForDstAndHandle) {
	if (!ignoreCheckForDstAndHandle) {
		if (&SrcBB == &handleBB) {
			return Builder.getFalse();
		} else if (&SrcBB == &DstBB) {
			return Builder.getTrue();
		}
	}
	auto t = SrcBB.getTerminator();
	if (isa<UnreachableInst>(t)) {
		return Builder.getFalse();
	} else if (auto br = dyn_cast<BranchInst>(t)) {
		if (br->isConditional()) {
			auto t = constructBranchConditionToBB(Builder, *br->getSuccessor(0), DstBB, handleBB, false);
			auto f = constructBranchConditionToBB(Builder, *br->getSuccessor(1), DstBB, handleBB, false);
			return Builder.CreateSelect(br->getCondition(), t, f);
		} else {
			return constructBranchConditionToBB(Builder, *br->getSuccessor(0), DstBB, handleBB, false);
		}
	} else if (auto sw = dyn_cast<SwitchInst>(t)) {
		auto res = constructBranchConditionToBB(Builder, *sw->getDefaultDest(), DstBB, handleBB, false);
		for (auto& c: sw->cases()) {
			auto eq = Builder.CreateICmpEQ(sw->getCondition(), c.getCaseValue());
			auto cV = constructBranchConditionToBB(Builder, *c.getCaseSuccessor(), DstBB, handleBB, false);
			res = Builder.CreateSelect(eq, cV, res);
		}
		return res;
	} else {
		llvm_unreachable("NotImplemented: unsupported terminator");
	}
}

bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
		llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
		llvm::SwitchInst &SI, bool &exprChanged) {
	auto &BB = *SI.getParent();
	SetVector<BasicBlock*> switchSuccessos;
	for (BasicBlock *suc : successors(&BB)) {
		switchSuccessos.insert(suc);
	}
	SetVector<BasicBlock*> uniqueExits;
	for (BasicBlock *suc : switchSuccessos) {
		// is successor
		if (&*suc->begin() != suc->getTerminator()) {
			// does not contain only terminator, treat it as exit block
			if (!suc->phis().empty())
				return false;
			uniqueExits.insert(suc);
			if (uniqueExits.size() > 2)
				return false; // not the pattern of interest
		}

		auto t = suc->getTerminator();
		if (isa<UnreachableInst>(t)) {
			continue; // this block is irrelevant during search of exits as it can not be reached
		} else if (!isa<BranchInst>(t) && !isa<SwitchInst>(t)) {
			// unsupported terminator
			return false;
		}

		for (auto sucSuc : successors(suc)) {
			if (switchSuccessos.contains(sucSuc))
				continue; // skip because this is not exit but jump to another sibling block
			if (!sucSuc->phis().empty())
				return false;
			uniqueExits.insert(sucSuc);
			if (uniqueExits.size() > 2)
				return false; // not the pattern of interest
		}
	}
	// now we know that there are only <=2 unique blocks from the cluster of empty blocks after the SwitchInst
	Builder.SetInsertPoint(&SI);
	SmallVector<DominatorTree::UpdateType> updates;
	switch (uniqueExits.size()) {
	case 0: {
		for (BasicBlock *suc : switchSuccessos) {
			updates.push_back({DominatorTree::Delete, &BB, suc});
		}
		Builder.CreateUnreachable();
		break;
	}
	case 1: {
		auto newSuc = uniqueExits[0];
		for (BasicBlock *suc : switchSuccessos) {
			if (suc == newSuc)
				continue;
			updates.push_back({DominatorTree::Delete, &BB, suc});
		}
		if (!switchSuccessos.contains(newSuc)) {
			updates.push_back({DominatorTree::Insert, &BB, newSuc});
		}
		Builder.CreateBr(newSuc);
		break;
	}
	case 2: {
		for (BasicBlock *suc : switchSuccessos) {
			if (suc == uniqueExits[0] || suc == uniqueExits[1])
				continue;
			updates.push_back({DominatorTree::Delete, &BB, suc});
		}
		for (auto newSuc: uniqueExits) {
			if (!switchSuccessos.contains(newSuc)) {
				updates.push_back({DominatorTree::Insert, &BB, newSuc});
			}
		}

		exprChanged = true;
		auto c = constructBranchConditionToBB(Builder, BB, *uniqueExits[0], *uniqueExits[1], true);
		Builder.CreateCondBr(c, uniqueExits[0], uniqueExits[1]);
		break;
	}
	default:
		llvm_unreachable("All cases should be already handled");
	}
	SI.eraseFromParent();
	DTU.applyUpdates(updates);
	return true;
}

}
