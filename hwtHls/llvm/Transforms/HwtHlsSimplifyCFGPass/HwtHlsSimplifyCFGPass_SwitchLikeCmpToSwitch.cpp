
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchLikeCmpToSwitch.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>

#include <map>
#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/Instructions.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/ADT/SetVector.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>


using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

bool isValueEqualityComparation(Value *Expr, CmpPredicate &pred,
		Value *&comparedVal, ConstantInt *&caseVal) {
	return match(Expr,
			m_ICmp(pred, m_Value(comparedVal), m_ConstantInt(caseVal)));
}

struct CmpBrInfo {
	BasicBlock &parentBlock;
	CmpPredicate predicate;
	ConstantInt *caseVal;  // parentBlock is entered if  predicate is satisfied on condition and caseVal
	BasicBlock *TSucc;
	BasicBlock *FSucc;
	CmpBrInfo(BasicBlock &_parentBlock, BranchInst &BI) :
			parentBlock(_parentBlock), predicate(
					ICmpInst::Predicate::BAD_ICMP_PREDICATE), caseVal(nullptr), TSucc(
					BI.getSuccessor(0)), FSucc(BI.getSuccessor(1)) {
	}
};

bool tryHoistFromCheapBlocksWithSwitchLikeCmpBrRewriteBlock(
		BasicBlock::iterator MovePos, Value *CmpCond, BasicBlock &BB,
		SmallVectorImpl<CmpBrInfo> &branchInfo) {
	bool Changed = tryHoistCheapInstsAtBlockBegin(BB, MovePos);
	if (BB.begin() != BB.getTerminator()->getIterator()) {
		// there is some leftover in the block, can not continue in search
	} else if (auto *Br = dyn_cast<BranchInst>(BB.getTerminator())) {
		Value *potentialSwitchCond = nullptr;
		if (!Br->isConditional())
			return Changed;

		CmpBrInfo brInfo(BB, *Br);
		if (!isValueEqualityComparation(Br->getCondition(), brInfo.predicate,
				potentialSwitchCond, brInfo.caseVal)) {
			return Changed;

		} else if (potentialSwitchCond == CmpCond) {
			branchInfo.push_back(brInfo);
			for (BasicBlock *Suc : successors(&BB)) {
				if (Suc != &BB && Suc->hasNPredecessors(1)) {
					Changed |=
							tryHoistFromCheapBlocksWithSwitchLikeCmpBrRewriteBlock(
									MovePos, CmpCond, *Suc, branchInfo);
				}
			}
		}
	}
	return Changed;
}

bool tryHoistFromCheapBlocksWithSwitchLikeCmpBr_match(
	llvm::BranchInst *BI, bool &exprChanged, SwitchInst *&MainSwitch,
	bool &usingParentSwitch, SmallVector<CmpBrInfo> &branchInfo,
	BasicBlock *&BBTop, BasicBlock *&BBTopPred, Value *&potentialSwitchCond) {

	if (!BI->isConditional())
		return false;

	potentialSwitchCond = nullptr;

	// search in the direction up while the branch instruction is compatible
	// to find final hoisting location
	BBTop = BI->getParent();
	// writeCFGToDotFile(*BBTop->getParent(),
	// "tryHoistFromCheapBlocksWithcSwitchLikeCmpBr.before.dot", nullptr,
	// nullptr);

	CmpBrInfo brInfo(*BBTop, *BI);
	if (!isValueEqualityComparation(BI->getCondition(), brInfo.predicate,
									potentialSwitchCond, brInfo.caseVal)) {
		return false;
	}
	if (auto *Pred = BBTop->getSinglePredecessor()) {
		if (auto *PredBr = dyn_cast<BranchInst>(Pred->getTerminator())) {
			CmpPredicate pred1;
			Value *c;
			ConstantInt *case1Val;
			if (isValueEqualityComparation(PredBr->getCondition(), pred1, c,
										   case1Val)) {
				if (potentialSwitchCond == c)
					return false; // parent has also this pattern, we should
								  // start search from there later
			}
		}
	}
	MainSwitch = nullptr;
	usingParentSwitch = false;

	BBTopPred = BBTop->getUniquePredecessor();
	BasicBlock::iterator MoveBeforePoint = BI->getIterator();
	if (BBTopPred) {
		if (auto *BBTopPredSw =
				dyn_cast<SwitchInst>(BBTopPred->getTerminator())) {
			if (BBTopPredSw->getCondition() == potentialSwitchCond) {
				usingParentSwitch = true;
				MainSwitch = BBTopPredSw;
				MoveBeforePoint = BBTopPredSw->getIterator();
			}
		}
	}

	branchInfo.push_back(brInfo);
	for (auto &brInfo: branchInfo) {
		if (!usingParentSwitch && &brInfo.parentBlock == BBTop)
			continue;
		// hoist an normalize branch
		exprChanged |=
				tryHoistFromCheapBlocksWithSwitchLikeCmpBrRewriteBlock(
					MoveBeforePoint, potentialSwitchCond, brInfo.parentBlock, branchInfo);

		// can not rewrite if some blocks except top contain something
		// with a side effect, the blocks are not just implementing SwitchInst
		if (&*brInfo.parentBlock.begin() != brInfo.parentBlock.getTerminator())
			return false;
	}

	if (!(branchInfo.size() > 1 || usingParentSwitch)) {
		return false;
	} else if (!all_of(branchInfo, [&branchInfo](CmpBrInfo &bi) {
				   return bi.TSucc == branchInfo[0].TSucc &&
						  bi.predicate == ICmpInst::Predicate::ICMP_EQ;
			   })) {
		return false;
	}
	for (auto BInfo = branchInfo.begin(); BInfo != branchInfo.end() - 1;
		 ++BInfo) {
		if (BInfo->FSucc != &(BInfo + 1)->parentBlock) {
			// can not rewrite because blocks are not chained
			return false;
		}
	}
	return true;
}

