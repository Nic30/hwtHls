#pragma once

#include <map>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Transforms/Utils/Cloning.h>

namespace hwtHls {

class LowerPhisToSelectInRegionContext {
public:
	llvm::IRBuilderBase &Builder;
	// the top block of region, which dominates all block in
	//	allBBsOfRegion except the exit blocks
	llvm::BasicBlock &BB0;
	// :note: if BB0 is in allBBsOfRegion it means the region is a loop and BB0 is its header
	// :note: exitBBs are part of allBBsOfRegion
	llvm::SetVector<llvm::BasicBlock *> &allBBsOfRegion;
	llvm::SmallVector<bool, 2> exitBBDominatedByBB0; // for each exit block true if every pred is from region
	llvm::SetVector<llvm::BasicBlock *> &exitBBs; // exit blocks from region
	// exit block is t block which contain some instruction which can not be in region of it
	// is not properly dominated by BB0
	// :attention: BB0 can also be the exit block

	// cache for expressions of branch conditions which are 1 if the BB is
	// reached from BB0
	// :note: if block has a record in bbEnableCache it means that all phis
	// in that block were lowered and thus no check of parent is required
	llvm::DenseMap<llvm::BasicBlock *, llvm::Value *> bbEnableCache;
	// llvm::DenseMap<std::pair<llvm::BasicBlock *, llvm::BasicBlock *>, llvm::Value *> bbEdgeEnableCache;

	// llvm::DenseMap<llvm::PHINode *, llvm::Value *> loweredPhiCache;
	// subset of allBBsOfRegion, blocks reachable from exitBBs[0] post-dominated by exitBBs[]
	llvm::SetVector<llvm::BasicBlock *> betweenExitBBs;

	// BB0, exit block if it has some predecessor from outside of the region
	// or some other exit block transitively
	llvm::SetVector<llvm::BasicBlock *> bbsWhichMustPreservePhis;

	// set of values which transitively depend on something from exitBB0
	//std::unordered_set<llvm::Value *> valuesAfffectedByExit0;
	// // map for phis which are instantiated for values defined in exitBB0
	// // directly and used in betweenExitBBs or exitBB1 phi node args
	// llvm::MapVector<llvm::PHINode *, llvm::PHINode *> phiInExit1ForValuesFromExit0;
	// // map for value  from betweenExitBBs which may be visited without passing
	// // trough the exitBBs[0]
	// // * this map stores the version of value for all non-exitBBs[0] paths
	// //   and it is used to resolve final value in exitBBs[1]
	// // * selects implementing phis are build the end of BB0
	// // * :note: exitBBs[1] phi rewrite need to also create another
	// //    version for exit1 as there must be also a version of phi for exit0(original),
    // //    exit1(original updated with exit1Versions) and final (the one merging
    // //    all together based on branch condition for exitBBs)
	// llvm::DenseMap<llvm::Value*, llvm::PHINode *> exit1VersionOfValueDependentOnExit0;
	llvm::DenseSet<llvm::PHINode*> newPhisInExit1;
	std::map<llvm::Instruction*, llvm::PHINode*> phisForInstNotDominatingE0;
	std::map<llvm::Instruction*, llvm::PHINode*> phisForInstNotDominatingE1;
	
	llvm::BasicBlock::iterator bb0SelectInsertPos;
	//llvm::BasicBlock::iterator bbExit0SelectInsertPos;
	//llvm::BasicBlock::iterator bbExit1SelectInsertPos;
		
	LowerPhisToSelectInRegionContext(
		llvm::IRBuilderBase &Builder, llvm::BasicBlock &BB0,
		llvm::SetVector<llvm::BasicBlock *> &allBBsOfRegion,
		llvm::SetVector<llvm::BasicBlock *> &exitBBs) :
		Builder(Builder),
		BB0(BB0),
		allBBsOfRegion(allBBsOfRegion),
		exitBBs(exitBBs) {
#ifndef NDEBUG
		for (auto exitBB : exitBBs) {
			assert(allBBsOfRegion.contains(exitBB));
		}
#endif
	};
	/* recursively discard blocks from  allBBsOfRegion if they are successor of exitBBs[1]
	 * :returns: true if any block fom exitBBs was reached (meaning there is a loop on exitBBs[1])
	 */
	bool _discardAllExit1SuccessorsFromRegion();
	void _swapExits();
	bool analyze();
	
	bool hasPredecessorFromRegion(llvm::BasicBlock *BB) const {
		return any_of(predecessors(BB), [this](llvm::BasicBlock *BB) {
			return allBBsOfRegion.contains(BB);
		});
	};
	bool hasPredecessorOutOfRegion(llvm::BasicBlock &BB) const {
		return (&BB == &BB0) ||
			   (&BB == exitBBs[0] && !exitBBDominatedByBB0[0]) ||
			   (exitBBs.size() == 2 && &BB == exitBBs[1] &&
				(!exitBBDominatedByBB0[1]));
		// return any_of(predecessors(&BB), [this](llvm::BasicBlock *predBB) {
		//	return predBB != &BB0 && !allBBsOfRegion.contains(predBB);
		// });
	}
	bool isDominatedByBB0(llvm::BasicBlock &BB, bool properly = false) const {
		if (&BB == &BB0) {
			return !properly;
		} else if (&BB == exitBBs[0] || betweenExitBBs.contains(&BB)) {
			return exitBBDominatedByBB0[0];
		} else if (exitBBs.size() == 2 && &BB == exitBBs[1] &&
				   (!exitBBDominatedByBB0[0] || !exitBBDominatedByBB0[1])) {
			return false;
		}
		// section between BB0 and exits
		return true;
	}
	bool isProperlyDominatedByBB0(llvm::BasicBlock &BB) const {
		return isDominatedByBB0(BB, true);
	}
	bool hasSuccessorFromRegionExceptForUnreachable(llvm::BasicBlock *BB) const {
		return any_of(successors(BB), [this, BB](llvm::BasicBlock *sBB) {
			// :note: BB0 is excluded because if there is such a edge, the edge is not part of the region itself
			return sBB != &BB0 && sBB != BB && allBBsOfRegion.contains(sBB) && !isa<llvm::UnreachableInst>(sBB->getTerminator());
		});
	};
	bool isInExit0Section(llvm::BasicBlock &BB) const {
		return exitBBs.size() == 2 && (&BB == exitBBs[0] || betweenExitBBs.contains(&BB));
	}
	
