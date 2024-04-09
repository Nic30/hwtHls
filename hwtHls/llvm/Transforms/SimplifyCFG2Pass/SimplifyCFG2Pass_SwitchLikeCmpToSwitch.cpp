#include "SimplifyCFG2Pass_SwitchLikeCmpToSwitch.h"

#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/ADT/SetVector.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFGUtils.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#define DEBUG_TYPE "simplifycfg2"

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

bool isValueEqualityComparation(Value *Expr, ICmpInst::Predicate &pred,
		Value *&comparedVal, ConstantInt *&caseVal) {
	return match(Expr,
			m_ICmp(pred, m_Value(comparedVal), m_ConstantInt(caseVal)));
}

struct CmpBrInfo {
	BasicBlock &parentBlock;
	ICmpInst::Predicate predicate;
	ConstantInt *caseVal;
	BasicBlock *TSucc;
	BasicBlock *FSucc;
	CmpBrInfo(BasicBlock &_parentBlock, BranchInst &BI) :
			parentBlock(_parentBlock), predicate(
					ICmpInst::Predicate::BAD_ICMP_PREDICATE), caseVal(nullptr), TSucc(
					BI.getSuccessor(0)), FSucc(BI.getSuccessor(1)) {
	}
};

bool tryHoistFromCheapBlocksWithcSwitchLikeCmpBrRewriteBlock(
		Instruction *MovePos, Value *CmpCond, BasicBlock &BB,
		SmallVectorImpl<CmpBrInfo> &branchInfo) {
	bool Changed = tryHoistCheapInstsAtBlockBegin(BB, MovePos);
	if (auto *Br = dyn_cast<BranchInst>(BB.getTerminator())) {
		Value *potentialSwitchCond = nullptr;
		if (!Br->isConditional())
			return Changed;
		CmpBrInfo brInfo(BB, *Br);
		if (!isValueEqualityComparation(Br->getCondition(), brInfo.predicate,
				potentialSwitchCond, brInfo.caseVal))
			return Changed;
		if (potentialSwitchCond == CmpCond) {
			branchInfo.push_back(brInfo);
			for (BasicBlock *Suc : successors(&BB)) {
				if (Suc != &BB && Suc->hasNPredecessors(1)) {
					Changed |=
							tryHoistFromCheapBlocksWithcSwitchLikeCmpBrRewriteBlock(
									MovePos, CmpCond, *Suc, branchInfo);
				}
			}
		}
	}
	return Changed;
}

