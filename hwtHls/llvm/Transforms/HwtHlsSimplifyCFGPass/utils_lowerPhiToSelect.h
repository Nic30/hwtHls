#pragma once

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/IRBuilder.h>
#include <unordered_set>

namespace hwtHls {

class LowerPhisToSelectInRegionContext {
public:
	llvm::IRBuilderBase &Builder;
	llvm::BasicBlock &BB0; // entry block to a region
	llvm::SetVector<llvm::BasicBlock *> &allBBsOfRegion;
	llvm::SetVector<llvm::BasicBlock *> &exitBBs; // exit blocks from region
	// exit block is t blok which contain some instruction which can not be in region of it
	// is not properly dominated by BB0
	// :attention: BB0 can also be the exit block

	// cache for expressions of branch conditions which are 1 if the BB is
	// reached from BB0
	// :note: if block has a record in bbEnableCache it means that all phis
	// in that block were lowered and thus no check of parent is required
	llvm::DenseMap<llvm::BasicBlock *, llvm::Value *> bbEnableCache;
	// llvm::DenseMap<std::pair<llvm::BasicBlock *, llvm::BasicBlock *>, llvm::Value *> bbEdgeEnableCache;

	// llvm::DenseMap<llvm::PHINode *, llvm::Value *> loweredPhiCache;
	llvm::SetVector<llvm::BasicBlock *> betweenExitBBs;

	// BB0, exit block if it has some predecessor from outside of the region
	// or some other exit block transitively
	llvm::SetVector<llvm::BasicBlock *> bbsWhichMustPreservePhis;

	// set of values which transitively depend on something from exitBB0
	std::unordered_set<llvm::Value *> valuesAfffectedByExit0;
	// map for phis which are instantiated for values defined in exitBB0
	// directly and used in betweenExitBBs or exitBB1 phi node args
	llvm::DenseMap<llvm::PHINode *, llvm::PHINode *>
		phiInExit1ForValuesFromExit0;

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
	bool analyze();
	bool hasPredecessorFromRegion(llvm::BasicBlock *BB) {
		return any_of(predecessors(BB), [this](llvm::BasicBlock *BB) {
			return allBBsOfRegion.contains(BB);
		});
	};
	bool hasSuccessorFromRegion(llvm::BasicBlock *BB) {
		return any_of(successors(BB), [this, BB](llvm::BasicBlock *sBB) {
			// :note: BB0 is excluded because if there is such a edge, the edge is not part of the region itself
			return sBB != &BB0 && sBB != BB && allBBsOfRegion.contains(sBB);
		});
	};
};

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
												llvm::BasicBlock &DstBB);

// :returns: the enable condition for a given block
llvm::Value *lowerPhisOfBlockInRegion(LowerPhisToSelectInRegionContext &ctx,
									  llvm::BasicBlock &BB);
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