bool tryHoistFromCheapBlocksWithSwitchLikeCmpBr(llvm::BranchInst *BI,
		llvm::IRBuilder<> &Builder, llvm::DomTreeUpdater *DTU, bool & exprChanged) {
	SwitchInst * MainSwitch;
	bool usingParentSwitch;
	SmallVector<CmpBrInfo> branchInfo;
	BasicBlock *BBTop;
	BasicBlock *BBTopPred;
	Value *potentialSwitchCond;
	if (!tryHoistFromCheapBlocksWithSwitchLikeCmpBr_match(
			BI, exprChanged, MainSwitch, usingParentSwitch, branchInfo, BBTop,
			BBTopPred, potentialSwitchCond)) {
		return false;
	}
	BasicBlock &BBExit =
		*branchInfo[0].TSucc; // common exit for all block in the chain
	BasicBlock &BBDefault =
		*branchInfo.back().FSucc; // a block on the end of the chain

	// if (BBTopPred) {
	// 	errs() << "BBTopPred: ";
	// 	BBTopPred->printAsOperand(errs());
	// 	errs() << "\n";
	// }
	// errs() << "BBTop:";
	// BBTop->printAsOperand(errs());
	// errs() << "\n";
	// errs() << "BBExit:";
	// BBExit.printAsOperand(errs());
	// errs() << "\n";
	// errs() << "BBDefault:";
	// BBDefault.printAsOperand(errs());
	// errs() << "\n";
	// errs() << "Branches:\n";
	// for (auto &br : branchInfo) {
	// 	errs() << "    " << *br.caseVal << "  ";
	// 	br.parentBlock.printAsOperand(errs());
	// 	errs() << "\n";
	// }

	std::map<ConstantInt *, BasicBlock *> finalCaseDst;

	for (auto &BrInfo : reverse(branchInfo)) {
		assert(BrInfo.predicate == CmpInst::ICMP_EQ);
		finalCaseDst[BrInfo.caseVal] = &BrInfo.parentBlock;
	}
	if (usingParentSwitch) {
		// if using parent switch with same case values we have to check for
		// several situations
		// * block is unreachable because parent switch is jumping somewhere
		// else
		//			// block should replace dest in parent switch case if
		//original dest is in block before new dest
		//			// else should replace dest with succ for same val or
		//BBDefault because top Switch jumps to blocks which are comparing with
		//a different values
		// does not make branch unreachable

		// SmallPtrSet<BasicBlock*, 16> seen;
		// for (auto &BrInfo: branchInfo) {
		//	auto prevDstCase = finalCaseDst.find(BrInfo.caseVal);
		//	if (prevDstCase == finalCaseDst.end()) {
		//		finalCaseDst[BrInfo.caseVal] = &BrInfo.parentBlock;
		//	} else {
		//		bool origJmpToSomePred = seen.contains(prevDstCase->second);
		//		if (origJmpToSomePred) {
		//		} else {
		//		}
		//	}
		//	seen.insert(&BrInfo.parentBlock);
		// }
		assert(MainSwitch->getDefaultDest() == &BBDefault);
		DenseMap<BasicBlock *, unsigned> bbIndexInChain;
		DenseMap<ConstantInt *, SmallVector<BasicBlock *, 2>> blockForConst;
		{
			unsigned i = 0;
			for (auto &BrInfo : branchInfo) {
				bbIndexInChain[&BrInfo.parentBlock] = i;
				blockForConst[BrInfo.caseVal].push_back(&BrInfo.parentBlock);
				++i;
			}
		}
		for (auto &C : MainSwitch->cases()) {
			auto *curDst = C.getCaseSuccessor();
			auto bbIndex = bbIndexInChain.find(curDst);
			if (bbIndex == bbIndexInChain.end()) {
				// if case constant does not cause jump in block chain
				// (branchInfo), then we keep it as it is
				finalCaseDst[C.getCaseValue()] = curDst;
			} else {
				// if it jumps somewhere in branchInfo
				// we pick the first block which is case dst for same constant
				// after (>=) the position of current jump or BBDefault
				auto caseValBBs = blockForConst.find(C.getCaseValue());
				BasicBlock *newDst = nullptr;
				if (caseValBBs == blockForConst.end()) {
					newDst = &BBDefault;
				} else {
					for (auto *BB : caseValBBs->second) {
						if (bbIndexInChain[BB] >= bbIndex->second) {
							// found a block which is case for this value and is
							// after (>=) the position the original jump was
							// jumping to, thus this block will jump to BBExit
							// if the switch condition has the value of case val
							newDst = BB;
							break;
						}
					}
					if (!newDst) {
						newDst = &BBDefault;
					}
				}
				finalCaseDst[C.getCaseValue()] = newDst;
			}
		}
	}

	SmallVector<DominatorTree::UpdateType> domTreeUpdates;
	auto topHasSuccessor = [BBTopPred](BasicBlock *succ) {
		return any_of(successors(BBTopPred),
					  [succ](BasicBlock *BB) { return BB == succ; });
	};
	BasicBlock *BBC0 = nullptr;
	if (usingParentSwitch) {
		// use parent switch and BBTop will be just another case branch
		BBC0 = BBTop;
		auto BBDefPhis = BBDefault.phis();
		if (&BBDefault == MainSwitch->getDefaultDest() && BBDefPhis.empty()) {
			// no need to modify, the BBDefault is already a switch default
		} else {
			// writeCFGToDotFile(*BBTop->getParent(),
			// "tryHoistFromCheapBlocksWithSwitchLikeCmpBr.usingParentSwitch.dot",
			// nullptr, nullptr); if BBTop was entered from BBTopPred then
			// parent switch default should jump to BBDefault else to original
			// parent switch (MainSwitch) default

			// insert new block between BBTopPred, BBDefault
			DominatorTree *DT = nullptr;
			if (DTU) {
				DTU->flush();
				DT = &DTU->getDomTree();
			}
			auto originalSwDefBB = MainSwitch->getDefaultDest();
			auto newSwDefBB = SplitEdge(BBTopPred, originalSwDefBB, DT);
			// auto newSwDefForTopBB = BasicBlock::Create(BBTop->getContext(),
			// "", BBTop->getParent(), originalSwDefBB->getNextNode());

			// jmp BBDefault if BBTop was entered from BBTopPred else jump to
			// BBTopPred default
			auto origTerm = newSwDefBB->getTerminator();
			Builder.SetInsertPoint(origTerm);
			Value *BrToBBTopCond =
				constructBranchConditionToBBDirect(Builder, *BBTopPred, *BBTop);
			Builder.CreateCondBr(BrToBBTopCond, originalSwDefBB, &BBDefault);
			origTerm->eraseFromParent();
			if (DTU)
				DTU->applyUpdates(
					{{DominatorTree::Insert, newSwDefBB, &BBDefault}});

			auto *lastCBB = &branchInfo.back().parentBlock;
			BBDefault.replacePhiUsesWith(lastCBB, newSwDefBB);
			for (auto &C : MainSwitch->cases()) {
				auto *finCaseDst = finalCaseDst[C.getCaseValue()];
				auto *curCaseDst = C.getCaseSuccessor();
				if (finCaseDst != curCaseDst) {
					bool finWasSuccessor = DTU && topHasSuccessor(finCaseDst);
					C.setSuccessor(finCaseDst);
					bool curIsStillSuccessor =
						DTU && topHasSuccessor(curCaseDst);
					if (DTU) {
						if (!curIsStillSuccessor)
							DTU->applyUpdates({{DominatorTree::Delete,
												BBTopPred, curCaseDst}});

						if (!finWasSuccessor)
							DTU->applyUpdates({{DominatorTree::Insert,
												BBTopPred, finCaseDst}});
					}
				}
			}

			//	llvm_unreachable(
			//			"NotImplemented - merge current switch default with
			//newly discovered BBDefault");
		}
	} else {
		// split BBTop to block with all code ending with switch to all branches
		// and an empty branch block BBC0
		BBC0 = SplitBlock(BBTop, BI, DTU, nullptr, nullptr, ".swToBr");
		BBTop->getTerminator()->eraseFromParent();
		if (DTU)
			DTU->applyUpdates({{DominatorTree::Delete, BBTop, BBC0}});
		Builder.SetInsertPoint(BBTop);
		MainSwitch = Builder.CreateSwitch(potentialSwitchCond, &BBDefault);
		if (DTU)
			DTU->applyUpdates({{DominatorTree::Insert, BBTop, &BBDefault}});
	}

	SmallSet<ConstantInt *, 16> seenCases;
	for (auto &C : MainSwitch->cases()) {
		seenCases.insert(C.getCaseValue());
	}

	SmallVector<Value *> valueForPrevCaseForPhiInBBExit;
	auto BBExitPhis = BBExit.phis();
	for (auto &BrInfo : branchInfo) {
		auto *Dest = &BrInfo.parentBlock;
		if (Dest == BBTop)
			Dest = BBC0;
		if (seenCases.contains(BrInfo.caseVal)) {
			continue; // this block is already updated
		} else if (finalCaseDst[BrInfo.caseVal] != &BrInfo.parentBlock) {
			continue; // this block will become unreachable
		}
		seenCases.insert(BrInfo.caseVal);
		MainSwitch->addCase(BrInfo.caseVal, Dest);

		// replace conditional jump depending on cmp with condition of new
		// switch with jump to common BBExit
		Dest->getTerminator()->eraseFromParent();
		Builder.SetInsertPoint(Dest);
		Builder.CreateBr(&BBExit);

		if (!BBExitPhis.empty()) {
			bool isFirstBB = valueForPrevCaseForPhiInBBExit.empty();
			size_t phiIndex = 0;
			for (auto &phi : BBExitPhis) {
				auto BBIndex = phi.getBasicBlockIndex(Dest);
				Value *v = nullptr;
				if (BBIndex < 0) {
					// the block was not originally a predecessor of exit block
					// that means if the block is entered some successor would
					// eventually enter the BBExit, but all cmps are checking
					// for equality and now when this block is entered we know
					// that only possible branch in original code was default
					// branch at the end
					v = PoisonValue::get(phi.getType());
					if (isFirstBB) {
						phi.addIncoming(v, Dest);
					} else {
						auto _v = valueForPrevCaseForPhiInBBExit[phiIndex];
						phi.addIncoming(_v, Dest);
					}
				} else {
					v = phi.getIncomingValue(BBIndex);
				}
				if (isFirstBB) {
					valueForPrevCaseForPhiInBBExit.push_back(v);
				} else {
					valueForPrevCaseForPhiInBBExit[phiIndex] = v;
				}
				++phiIndex;
			}
		}
		if (DTU) {
			// Dest->BrInfo.TSucc (ExitBB) remains
			DTU->applyUpdates({
				{DominatorTree::Insert, BBTop, Dest}, //
				{DominatorTree::Delete, Dest, BrInfo.FSucc},
			});
		}
	}
	if (!usingParentSwitch) {
		// BBDefault is now entered from BBTop instead of last case BB in
		// branchInfo
		BasicBlock *lastCBB = &branchInfo.back().parentBlock;
		BBDefault.replacePhiUsesWith(lastCBB, BBTop);
		if (DTU) {
			DTU->applyUpdates({
				{DominatorTree::Delete, lastCBB, &BBDefault},
			});
		}
	}
	sortPhiOperands(BBDefault);
	sortPhiOperands(BBExit);

	return true;
}

}