bool tryHoistFromCheapBlocksWithcSwitchLikeCmpBr(llvm::BranchInst *BI,
		llvm::IRBuilder<> &Builder, llvm::DomTreeUpdater *DTU) {
	if (!BI->isConditional())
		return false;

	Value *potentialSwitchCond = nullptr;

	// search in the direction up while the branch instruction is compatible
	// to find final hoisting location
	BasicBlock *BBTop = BI->getParent();
	//writeCFGToDotFile(*BBTop->getParent(), "tryHoistFromCheapBlocksWithcSwitchLikeCmpBr.before.dot", nullptr, nullptr);

	bool Changed = false;
	CmpBrInfo brInfo(*BBTop, *BI);
	if (isValueEqualityComparation(BI->getCondition(), brInfo.predicate,
			potentialSwitchCond, brInfo.caseVal)) {
		if (auto *Pred = BBTop->getSinglePredecessor()) {
			if (auto *PredBr = dyn_cast<BranchInst>(Pred->getTerminator())) {
				ICmpInst::Predicate pred1;
				Value *c;
				ConstantInt *case1Val;
				if (isValueEqualityComparation(PredBr->getCondition(), pred1, c,
						case1Val)) {
					if (potentialSwitchCond == c)
						return false; // parent has also this pattern, we should start search from there later
				}
			}
		}
		SwitchInst *MainSwitch = nullptr;
		bool usingParentSwitch = false;

		auto BBTopPred = BBTop->getUniquePredecessor();
		Instruction *MoveBeforePoint = BI;
		if (BBTopPred) {
			if (auto *BBTopPredSw = dyn_cast<SwitchInst>(
					BBTopPred->getTerminator())) {
				if (BBTopPredSw->getCondition() == potentialSwitchCond) {
					usingParentSwitch = true;
					MainSwitch = BBTopPredSw;
					MoveBeforePoint = BBTopPredSw;
				}
			}
		}

		SmallVector<CmpBrInfo> branchInfo;
		branchInfo.push_back(brInfo);
		for (BasicBlock *Suc : successors(BBTop)) {
			if (Suc != BBTop && Suc->hasNPredecessors(1)) {
				Changed |=
						tryHoistFromCheapBlocksWithcSwitchLikeCmpBrRewriteBlock(
								MoveBeforePoint, potentialSwitchCond, *Suc,
								branchInfo);
			}
		}

		if ((branchInfo.size() > 1 || usingParentSwitch)
				&& all_of(branchInfo,
						[&branchInfo](CmpBrInfo &bi) {
							return bi.TSucc == branchInfo[0].TSucc
									&& bi.predicate
											== ICmpInst::Predicate::ICMP_EQ;
						})) {
			// for pattern like
			// bb0:
			//   br c==0, bbExit, bb1
			// bb1:
			//   br c==1, bbExit, bb2
			//...
			// bbn:
			//   br c==n, bbExit, bbDefault
			// rewrite this to:
			// bb0.0:
			//    switch c, default: bbDefault {
			//       0: bb0.1
			//       1: bb1
			//       ...
			//    }
			// bb0.1:
			//    br bbExit
			// bb1:
			//    br bbExit
			// ...
			for (auto BInfo = branchInfo.begin(); BInfo != branchInfo.end() - 1;
					++BInfo) {
				if (BInfo->FSucc != &(BInfo + 1)->parentBlock) {
					// can not rewrite because blocks are not chained
					return Changed;
				}
			}
			BasicBlock &BBExit = *branchInfo[0].TSucc;
			BasicBlock &BBDefault = *branchInfo.back().FSucc;
			SmallVector<DominatorTree::UpdateType> domTreeUpdates;

			BasicBlock *BBC0 = nullptr;
			if (usingParentSwitch) {
				// use parent switch and BBTop will be just another case branch
				BBC0 = BBTop;
				// [todo]
				// writeCFGToDotFile(*BBTop->getParent(), "tryHoistFromCheapBlocksWithcSwitchLikeCmpBr.usingParentSwitch.dot", nullptr, nullptr);
				llvm_unreachable(
						"NotImplemented - merge current switch default with newly discovered BBDefault");
			} else {
				// split BBTop to block with all code ending with switch to all branches and an empty branch block BBC0
				BBC0 = SplitBlock(BBTop, BI, DTU, nullptr, nullptr);
				BBTop->getTerminator()->eraseFromParent();
				if (DTU)
					DTU->applyUpdates(
							{ { DominatorTree::Delete, BBTop, BBC0 } });
				Builder.SetInsertPoint(BBTop);
				MainSwitch = Builder.CreateSwitch(potentialSwitchCond,
						&BBDefault);
				if (DTU)
					DTU->applyUpdates( { { DominatorTree::Insert, BBTop,
							&BBDefault } });
			}

			for (auto &BrInfo : branchInfo) {
				auto *Dest = &BrInfo.parentBlock;
				if (Dest == BBTop)
					Dest = BBC0;
				// errs() << "Add case val " << *BrInfo.caseVal << "\n";
				MainSwitch->addCase(BrInfo.caseVal, Dest);
				Dest->getTerminator()->eraseFromParent();
				Builder.SetInsertPoint(Dest);
				Builder.CreateBr(&BBExit);
				if (DTU) {
					// Best->BrInfo.TSucc remains
					DTU->applyUpdates( { { DominatorTree::Insert, BBTop, BBC0 },
							{ DominatorTree::Delete, Dest, BrInfo.FSucc }, });
				}
			}
			//writeCFGToDotFile(*BBTop->getParent(), "tryHoistFromCheapBlocksWithcSwitchLikeCmpBr.dot", nullptr, nullptr);
		}
	}

	return Changed;

}

}
