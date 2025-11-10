#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/InstructionSimplify.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;

namespace hwtHls {

// construct an expression which is true if the DstBB is reached from SrcBB
// :note: ignoreCheckForDstAndHandle is useful when we start at the block which is dst or handle
//        but we want to probe successors
// :param handleBBs: blocks where pred->suc search for DstBB should stop and return false
Value* constructBranchConditionToBB(llvm::IRBuilderBase &Builder,
		BasicBlock &SrcBB, BasicBlock &DstBB,
		const SetVector<BasicBlock*> &handleBBs,
		bool ignoreCheckForDstAndHandle) {
	if (!ignoreCheckForDstAndHandle) {
		if (&SrcBB == &DstBB) {
			return Builder.getTrue();
		} else if (handleBBs.contains(&SrcBB)) {
			return Builder.getFalse();
		}
	}
	auto t = SrcBB.getTerminator();
	if (isa<UnreachableInst>(t)) {
		return Builder.getFalse();
	} else if (auto br = dyn_cast<BranchInst>(t)) {
		if (br->isConditional()) {
			auto t = constructBranchConditionToBB(Builder, *br->getSuccessor(0),
					DstBB, handleBBs, false);
			auto f = constructBranchConditionToBB(Builder, *br->getSuccessor(1),
					DstBB, handleBBs, false);
			return Builder.CreateSelect(br->getCondition(), t, f);
		} else {
			return constructBranchConditionToBB(Builder, *br->getSuccessor(0),
					DstBB, handleBBs, false);
		}
	} else if (auto sw = dyn_cast<SwitchInst>(t)) {
		auto res = constructBranchConditionToBB(Builder, *sw->getDefaultDest(),
				DstBB, handleBBs, false);
		for (auto &c : sw->cases()) {
			auto eq = Builder.CreateICmpEQ(sw->getCondition(),
					c.getCaseValue());
			auto cV = constructBranchConditionToBB(Builder,
					*c.getCaseSuccessor(), DstBB, handleBBs, false);
			res = Builder.CreateSelect(eq, cV, res);
		}
		return res;
	} else {
		llvm_unreachable("NotImplemented: unsupported terminator");
	}
}

Value* constructBranchConditionToBBDirect(llvm::IRBuilderBase &Builder,
		BasicBlock &SrcBB, BasicBlock &DstBB) {
	auto t = SrcBB.getTerminator();
	if (auto br = dyn_cast<BranchInst>(t)) {
		if (br->isConditional()) {
			auto C = br->getCondition();
			if (br->getSuccessor(0) == &DstBB) {
				if (br->getSuccessor(1) == &DstBB)
					return Builder.getTrue();
				else
					return C;
			} else {
				assert(br->getSuccessor(1) == &DstBB);
				return Builder.CreateNot(C);
			}
		} else {
			assert(br->getSuccessor(0) == &DstBB);
			return Builder.getTrue();
		}
	} else if (auto sw = dyn_cast<SwitchInst>(t)) {
		SmallVector<Value*> otherBrConditions;
		SmallVector<Value*> brSuccessConditions;
		bool dstIsSwDefault = sw->getDefaultDest() == &DstBB;

		for (auto &c : sw->cases()) {
			bool isCaseForDstBB = c.getCaseSuccessor() == &DstBB;
			if (isCaseForDstBB || dstIsSwDefault) {
				auto eq = Builder.CreateICmpEQ(sw->getCondition(),
						c.getCaseValue());
				if (isCaseForDstBB) {
					brSuccessConditions.push_back(eq);
				} else {
					otherBrConditions.push_back(eq);
				}
			}
		}
		Value *sucBr;
		if (brSuccessConditions.empty()) {
			sucBr = Builder.getFalse();
		} else {
			sucBr = Builder.CreateOr(brSuccessConditions);
		}
		Value *res;
		if (dstIsSwDefault) {
			if (otherBrConditions.empty()) {
				res = Builder.getTrue();
			} else {
				Value *brDefault = Builder.CreateNot(
						Builder.CreateOr(otherBrConditions));
				res = Builder.CreateOr(sucBr, brDefault);
			}
		} else {
			res = sucBr;
		}
		return res;
	} else {
		llvm_unreachable("NotImplemented: unsupported terminator");
	}
}

// transform PHIs operands to select,
// but only for blocks in switchSuccessors which are going to be removed
// :note: if exitBB has predecessors which are not in switchSuccessors then
//        it will retain phi, but incoming values from switchSuccessors will be stripped
//        and new incoming value from BBWithSwitch will be added together with isJmpFromSw phi
// :note: this should be called before predecessors/successors are updated
void lowerPhisToSelect(llvm::IRBuilderBase &Builder, BasicBlock &BBWithSwitch,
		const SetVector<BasicBlock*> &switchSuccessors,
		const SetVector<BasicBlock*> &exitBBs, BasicBlock &exitBB) {
	auto IP = Builder.saveIP();
	//auto exitBBAfterPhis = exitBB.getFirstNonPHIIt();
	SetVector<BasicBlock*> predsWhichWillBePreserved;
	predsWhichWillBePreserved.insert(&BBWithSwitch);
	for (BasicBlock *pred : predecessors(&exitBB)) {
		if (!switchSuccessors.contains(pred) || exitBBs.contains(pred)) {
			predsWhichWillBePreserved.insert(pred);
		}
	}

	//PHINode *useValFromPhi = nullptr;
	//if (predsWhichWillBePreserved.size() > 1) {
	//	IRBuilderBase::InsertPointGuard g(Builder);
	//	Builder.SetInsertPoint(&exitBB, exitBB.begin());
	//	useValFromPhi = Builder.CreatePHI(Builder.getInt1Ty(),
	//			pred_size(&exitBB), "fewExitSw.useValFromPhi");
	//	for (BasicBlock *pred : predecessors(&exitBB)) {
	//		if (predsWhichWillBePreserved.contains(pred)) {
	//			useValFromPhi->addIncoming(
	//					Builder.getInt1(pred != &BBWithSwitch), pred);
	//		}
	//	}
	//	if (!is_contained(predecessors(&exitBB), &BBWithSwitch))
	//		useValFromPhi->addIncoming(Builder.getInt1(1), &BBWithSwitch);
	//}
	SmallVector<Value*> phiReplacements;
	for (auto &phi : exitBB.phis()) {
		//if (&phi == useValFromPhi)
		//	continue;
		Value *v;
		auto curPredI = phi.getBasicBlockIndex(&BBWithSwitch);
		if (curPredI < 0) {
			v = PoisonValue::get(phi.getType());
		} else {
			v = phi.getIncomingValue(curPredI);
		}
		phiReplacements.push_back(v);
	}
	SmallPtrSet<BasicBlock*, 32> seenPredecessors;
	for (BasicBlock *pred : predecessors(&exitBB)) {
		if (pred != &BBWithSwitch && predsWhichWillBePreserved.contains(pred))
			continue; // for this predecessor we do not have to generate select tree because we use original phi
		if (seenPredecessors.contains(pred))
			continue;
		seenPredecessors.insert(pred);
		Builder.SetInsertPoint(&BBWithSwitch,
				BBWithSwitch.getTerminator()->getIterator());
		Value *c;
		auto c2 = constructBranchConditionToBBDirect(Builder, *pred, exitBB);
		if (pred != &BBWithSwitch) {
			c = constructBranchConditionToBB(Builder, BBWithSwitch, *pred,
					exitBBs, true);
			// pred reached from BBWithSwitch & pred jumps to exitBB
			c = Builder.CreateAnd(c, c2,
					"sw." + pred->getName() + ".enFor." + exitBB.getName());
		} else {
			c = c2;
		}
		if (auto cI = dyn_cast<Instruction>(c)) {
			if (!cI->hasName()) {
				cI->setName("fewExitSw.sucSel.en." + pred->getName());
			}
		}
		size_t phiIndex = 0;
		for (auto &phi : exitBB.phis()) {
			//if (&phi == useValFromPhi)
			//	continue;
			Value *prevVal = phiReplacements[phiIndex];
			assert(prevVal->getType() == phi.getType());
			Value *val = phi.getIncomingValueForBlock(pred);
			assert(val->getType() == phi.getType());
			phiReplacements[phiIndex] = Builder.CreateSelect(c, val, prevVal);
			phiIndex++;
		}
		Builder.restoreIP(IP);
	}

	size_t phiIndex = 0;
	for (auto &phi : make_early_inc_range(exitBB.phis())) {
		//if (&phi == useValFromPhi)
		//	continue;
		Value *replacement = phiReplacements[phiIndex];
		assert(replacement->getType() == phi.getType());
		if (predsWhichWillBePreserved.size() <= 1) {
			replacement->takeName(&phi);
			phi.replaceAllUsesWith(replacement);
			phi.eraseFromParent();
		} else {
			// :note: at this point the phi may still have old input values, but they
			//   will be replaced with PoisionValue later
			//   we do not remove blocks which will become unreachable immediately
			//   because it would complicate DT update

			//for (BasicBlock *pred : predecessors(&exitBB)) {
			//	if (!predsWhichWillBePreserved.contains(pred)) {
			//		phi.removeIncomingValue(pred, false);
			//	}
			//}
			if (is_contained(predecessors(&exitBB), &BBWithSwitch)) {
				phi.setIncomingValueForBlock(&BBWithSwitch, replacement);
			} else {
				phi.addIncoming(replacement, &BBWithSwitch);
			}
			//IRBuilderBase::InsertPointGuard g(Builder);
			//Builder.SetInsertPoint(&exitBB, exitBB.getFirstNonPHIIt());
			//assert(useValFromPhi);
			//bool phiIsUseless = phi.getNumIncomingValues() == 1;
			//
			//if (phiIsUseless) {
			//	replacement = Builder.CreateSelect(useValFromPhi,
			//			phi.getIncomingValue(0), replacement);
			//	phi.replaceAllUsesWith(replacement);
			//	phi.eraseFromParent();
			//} else {
			//	replacement = Builder.CreateSelect(useValFromPhi,
			//			&phi, replacement);
			//	replacement->setName(phi.getName());
			//	phi.replaceUsesWithIf(replacement,
			//			[replacement](Use &u) -> bool {
			//				return u.getUser() != replacement; // all except SelectInst which we just create
			//			});
			//}
		}
		phiIndex++;
	}
}

//// traverse DstBB and search for SrcBB and exit or reach of dominatingBB
//bool isPotentiallyReachableForSwitchSuccessors(BasicBlock & dominatingBB, BasicBlock & DstBB, BasicBlock & SrcBB) {
//	if (&SrcBB == &DstBB)
//		return true;
//	if (&SrcBB == &dominatingBB)
//		return false;
//	for (auto * pred: predecessors(&DstBB)) {
//		if (isPotentiallyReachableForSwitchSuccessors(dominatingBB, *pred, SrcBB))
//			return true;
//	}
//	return false;
//}

bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
		llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
		llvm::SwitchInst &SI, bool &exprChanged) {
	auto &BB = *SI.getParent();
	SetVector<BasicBlock*> switchSuccessors;
	for (BasicBlock *suc : successors(&BB)) {
		switchSuccessors.insert(suc);
	}

	DTU.flush();
	auto &DT = DTU.getDomTree();
	SetVector<BasicBlock*> uniqueExits;
	for (size_t sucI = 0; sucI < switchSuccessors.size(); sucI++) {
		BasicBlock *suc = switchSuccessors[sucI];
		// is successor
		if (&BB == suc || !DT.dominates(&BB, suc)
				//|| is_contained(successors(suc), &BB)
				) {
			// is entered from somewhere else than after switch region or
			//// is latch or
			// does not contain only terminator,
			// -> treat it as exit block
			uniqueExits.insert(suc);
			if (uniqueExits.size() > 2)
				return false; // not the pattern of interest
			continue;
		}
		if (&*suc->begin() != suc->getTerminator()) {
			// does not contain only terminator,
			// -> treat it as exit block
			if (!tryHoistCheapInstsAtBlockBegin(*suc, SI.getIterator())
					|| &*suc->begin() != suc->getTerminator()) {
				// hoist is not possible
				uniqueExits.insert(suc);
				if (uniqueExits.size() > 2)
					return false; // not the pattern of interest
				continue;
			}
		}

		auto t = suc->getTerminator();
		if (isa<UnreachableInst>(t)) {
			continue; // this block is irrelevant during search of exits as it can not be reached
		} else if (!isa<BranchInst>(t) && !isa<SwitchInst>(t)) {
			// unsupported terminator
			return false;
		}

		for (auto sucSuc : successors(suc)) {
			switchSuccessors.insert(sucSuc);
			//if (switchSuccessors.contains(sucSuc))
			//	continue; // skip because this is not exit but jump to another sibling block

			//if (!uniqueExits.empty()) {
			//	if (uniqueExits.contains(sucSuc))
			//		continue; // already added
			//
			//	// in the case that the one exit dominates second it means that the dominating
			//	// exit is true exit from section after switch and it has branch to some other block
			//	SmallVector<BasicBlock*, 2> _uniqueExits(uniqueExits.begin(),
			//			uniqueExits.end());
			//	bool isDominated = false;
			//	for (auto curExit : _uniqueExits) {
			//		if (curExit == &BB) {
			//		} else {
			//			if (DT.dominates(curExit, sucSuc)) {
			//				isDominated = true;
			//				break;
			//			} else if (DT.dominates(sucSuc, curExit)) {
			//				uniqueExits.remove(curExit);
			//				uniqueExits.insert(sucSuc);
			//			}
			//		}
			//	}
			//	if (isDominated)
			//		continue;
			//}
			//
			//uniqueExits.insert(sucSuc);
			//if (uniqueExits.size() > 2)
			//	return false; // not the pattern of interest
		}
	}
	if (switchSuccessors.size() == uniqueExits.size()
			&& all_of(uniqueExits, [&switchSuccessors](BasicBlock *eBB) {
				return switchSuccessors.contains(eBB);
			}))
		return false; // there are no blocks to reduce, all successors are exit blocks

	//if (uniqueExits.size() > 1 && uniqueExits.contains(&BB))
	//	return false; // for now we can not allow that because the other exit block would not receive correct predecessors
	if (uniqueExits.size() == 1 && succ_size(&BB) == switchSuccessors.size()
			&& all_of(switchSuccessors, [](BasicBlock *caseBB) {
				auto t = caseBB->getTerminator();
				if (auto br = dyn_cast<BranchInst>(t)) {
					return !br->isConditional();
				} else if (isa<UnreachableInst>(t)) {
					return false;
				} else {
					return true;
				}
			})) {
		return false; // this would only convert phis to select which is not considered good enough CFG simplification
		// we avoid it because it cancels the oportunity to simplify phis.
	}
	// errs() << "uniqueExits:\n";
	// for (auto e : uniqueExits)
	// 	errs() << "    " << e->getName() << "\n";
	// errs() << "before HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: "
	// 		<< *BB.getParent() << "\n";

	// now we know that there are only <=2 unique blocks from the cluster of empty blocks after the SwitchInst
	Builder.SetInsertPoint(&SI);
	SmallVector<DominatorTree::UpdateType> updates;

	switch (uniqueExits.size()) {
	case 0: {
		for (BasicBlock *suc : switchSuccessors) {
			updates.push_back( { DominatorTree::Delete, &BB, suc });
		}
		Builder.CreateUnreachable();
		break;
	}
	case 1: {
		auto newSuc = uniqueExits[0];
		if (!newSuc->phis().empty()) {
			exprChanged = true;
			lowerPhisToSelect(Builder, BB, switchSuccessors, uniqueExits,
					*newSuc);
		}
		for (BasicBlock *suc : successors(&BB)) {
			if (suc == newSuc)
				continue;
			updates.push_back( { DominatorTree::Delete, &BB, suc });
		}
		if (!is_contained(successors(&BB), newSuc)) {
			updates.push_back( { DominatorTree::Insert, &BB, newSuc });
		}
		Builder.CreateBr(newSuc);
		break;
	}
	case 2: {
		// :note: this does not solve the case where exit block has some other
		//        predecessors and the switch is inside of the loop
		//if (isPotentiallyReachableForSwitchSuccessors(BB, *uniqueExits[0],
		//		*uniqueExits[1])) {
		//	// swap exit block so the uniqueExits[0] dominates uniqueExits[1]
		//	auto e0 = uniqueExits[0];
		//	auto e1 = uniqueExits[1];
		//	uniqueExits.clear();
		//	uniqueExits.insert(e1);
		//	uniqueExits.insert(e0);
		//
		//	assert(
		//			!isPotentiallyReachableForSwitchSuccessors(BB,
		//					*uniqueExits[0], *uniqueExits[1])
		//					&& "There should not be any cycle");
		//}
		//switchSuccessos.remove(uniqueExits[0]);
		//switchSuccessos.remove(uniqueExits[1]);
		exprChanged = true;

		for (auto *newSuc : uniqueExits)
			if (!newSuc->phis().empty()) {
				lowerPhisToSelect(Builder, BB, switchSuccessors, uniqueExits,
						*newSuc);
			}
		// must be constructed before we remove terminator from pred blocks
		auto toExit0brCond = constructBranchConditionToBB(Builder, BB,
				*uniqueExits[0], uniqueExits, true);

		for (BasicBlock *suc : switchSuccessors) {
			if (uniqueExits.contains(suc))
				continue;

			//new UnreachableInst(suc->getContext(),
			//		suc->getTerminator()->getIterator());
			//suc->getTerminator()->eraseFromParent();

			// this block will become unreachable, from this reason we has to replace
			// all successor phi values for this BB with PoisonValue to prevent
			// use before def, the value of phi in successor should be already updated and
			// the incoming value from BBWithSwitch should have the value as this value had
			// before this transformation
			for (auto sucOfSuc : successors(suc)) {
				for (auto &phi : sucOfSuc->phis()) {
					phi.setIncomingValueForBlock(suc,
							PoisonValue::get(phi.getType()));
				}
			}
			updates.push_back( { DominatorTree::Delete, &BB, suc });
		}
		for (auto newSuc : uniqueExits) {
			if (!is_contained(successors(&BB), newSuc)) {
				updates.push_back( { DominatorTree::Insert, &BB, newSuc });
			}
		}

		assert(Builder.GetInsertPoint() == SI.getIterator());
		Builder.CreateCondBr(toExit0brCond, uniqueExits[0], uniqueExits[1]);
		break;
	}
	default:
		llvm_unreachable("All cases should be already handled");
	}
	SI.eraseFromParent();
	DTU.applyUpdates(updates);
	for (auto *eBB : uniqueExits) {
		sortPhiOperands(*eBB, /*removeRedundantOperands*/true);
	}
	// errs() << "after HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: "
	// 		<< *BB.getParent() << "\n";

	return true;
}

}