	bool isBlockExit1WithConditionRequired(llvm::BasicBlock & BB) const {
		// if we can not use exit0 cond
		return exitBBs.size() == 2 && (exitBBs[0] == &BB0 && exitBBs[1] == &BB);
	}

	bool isPartOfRegion(llvm::BasicBlock &BB) const {
		return &BB == &BB0 || allBBsOfRegion.contains(&BB);
	}
	// Unswitch such blocks so there is a variant which have exit0 as (transitive) pred
	// and original will become dominated by exit0 (path from bb0 without exit0 will be removed)
	bool blocksReachableFromBB0WithoutExit0_unswitch( llvm::DomTreeUpdater &DTU, llvm::ValueToValueMapTy& VMap);
	bool blocksReachableFromBB0WithoutExit0_unswitch(
		llvm::DomTreeUpdater &DTU,
		llvm::SetVector<llvm::BasicBlock *> &origSwitchSuccessors);
	// for exit blocks which ends with unreachable unswitch them,
	// from orginal bb, remove non-region predecessors,
	// form a new exit block replacement
	// and reroute non-region block to jump into this block instead, convert exit block to a
	// normal region block (remove it from exits)
	// :note: this is necessary because unreachable blocks will not have branch condition constructed
	//  and the condition would be missing in bbEnableCache
	bool unreachableExits_unswitch(
		llvm::DomTreeUpdater &DTU,
		llvm::SetVector<llvm::BasicBlock *> &origSwitchSuccessors);
	void print(llvm::raw_ostream &OS) const;
};
}

namespace llvm {
static inline raw_ostream &operator<<(raw_ostream &OS, const hwtHls::LowerPhisToSelectInRegionContext &lptsrc) {
  lptsrc.print(OS);
  return OS;
}
}

namespace hwtHls {
// construct an expression which is true if the DstBB is reached from SrcBB
// The expression is constructed from bottom-up, the SelectInst
// is used to select tha value from successor
// :note: ignoreCheckForDstAndHandle is useful when we start at the block which
//        is dst or handle but we want to probe successors
// :param handleBBs: blocks where pred->suc search for DstBB should stop and
//        return false
llvm::Value *constructBranchConditionToBB(
	llvm::IRBuilderBase &Builder, llvm::BasicBlock &SrcBB,
	llvm::BasicBlock &DstBB,
	const llvm::SetVector<llvm::BasicBlock *> &handleBBs,
	bool ignoreCheckForDstAndHandle);

// Construct the expression which is 1 if the SrcBB jumps to DstBB
llvm::Value *constructBranchConditionToBBDirect(llvm::IRBuilderBase &Builder,
												llvm::BasicBlock &SrcBB,
												llvm::BasicBlock &DstBB,
												std::optional<llvm::Value*> condOverride={}
											);

// * construct enable selections for every jump
// * convert phis to select if possible
// * when block has also predecessor from outside of block there are several complicated situation
//    * phi in BB0 or exitBBs - phis in this block and all later needs to have phi constructed in predecessor (BB0 or exitBBs)
//      for values defined in BB0, exitBBs[0] to assert def before use  
//    * phi in exit1 - values and select conditions are potentially defined in BB0, exitBBs[0] or in betweenExitBBs
//      that implies that the phi must be created in exitBBs[0] or/and in exitBBs[1], (for blocks in betweenExitBBs 
//      new phis should not be required as if value was use in exitBBs[1] the phis should already exist)
// :returns: the enable condition for a given block
llvm::Value *lowerPhisOfBlockInRegion(LowerPhisToSelectInRegionContext &ctx,
									  llvm::BasicBlock &BB);

//void lowerPhisOfBlockInRegion_finalizeExit0AndBB0PathSelect(LowerPhisToSelectInRegionContext &ctx, llvm::DominatorTree &DT);
//void updatePhiOperandsBeforeCfgUpdate(LowerPhisToSelectInRegionContext &ctx);
// transform PHIs operands to select,
// but only for blocks in switchSuccessors which are going to be removed
// :note: if exitBB has predecessors which are not in switchSuccessors then
//        it will retain phi, but incoming values from switchSuccessors will be
//        stripped and new incoming value from BBWithSwitch will be added
//        together with isJmpFromSw phi
// :note: this should be called before predecessors/successors are updated
//bool lowerPhisToSelectInRegion(LowerPhisToSelectInRegionContext &ctx);

} // namespace hwtHls