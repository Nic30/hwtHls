#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>

#include <cassert>
#include <optional>

#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/CFG.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/ErrorHandling.h>
#include <utility>

//#define LowerPhisToSelectInRegionContext_DEBUG
#ifdef LowerPhisToSelectInRegionContext_DEBUG
#include <llvm/IR/Verifier.h>
#endif
using namespace llvm;

namespace hwtHls {

void collectBlocks(BasicBlock &src, llvm::SetVector<llvm::BasicBlock *> &seen,
				   std::function<bool(BasicBlock &)> predicate) {
	for (auto* suc: successors(&src)) {
		// dbgs() << "collectBlocks: ";
		// suc->printAsOperand(dbgs());
		// dbgs() << "\n";
		if (seen.contains(suc)) {
			continue;
		}			
		if (!predicate(*suc))
			continue;
		seen.insert(suc);
		collectBlocks(*suc, seen, predicate);
	}		
}

bool LowerPhisToSelectInRegionContext::_discardAllExit1SuccessorsFromRegion() {
	SmallVector<BasicBlock*> toSearch;
	assert(exitBBs.size() == 2);
	SmallPtrSet<BasicBlock*, 32> toRm;
	for (auto suc: successors(exitBBs[1])) {
		if (allBBsOfRegion.contains(suc)) {
			toSearch.push_back(suc);
		}
	}
	while (!toSearch.empty()) {
		auto bb = toSearch.pop_back_val();
		if (exitBBs.contains(bb))
			return true;
		if (toRm.insert(bb).second) {
			for (auto suc: successors(bb)) {
				if (allBBsOfRegion.contains(suc)) {
					toSearch.push_back(suc);
				}
			}
		}
	}
	allBBsOfRegion.remove_if([&toRm] (BasicBlock * BB) {
		return toRm.contains(BB);
	});
	
	return false;
}

void LowerPhisToSelectInRegionContext::_swapExits() {
	auto e1 = exitBBs.pop_back_val();
	auto e0 = exitBBs.pop_back_val();
	exitBBs.insert(e1);
	exitBBs.insert(e0);
}

bool LowerPhisToSelectInRegionContext::analyze() {
	// auto exitBBAfterPhis = exitBB.getFirstNonPHIIt();
	bbsWhichMustPreservePhis.insert(exitBBs.begin(), exitBBs.end());
	bbsWhichMustPreservePhis.insert(&BB0);
#ifdef LowerPhisToSelectInRegionContext_DEBUG
	for (auto exitBB : exitBBs) {
		assert(allBBsOfRegion.contains(exitBB) &&
			   "This should be always the case");
	}
#endif
	topologicalSortForBlocks(allBBsOfRegion, &BB0);
#ifdef LowerPhisToSelectInRegionContext_DEBUG
	errs() << "allBBsOfRegion\n";
	for (auto *BB: allBBsOfRegion) {
		errs() << "     ";
		BB->printAsOperand(errs());
		errs() << "\n";
	}
	for (auto exitBB : exitBBs) {
		assert(allBBsOfRegion.contains(exitBB) && "This should be always the case");
	}
#endif
	if (exitBBs.size() > 1) {
		assert(exitBBs.size() == 2);
		assert(!exitBBs.contains(&BB0) && "This is required because IP for select/phis would not be clearly defined");
		// assert that the exitBB0 is topologically before exitBB1
		if (hasSuccessorFromRegionExceptForUnreachable(exitBBs[1])) {
			// swap items in exitBBs
			_swapExits();
#ifdef LowerPhisToSelectInRegionContext_DEBUG
			errs() << "LowerPhisToSelectInRegionContext::analyze\n";
			exitBBs[0]->printAsOperand(errs());
			errs() << "    " << hasSuccessorFromRegionExceptForUnreachable(exitBBs[0]) << "\n";
			exitBBs[1]->printAsOperand(errs());
			errs() << "    " << hasSuccessorFromRegionExceptForUnreachable(exitBBs[1]) << "\n";
#endif
			if (exitBBs[1] != &BB0) {
				if(_discardAllExit1SuccessorsFromRegion()) {
					return false;
				}
				assert((!hasSuccessorFromRegionExceptForUnreachable(exitBBs[1])) &&
							   "There should not be any loop between the exit blocks");
			}
		}

		// localize blocks between exits
		// because we will have to sink part of instructions to exit1
		findBlocksBetweenExitBlocksOfRegion(BB0, allBBsOfRegion, exitBBs,
											betweenExitBBs);
		if (!betweenExitBBs.empty())
			topologicalSortForBlocks(betweenExitBBs);
		//for (auto &I : *exitBBs[0]) {
		//	valuesAfffectedByExit0.insert(&I);
		//}
	}
	for (auto e: exitBBs) {
		exitBBDominatedByBB0.push_back(all_of(predecessors(e), [this](BasicBlock* BB) {
			return isPartOfRegion(*BB);
		}));
	}
	//if (all_of(allBBsOfRegion,
	//		   [](BasicBlock *BB) { return BB->phis().empty(); })) {
	//	if (!hasPredecessorFromRegion(&BB0) || BB0.phis().empty()) {
	//		return false; // no phis to lower
	//	}
	//}
#ifndef NDEBUG
	for (auto exitBB : exitBBs) {
		assert(allBBsOfRegion.contains(exitBB) && "This was the case at beginning as it should be always the case");
	}
#endif
	return true;
}

bool LowerPhisToSelectInRegionContext::blocksReachableFromBB0WithoutExit0_unswitch(llvm::DomTreeUpdater &DTU, ValueToValueMapTy& VMap) {
	// :note: at this point blocks would be topologically sorted
	assert(exitBBs.size() == 2);
	llvm::SetVector<llvm::BasicBlock *> blocksReachableFromBB0WithoutExit0;
	auto fromBB0ReachablePred = [this](BasicBlock &BB) {
		return !exitBBs.contains(&BB);
	};
	collectBlocks(BB0, blocksReachableFromBB0WithoutExit0,
				  fromBB0ReachablePred);
	bool hasAnyBetweenExitBBReachableFromBB0 = false;
    for (auto *BB: betweenExitBBs) {
		if (blocksReachableFromBB0WithoutExit0.contains(BB)) {
			hasAnyBetweenExitBBReachableFromBB0 = true;
			break;
		}
	}

#ifdef LowerPhisToSelectInRegionContext_DEBUG
	auto &OS = dbgs();
	OS << "blocksReachableFromBB0WithoutExit0:\n";
	for (auto bb : blocksReachableFromBB0WithoutExit0) {
		OS << "    ";
		bb->printAsOperand(OS);
		OS << "\n";
	}
#endif
	if (!hasAnyBetweenExitBBReachableFromBB0)
		return false; // nothing to unswitch
	
	// first we have to construct the blocks for noE0 path, and update successors in terminators
	// and prune incoming blocks in phis
	SmallVector<BasicBlock*> blocksForBB0Path;
	SmallVector<DominatorTree::UpdateType> DTUpdates;
	auto newBBIp = exitBBs[0]->getIterator();
	auto & F = *BB0.getParent();
	for (auto *bb: reverse(allBBsOfRegion)) {
		// dbgs() << "blocksReachableFromBB0WithoutExit0_unswitch ";
		// bb->printAsOperand(dbgs());
		// dbgs() << "\n";
		if (bb == exitBBs[0]) {
			// keep as is
			continue;
		} else if (betweenExitBBs.contains(bb) &&
				   blocksReachableFromBB0WithoutExit0.contains(bb)) {
			// this block needs a new variant which will be private to path not
			// containing exit0
			auto newBB = CloneBasicBlock(bb, VMap, ".noE0");
			VMap[bb] = newBB;
			F.insert(newBBIp, newBB);
			blocksForBB0Path.push_back(newBB);
			for (auto *pred : predecessors(bb)) {
				bool isForE0Path =
					pred == exitBBs[0] ||
					blocksReachableFromBB0WithoutExit0.contains(pred);
				for (const auto &[phi, phiNew] :
					 zip(bb->phis(), newBB->phis())) {
					if (isForE0Path) {
						// preserve only in original block for path with e0
						phiNew.removeIncomingValue(pred, false);
					} else {
						// preserve only in new block for path without e0
						phi.removeIncomingValue(pred, false);
					}
				}
				if (!isForE0Path) {
					pred->getTerminator()->replaceSuccessorWith(bb, newBB);
					DTUpdates.push_back({DominatorTree::Delete, pred, bb});
					DTUpdates.push_back({DominatorTree::Insert, pred, newBB});
				}
			}
			bb = newBB;
		}
		// case for blocks topologically before exit0 or after exit1 or newBB
		SetVector<BasicBlock*> sucs;
		sucs.insert_range(successors(bb));
		for (auto * suc: sucs) {
			auto repl = VMap.find(suc);
			if (repl != VMap.end()) {
				// replace with a variant for path not containing exit0
				auto newSuc = static_cast<BasicBlock*>(&*repl->second);
				bb->getTerminator()->replaceSuccessorWith(suc, newSuc);
				DTUpdates.push_back({DominatorTree::Delete, bb, suc});
				DTUpdates.push_back({DominatorTree::Insert, bb, newSuc});
			} else {
				assert(!(betweenExitBBs.contains(bb) &&
						 blocksReachableFromBB0WithoutExit0.contains(suc)) &&
					   "we are iterating bottom up if block needs replacement, "
					   "it should already be constructed");
			}
		}
		
	}
	// once we have all blocks constructed we can update phi incoming blocks and values
	for (auto *bb: reverse(blocksForBB0Path)) {
		// iterate new block from top to down
		if (bb->phis().empty())
			continue;
		SetVector<BasicBlock*> preds;
		preds.insert_range(predecessors(bb));
		for (auto * pred: preds) {
			auto predNew = VMap.find(pred);
			if (predNew != VMap.end()) {
				auto newBB = static_cast<BasicBlock*>(&*predNew->second);
				for (auto& phi: bb->phis()) {
					int i = phi.getBasicBlockIndex(pred);
					auto newV = VMap.find(phi.getIncomingValue(i));
					if (newV != VMap.end()) {
						phi.setIncomingValue(i, newV->second);
					}
					phi.setIncomingBlock(i, newBB);
				}
			}
		}
	}
	// exit1 is a special case because the incomming values are not replaced but they are duplicated
	// for each path
	auto e1 = exitBBs[1];
	if (!e1->phis().empty()) {
		SetVector<BasicBlock *> preds;
		preds.insert_range(predecessors(e1));
		for (auto *pred : preds) {
			auto predNew = VMap.find(pred);
			if (predNew != VMap.end()) {
				auto newBB = static_cast<BasicBlock *>(&*predNew->second);
				for (auto &phi : e1->phis()) {
					int i = phi.getBasicBlockIndex(pred);
					auto v = phi.getIncomingValue(i);
					auto newV = VMap.find(phi.getIncomingValue(i));
					if (newV != VMap.end()) {
						v = newV->second;
					}
					assert(phi.getBasicBlockIndex(newBB) < 0);
					phi.addIncoming(v, newBB);
				}
			}
		}
	}
	// :note: allBBsOfRegion must stay in topological order 
	SetVector<BasicBlock*> newAllBBsOfRegion;
	for (auto bb: allBBsOfRegion) {
		if (bb == exitBBs[0]) {
			newAllBBsOfRegion.insert_range(reverse(blocksForBB0Path));
		}
		newAllBBsOfRegion.insert(bb);
	}
	allBBsOfRegion = newAllBBsOfRegion;
	DTU.applyUpdates(DTUpdates);
	DTU.flush();

#ifdef LowerPhisToSelectInRegionContext_DEBUG
	assert(DTU.getDomTree().verify());
	assert(!verifyFunction(F, &dbgs()));
	for (auto exitBB : exitBBs) {
		assert(allBBsOfRegion.contains(exitBB));
	}
#endif
	return true;
}

bool LowerPhisToSelectInRegionContext::blocksReachableFromBB0WithoutExit0_unswitch(llvm::DomTreeUpdater &DTU, SetVector<BasicBlock *>& origSwitchSuccessors) {
	ValueToValueMapTy VMap;
	if (!blocksReachableFromBB0WithoutExit0_unswitch(DTU, VMap)) {
		return false; // nothing to unswitch
	}
	SetVector<BasicBlock *> origSwitchSuccessorsNew;
	for (auto *BB: origSwitchSuccessors) {
		auto newBB = VMap.find(BB);
		if (newBB != VMap.end()) {
			 BB = static_cast<BasicBlock*>(&*newBB->second);
		}
		origSwitchSuccessorsNew.insert(BB);
	}
	origSwitchSuccessors = origSwitchSuccessorsNew;
	return true;
}

bool LowerPhisToSelectInRegionContext::unreachableExits_unswitch(llvm::DomTreeUpdater &DTU, SetVector<BasicBlock *>& origSwitchSuccessors) {
	auto &F = *BB0.getParent();
	SmallVector<BasicBlock*, 2> toRm;

	SmallVector<DominatorTree::UpdateType> updates;
	for (auto *eBB: exitBBs) {
		if (isa<UnreachableInst>(eBB->getTerminator())) {
			assert(eBB->phis().empty());
			assert(&*eBB->begin() == eBB->getTerminator());
			ValueToValueMapTy VMap;
			auto newBB = CloneBasicBlock(eBB, VMap, ".orig");
			F.insert(eBB->getIterator(), newBB);
			SmallVector<BasicBlock*> preds(predecessors(eBB));
			for (auto *pred: preds) {
				if (!isPartOfRegion(*pred)) {
					pred->getTerminator()->replaceSuccessorWith(eBB, newBB);
					updates.push_back({DominatorTree::Delete, pred, eBB});
					updates.push_back({DominatorTree::Insert, pred, newBB});
				}
			}
			toRm.push_back(eBB);
		}
	}
	for (auto eBB: toRm) {
		exitBBs.remove(eBB);
		bbsWhichMustPreservePhis.remove(eBB);
	}
	DTU.applyUpdates(updates);
	return !toRm.empty();
}

void LowerPhisToSelectInRegionContext::print(llvm::raw_ostream &OS) const {
	OS << "LowerPhisToSelectInRegionContext:\nbb0:";
	BB0.printAsOperand(OS);
	OS << "\n";
	OS << "allBBsOfRegion:\n";
	for (auto bb : allBBsOfRegion) {
		OS << "    ";
		bb->printAsOperand(OS);
		OS << "\n";
	}
	OS << "betweenExitBBs:\n";
	for (auto bb : betweenExitBBs) {
		OS << "    ";
		bb->printAsOperand(OS);
		OS << "\n";
	}
	OS << "exits:\n";
	for (auto e : exitBBs) {
		OS << "    ";
		e->printAsOperand(OS);
		OS << "\n";
	}
}

Value *constructBranchConditionToBB(llvm::IRBuilderBase &Builder,
									BasicBlock &SrcBB, BasicBlock &DstBB,
									const SetVector<BasicBlock *> &handleBBs,
									bool ignoreCheckForDstAndHandle) {
	if (!ignoreCheckForDstAndHandle) {
		if (&SrcBB == &DstBB) {
			return Builder.getTrue();
		} else if (handleBBs.contains(&SrcBB)) {
			return Builder.getFalse(); // CFG reached some other handleBB first
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
			auto eq =
				Builder.CreateICmpEQ(sw->getCondition(), c.getCaseValue());
			auto cV = constructBranchConditionToBB(
				Builder, *c.getCaseSuccessor(), DstBB, handleBBs, false);
			res = Builder.CreateSelect(eq, cV, res);
		}
		return res;
	} else {
		llvm_unreachable("NotImplemented: unsupported terminator");
	}
}

Value *constructBranchConditionToBBDirect(llvm::IRBuilderBase &Builder,
										  BasicBlock &SrcBB,
										  BasicBlock &DstBB,
										  std::optional<llvm::Value*> condOverride
									  ) {
	auto t = SrcBB.getTerminator();
	if (auto br = dyn_cast<BranchInst>(t)) {
		if (br->isConditional()) {
			auto C = br->getCondition();
			if (condOverride.has_value()) {
				C = condOverride.value();
			}
			if (br->getSuccessor(0) == &DstBB) {
				if (br->getSuccessor(1) == &DstBB) {
					// SrcBB br C, DstBB, DstBB
					return Builder.getTrue();
				} else {
					// SrcBB br C, DstBB, xBB
					return C;
				}
			} else {
				// SrcBB br C, xBB, DstBB
				assert(br->getSuccessor(1) == &DstBB);
				return Builder.CreateNot(C);
			}
		} else {
			// SrcBB br DstBB
			assert(br->getSuccessor(0) == &DstBB);
			return Builder.getTrue();
		}
	} else if (auto sw = dyn_cast<SwitchInst>(t)) {
		SmallVector<Value *>
			otherBrConditions; // conditions for cases not jumping to DstBB
		SmallVector<Value *>
			brSuccessConditions; // conditions for cases jumping to DstBB
		// if dstIsSwDefault then we have to collect all otherBrConditions
		bool dstIsSwDefault = sw->getDefaultDest() == &DstBB;
		auto C = sw->getCondition();
		if (condOverride.has_value()) {
			C = condOverride.value();
		}

		for (auto &c : sw->cases()) {
			bool isCaseForDstBB = c.getCaseSuccessor() == &DstBB;
			if (isCaseForDstBB || dstIsSwDefault) {
				auto eq =
					Builder.CreateICmpEQ(C, c.getCaseValue());
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
				// switch with case which all leading to the same dst as switch
				// default (which is DstBB)
				res = Builder.getTrue();
			} else {
				// there are some cases which are not leading to DstBB
				Value *brDefault =
					Builder.CreateNot(Builder.CreateOr(otherBrConditions));
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

// static void dfsMineBlocks(BasicBlock &BB, SetVector<BasicBlock *> &foundBBs) {
// 	if (foundBBs.contains(&BB))
// 		return;
// 	foundBBs.insert(&BB);
// 	for (auto *suc : successors(&BB)) {
// 		dfsMineBlocks(*suc, foundBBs);
// 	}
// }

// /*
//  * Create a variant of variable which goes from BB0 to exit1 without passing
//  * trough exit0 (the original CFG block from betweenExitBBs may be in 2 variants
//  * because the original cfg will remain only for exit0 path while exit1 only
//  * path will be replaced with a direct jump BB0->exit1)
//  */
// static Instruction *
// createVariantForExit1Path(LowerPhisToSelectInRegionContext &ctx,
// 						  IRBuilderBase &Builder, Value *V) {
// 	auto vAsI = dyn_cast<Instruction>(V);
// 	if (!vAsI)
// 		return nullptr;
// 	auto existingVariant = ctx.exit1VersionOfValueDependentOnExit0.find(vAsI);
// 	if (existingVariant != ctx.exit1VersionOfValueDependentOnExit0.end())
// 		return existingVariant->second;
// 
// 	auto defBB = vAsI->getParent();
// 	if (defBB != ctx.exitBBs.front() && !ctx.betweenExitBBs.contains(defBB) &&
// 		ctx.exitBBDominatedByBB0[1]) {
// 		// safe to use value as is
// 		return nullptr;
// 	}
// 	// create phi
// 	IRBuilderBase::InsertPointGuard IPG(Builder);
// 	Builder.SetInsertPoint(ctx.exitBBs.back()->getFirstInsertionPt());
// 	PHINode *exit0VerOfVal = Builder.CreatePHI(
// 		vAsI->getType(), pred_size(ctx.exitBBs[1]), vAsI->getName());
// 	ctx.exit1VersionOfValueDependentOnExit0[vAsI] = exit0VerOfVal;
// 	ctx.newPhisInExit1.insert(exit0VerOfVal);
// 	// populate operands of exit0VersionOfVal
// 	for (auto exitPred : predecessors(ctx.exitBBs[1])) {
// 		// auto predBBPos =
// 		// std::find(ctx.allBBsOfRegion.begin(),
// 		// ctx.allBBsOfRegion.end(), exitPred);
// 		if ((exitPred == ctx.exitBBs[0] ||
// 			 ctx.allBBsOfRegion.contains(exitPred))) {
// 			exit0VerOfVal->addIncoming(vAsI, exitPred);
// 		} else {
// 			// the value will be unused, the final select
// 			// will select value not coming from exitBB0
// 			// section
// 			exit0VerOfVal->addIncoming(
// 				PoisonValue::get(exit0VerOfVal->getType()), exitPred);
// 		}
// 	}
// 	if (!is_contained(predecessors(ctx.exitBBs[1]), &ctx.BB0)) {
// 		// because jump will be added later
// 		exit0VerOfVal->addIncoming(PoisonValue::get(exit0VerOfVal->getType()),
// 								   &ctx.BB0);
// 	}
// 	return exit0VerOfVal;
// }

/**
 * For a exit block which have pred. outside of region, create phi to assert def
 * before use in this block for final select
 */
//static Instruction *
//createPhiForNoDominatedSelectedUse(LowerPhisToSelectInRegionContext &ctx,
//								   BasicBlock &BB, Instruction &fromRegionVal,
//								   Value *defaultVal,
//								   Value *defaultValForExit1 = nullptr) {
//	if (&BB == fromRegionVal.getParent())
//		return &fromRegionVal;
//	auto &Builder = ctx.Builder;
//	assert(
//		!ctx.betweenExitBBs.contains(&BB) &&
//		"exit0 section should not be lowered, BB0 section is dominated by BB0");
//	bool isE1 = ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1];
//	bool needPhiAlsoInExit0 =
//		!ctx.exitBBDominatedByBB0[0] && (isE1 || ctx.isInExit0Section(BB));
//	assert(fromRegionVal.getParent() != ctx.exitBBs[0]);
//	assert(fromRegionVal.getParent() != &BB);
//
//	if (isE1) {
//		auto existingPhi = ctx.phisForInstNotDominatingE1.find(&fromRegionVal);
//		if (existingPhi != ctx.phisForInstNotDominatingE1.end()) {
//			return existingPhi->second;
//		}
//	}
//	if (!defaultValForExit1) {
//		defaultValForExit1 = defaultVal;
//	}
//
//	Instruction *fromRegionValVariantForExit0 = &fromRegionVal;
//	if (needPhiAlsoInExit0) {
//		if (fromRegionValVariantForExit0->getParent() != ctx.exitBBs[0]) {
//			auto existingPhi =
//				ctx.phisForInstNotDominatingE0.find(&fromRegionVal);
//			if (existingPhi == ctx.phisForInstNotDominatingE0.end()) {
//				auto &bbE0 = *ctx.exitBBs[0];
//				IRBuilder<>::InsertPointGuard g(Builder);
//				Builder.SetInsertPoint(bbE0.getFirstInsertionPt());
//				auto phi = Builder.CreatePHI(fromRegionVal.getType(),
//											 pred_size(&bbE0));
//				bool bb0addedAsPred = false;
//				for (auto *pred : predecessors(&bbE0)) {
//					// :attention: at this point we are constructing an updated
//					// phi, but the
//					//             predecessors are still in old version (all
//					//             predecessors from region will be replaced by
//					//             BB0 later)
//					if (pred == &bbE0) {
//						phi->addIncoming(phi, &bbE0);
//					} else if (ctx.isPartOfRegion(*pred)) {
//						if (!bb0addedAsPred) {
//							phi->addIncoming(&fromRegionVal, &ctx.BB0);
//							bb0addedAsPred = true;
//						}
//					} else {
//						phi->addIncoming(defaultVal, pred);
//					}
//				}
//				phi->setName(fromRegionVal.getName() + ".inE0ForE1");
//				ctx.phisForInstNotDominatingE0[&fromRegionVal] = phi;
//				fromRegionValVariantForExit0 = phi;
//			} else {
//				fromRegionValVariantForExit0 = existingPhi->second;
//			}
//		}
//		if (!isE1 && !ctx.betweenExitBBs.contains(&BB)) {
//			return fromRegionValVariantForExit0;
//		}
//	}
//
//	assert(&BB == &ctx.BB0 ||
//		   (ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1]) ||
//		   (!needPhiAlsoInExit0 && &BB == ctx.exitBBs[0]));
//	// his is exitBBs[1] and it needs to merge phi for values from region
//	// blocks, region blocks dominated by exitBBs[0] and for predecessors not
//	// dominated by BB0
//	IRBuilder<>::InsertPointGuard g(Builder);
//	Builder.SetInsertPoint(BB.getFirstInsertionPt());
//	// assert((&BB == &ctx.BB0 || ctx.exitBBs.contains(&BB)) && "only bb0 or
//	// exits may required new phis");
//	auto phi = Builder.CreatePHI(fromRegionVal.getType(), pred_size(&BB));
//	bool bb0Added = false;
//	for (auto *pred : predecessors(&BB)) {
//		if (ctx.isPartOfRegion(*pred)) {
//			if (pred != &ctx.BB0 &&			   //
//				!ctx.exitBBs.contains(pred) && //
//				!ctx.betweenExitBBs.contains(pred)) {
//				// if it is not a block which will remain after transformation
//				continue;
//			}
//			// add if it will be preserved after this transformation is
//			// done, else ignore
//			if (ctx.isInExit0Section(*pred)) {
//				phi->addIncoming(fromRegionValVariantForExit0, pred);
//			} else {
//				phi->addIncoming(&fromRegionVal, pred);
//			}
//		} else {
//			// value from outside of the region, use default value, as this will
//			// hold no active value
//			phi->addIncoming(defaultValForExit1, pred);
//		}
//		if (pred == &ctx.BB0) {
//			bb0Added = true;
//		}
//	}
//	if (!bb0Added) {
//		// because BB0 is added as predecessor
//		phi->addIncoming(&fromRegionVal, &ctx.BB0);
//	}
//	if (ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1])
//		ctx.newPhisInExit1.insert(phi);
//
//	ctx.phisForInstNotDominatingE1[&fromRegionVal] = phi;
//	return phi;
//}

// construct enFromPred for path from BB0 (excluding path through exitBBs[0] if there are multiple exits)
// :note: always constructed at the end of BB0 (bb0SelectInsertPos)
static void lowerPhisOfBlockInRegion_construct_enFromPred(LowerPhisToSelectInRegionContext &ctx, BasicBlock &BB,
		const SetVector<BasicBlock *>& BBPredecessors,
		SmallVector<Value *> &enFromPredecessor,
		SmallVector<bool> &shouldUpdateValueForPred, // false for predecessors outside of region
		bool &canCompletlyRemovePhi) {
	assert(!isa<UnreachableInst>(BB.getTerminator()));
	auto &Builder = ctx.Builder;
	auto &BB0 = ctx.BB0;
	// because previous phi was not yet lowered which means that it will have to stay and this path merges bb0 and bb.exit0 paths

	// errs() << "lowerPhisOfBlockInRegion_construct_enFromPred " << BB << "\n";
	//auto isPredecessorOutsideOfRegion = [&BB0, &ctx, &BB](BasicBlock *pred) {
	//	return pred != &BB0 &&
	//		   (!ctx.allBBsOfRegion.contains(
	//				pred) ||  // case of bb0, exits with predec from outside
	//			pred == &BB); // case of exit being self loop
	//};
	//bool needsPhiForRegionValues = &BB != &BB0 && any_of(BBPredecessors, isPredecessorOutsideOfRegion);
	// assert(ctx.blocksReachableFromBB0WithoutExit0.empty());
	assert(!ctx.betweenExitBBs.contains(&BB) && 
		"the betweenExitBBs should now be all dominated by exitBBs[0] and we should not lower phis in them, "
		"nor need them for any select condition");

	// IRBuilderBase::InsertPointGuard IPG(Builder);
	Builder.SetInsertPoint(ctx.bb0SelectInsertPos);
			
	for (BasicBlock *pred : BBPredecessors) {
		if (pred != &BB0 && (
			!ctx.allBBsOfRegion.contains(pred) || // case of bb0, exits with predec from outside
			pred == &BB || // case of exit being self loop	
			ctx.isInExit0Section(*pred)
		)) {
			// :note: allBBsOfRegion has to be checked because exit block are
			// allowed to have predecessors outside of the region :note: for BB0
			// we want to perform the update if there are multiple paths in CFG
			//        from BB0 to BB not leading trough blocks in
			//        bbsWhichMustPreservePhis

			canCompletlyRemovePhi = false;
			shouldUpdateValueForPred.push_back(false);
			enFromPredecessor.push_back(nullptr);
			// for this predecessor we do not have to generate select
			// tree because we use original phi
			continue;
		}
		//bool _shouldUpdateValueForPred = true;
		//bool predValWillStay = ctx.isInExit0Section(*pred);
		//if (predValWillStay) {
		//	canCompletlyRemovePhi = false;
		//	// [todo] rm blocksReachableFromBB0WithoutExit0 is pruned
		//	// if (!ctx.blocksReachableFromBB0WithoutExit0.contains(pred)) {
		//	// 	_shouldUpdateValueForPred = false;
		//	// }
		//}
		shouldUpdateValueForPred.push_back(true); 
		//IRBuilderBase::InsertPointGuard IPG(Builder);
		std::optional<Value *> CondOverride;
		if (ctx.isInExit0Section(*pred)) {
		 	// the bbEn condition is build only for exit1 path, )
			enFromPredecessor.push_back(nullptr);
			continue;
		 }
		
		
		// resolve condition which is 1 if the block is entered from some
		// predecessor
		//errs() << "br." + pred->getName() + ".enFor." + BB.getName() << "\n";

		//if (ctx.isInExit0Section(*pred)) {
		//	Builder.SetInsertPoint(ctx.bbExit1SelectInsertPos);
		//	// if the condition value depends on the exitBB0 we have to
		//	// substitute it with the the phi constructed in the exitBB1
		//	// constructed for this term
		//	auto predTerm = pred->getTerminator();
		//	if (auto Br = dyn_cast<BranchInst>(predTerm)) {
		//		if (Br->isConditional()) {
		//			CondOverride = Br->getCondition();
		//		}
		//	} else if (auto Sw = dyn_cast<SwitchInst>(predTerm)) {
		//		CondOverride = Sw->getCondition();
		//	}
		//	//if (CondOverride.has_value()) {
		//	//	if (auto exit0VersionOfVal = createVariantForExit1Path(ctx, Builder, CondOverride.value())) {
		//	//		CondOverride = exit0VersionOfVal;
		//	//	}
		//	//}
		//} else {
		//	Builder.SetInsertPoint(ctx.bb0SelectInsertPos);
		//}

		
		auto jmpFromPredEn =
			constructBranchConditionToBBDirect(Builder, *pred, BB, CondOverride);

		Value *enFromPred;
		if (pred == &BB0) {
			// no need to and for en for BB0
			enFromPred = jmpFromPredEn;
		} else {
			// need to and with en for predecessor
			auto _predEn = ctx.bbEnableCache.find(pred);
			assert(_predEn != ctx.bbEnableCache.end());
			auto predEn = _predEn->second;
			if (predEn) {
				// errs() << "predEn query: " << *predEn << "\n";
				enFromPred = Builder.CreateAnd(predEn, jmpFromPredEn,
										   "br." + pred->getName() + ".enFor." +
											   BB.getName());
			} else {
				assert(pred->getTerminator()->getNumSuccessors() == 1);
				// all jumps from BB0 so far were unconditional
				enFromPred = jmpFromPredEn;
			}
		}
		
		if (auto cI = dyn_cast<Instruction>(enFromPred)) {
			assert(cI->getParent());
			if (!cI->hasName()) {
				cI->setName("fewExitSw.sucSel.en." + pred->getName() + "." +
							BB.getName());
			}
		}

		enFromPredecessor.push_back(enFromPred);
	}
	assert(enFromPredecessor.size() == BBPredecessors.size());
	assert(shouldUpdateValueForPred.size() == BBPredecessors.size());
}

//struct PhiUpdateMeta {
//	Value *enFromPredBB;
//	BasicBlock * predBB;
//	bool shouldUpdateValueForPred;
//};

// Construct selects to emulate original phi behavior
// :attention: phiReplacements must be preallocated initialized to nullptrs
static void lowerPhisOfBlockInRegion_construct_selectsInBB0(LowerPhisToSelectInRegionContext &ctx,
		BasicBlock & BB, const SmallVector<PHINode *> &bbPhis, //bool isPhiWithVersionForExit0,
		const SetVector<BasicBlock *>& BBPredecessors,
		const SmallVector<Value *> &enFromPredecessor,
		const SmallVector<bool> &shouldUpdateValueForPred, // false for predecessors outside of region
		SmallVector<Value *>& phiReplacingSelectsInBB0
	) {
#ifdef LowerPhisToSelectInRegionContext_DEBUG
	dbgs() << "construct_selects: " << BB << "\n";
	assert(enFromPredecessor.size() == BBPredecessors.size());
	assert(enFromPredecessor.size() == shouldUpdateValueForPred.size());
	assert(bbPhis.size() == phiReplacingSelectsInBB0.size());
	assert(is_contained(shouldUpdateValueForPred, true) && "If no value should be updated, this function should not be called");
#endif
	auto &Builder = ctx.Builder;
	Builder.SetInsertPoint(ctx.bb0SelectInsertPos);
	// build a SelectInst tree from enFromPredecessor and phi operands
	//bool bbIsNotDominatedByBB0 = &BB != &ctx.BB0 && !ctx.isProperlyDominatedByBB0(BB);
	for (const auto &[_en, pred, shouldUpdate] :
		 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
		if (!shouldUpdate) {
			continue;
		}
		Value * en = _en;
		assert(en);
		//// :note: en may not be value available in BB because it is defined in BB0 and BB0 may not dominate this block
		//if (bbIsNotDominatedByBB0) {
		//	if (auto enAsI = dyn_cast<Instruction>(en)) {
		//		en = createPhiForNoDominatedSelectedUse(ctx, BB, *enAsI,
		//												Builder.getFalse());
		//		if (!enAsI->hasName()) {
		//			enAsI->setName("fewExitSw.sucSel.en." + pred->getName() +
		//						   "." + BB.getName());
		//		}
		//	}
		//}

		//if (!en) {
		//	assert(ctx.isInExit0Section(*pred) && "This could happen only for BBs in after exit0 section which are dominated by exit0");
		//	continue;
		//}
		//if (isPhiWithVersionForExit0 && ctx.isInExit0Section(*pred)) {
		//	continue; // this operand will not be part of select tree and
		//			  // will stay in phi as is
		//}
		bool predNotDominatedByBB0 = pred != &ctx.BB0 && (!ctx.allBBsOfRegion.contains(pred) || !ctx.isDominatedByBB0(*pred));
		assert(!predNotDominatedByBB0 && "For such predecessors we are not supposed to update at all");
		size_t phiIndex = 0;
		for (auto &_phi : bbPhis) {
			auto &phi = *_phi;
			Value *prevVal = phiReplacingSelectsInBB0[phiIndex];
			Value *val = phi.getIncomingValueForBlock(pred);
			//if (predNotDominatedByBB0) {
			//	if (auto valAsI = dyn_cast<Instruction>(val)) {
			//		val = createPhiForNoDominatedSelectedUse(ctx, *pred, *valAsI, PoisonValue::get(valAsI->getType()));
			//	}
			//}
			//if (bbIsNotDominatedByBB0) {
			//	if (auto valAsI = dyn_cast<Instruction>(val)) {
			//		val = createPhiForNoDominatedSelectedUse(ctx, BB, *valAsI, PoisonValue::get(valAsI->getType()));
			//	}
			//}
			if (prevVal == nullptr) {
				// the case of the first pred, which we will use as a default
				phiReplacingSelectsInBB0[phiIndex] = val;
			} else {
				// all other preds
				assert(prevVal->getType() == phi.getType());
				assert(val->getType() == phi.getType());
#ifndef NDEBUG
				if (ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1]) {
					assert(
						Builder.GetInsertBlock() == &ctx.BB0 &&
						"Only section directly after BB0 is removed, exit0,1 "
						"and block between them will remain,"
						" so if we are building value for it we must be in it");
				}
#endif
				// :note: build a select tree which will select the value as phis in BB0 section 
				// (and a part of the phi in exit BB if this is exit BB)
				phiReplacingSelectsInBB0[phiIndex] =
					Builder.CreateSelect(en, val, prevVal);
			}
			#ifdef LowerPhisToSelectInRegionContext_DEBUG
				dbgs() << "phiReplacingSelectsInBB0: " << phi << " -> " << *phiReplacingSelectsInBB0[phiIndex] << "\n";
			#endif
			phiIndex++;
		}
	}
#ifdef LowerPhisToSelectInRegionContext_DEBUG
	dbgs() << "construct_selects after: " << BB << "\n";
	assert(!is_contained(phiReplacingSelectsInBB0, nullptr));
#endif
}

//static void lowerPhisOfBlockInRegion_handePhiUpdate_exit1(
//	LowerPhisToSelectInRegionContext &ctx, BasicBlock &BB,
//	const SmallVector<PHINode *> &bbPhis,
//	const SetVector<BasicBlock *> &BBPredecessors,
//	const SmallVector<Value *> &enFromPredecessor,
//	const SmallVector<bool>
//		&shouldUpdateValueForPred, // false for predecessors outside of region
//	const SmallVector<Value *> &phiReplacements) {
//
//	auto &BB0 = ctx.BB0;
//	auto &Builder = ctx.Builder;
//	// update original phis to use values for bb0 to exitbb1 path
//	// set unused phi operands to PoisonValue (they will be implemented unsing
//	// final select) :note: select for those values is already constructed and
//	// available in  phiReplacements
//	for (auto *phi : bbPhis) {
//		for (const auto &[en, pred, shouldUpdate] :
//			 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
//			if (!shouldUpdate) {
//				continue;
//			}
//			auto predIsForExit0Section = ctx.isInExit0Section(*pred);
//			auto predI = phi->getBasicBlockIndex(pred);
//			if (predIsForExit0Section) {
//				// the phi will exits only for select from blocks in exit0
//				// section
//			} else {
//				phi->setIncomingValue(
//					predI,
//					PoisonValue::get(phi->getType())); // we will use select
//													   // to decide this
//				phi->setIncomingBlock(predI, &BB0);
//			}
//		}
//	}
//	// IRBuilderBase::InsertPointGuard IPG(Builder);
//	// construct select for selection between exit0-exit1 paths
//	auto exit0enInBB0 = ctx.bbEnableCache.find(ctx.exitBBs[0]);
//	assert(exit0enInBB0 != ctx.bbEnableCache.end() &&
//		   "We were walking topologically sorted blocks and "
//		   "now we are at ctx.exitBBs[1] we had to see ctx.exitBBs[0] "
//		   "already");
//	auto exit0enInE1 = exit0enInBB0->second;
//	auto mayNeedPhiForInput = !ctx.isProperlyDominatedByBB0(BB);
//	if (mayNeedPhiForInput &&
//		!ctx.newPhisInExit1.contains(dyn_cast<PHINode>(exit0enInE1))) {
//		// if block has predecessor outside of region we have to add phi for
//		// en, because en is generated in region and potentially does not
//		// dominate BB
//		if (auto exit0enI = dyn_cast<Instruction>(exit0enInE1)) {
//			exit0enInE1 = createPhiForNoDominatedSelectedUse(
//				ctx, BB, *exit0enI, Builder.getTrue(), Builder.getFalse());
//		}
//	}
//	size_t phiIndex = 0;
//	for (auto *phi : bbPhis) {
//		auto replacement = phiReplacements[phiIndex];
//		if (!replacement)
//			continue;
//		if (mayNeedPhiForInput) {
//			auto replI = dyn_cast<Instruction>(replacement);
//			if (replI && replI->getParent() != &BB && //
//				!ctx.newPhisInExit1.contains(dyn_cast<PHINode>(replacement))) {
//				replacement = createPhiForNoDominatedSelectedUse(
//					ctx, BB, *replI, PoisonValue::get(phi->getType()));
//			}
//		}
//		Builder.SetInsertPoint(ctx.bbExit1SelectInsertPos);
//		auto finalReplacement = Builder.CreateSelect(exit0enInE1, phi, replacement);
//		finalReplacement->takeName(phi);
//#ifdef LowerPhisToSelectInRegionContext_DEBUG
//		dbgs() << "finalReplacement: " << *finalReplacement << "\n";
//#endif
//		phi->replaceUsesWithIf(
//			finalReplacement, [finalReplacement, &ctx](Use &U) {
//				auto *User = U.getUser();
//				if (auto userPhi = dyn_cast<PHINode>(User)) {
//					return !ctx.newPhisInExit1.contains(userPhi);
//					// if (userPhi->getParent() == &BB)
//					//	return is_contained(bbPhis, userPhi);
//				}
//				return User != finalReplacement;
//			});
//		++phiIndex;
//	}
//}

static void lowerPhisOfBlockInRegion_handePhiUpdate(
	LowerPhisToSelectInRegionContext &ctx, BasicBlock &BB, //const SetVector<BasicBlock*> & preservedPredecessors,
	const SmallVector<PHINode *> &bbPhis, /*bool isPhiWithVersionForExit0,*/
	bool canCompletlyRemovePhi, const SetVector<BasicBlock *> &BBPredecessors,
	const SmallVector<Value *> &enFromPredecessor,
	const SmallVector<bool>
		&shouldUpdateValueForPred, // false for predecessors outside of region
	const SmallVector<Value *> &phiReplacements) {
#ifndef NDEBUG
	for (auto *_phi : bbPhis) {
		assert(!ctx.newPhisInExit1.contains(_phi));
	}
	//assert(!is_contained(phiReplacements, nullptr));
	assert(BBPredecessors.size() == enFromPredecessor.size());
	assert(BBPredecessors.size() == shouldUpdateValueForPred.size());
	assert(phiReplacements.size() == bbPhis.size());
#endif
	auto &BB0 = ctx.BB0;
	if (canCompletlyRemovePhi) {
		// replace phis with SelectInst, this may happen if:
		// * 1 exit which is dominated by BB0 or is BB0
		// * or if all incoming values are available after BB0
		size_t phiIndex = 0;
		for (auto *phi : bbPhis) {
			Value *replacement = phiReplacements[phiIndex];
			if (replacement) {
				assert(replacement->getType() == phi->getType());
				replacement->takeName(phi);
				phi->replaceAllUsesWith(replacement);
				phi->eraseFromParent();
			}
			// assert(loweredPhiCache.find(&phi) == loweredPhiCache.end());
			// loweredPhiCache[&phi] = replacement;
			phiIndex++;
		}
	//} else if (ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1]) {
	//	lowerPhisOfBlockInRegion_handePhiUpdate_exit1(
	//		ctx, BB, bbPhis, BBPredecessors, enFromPredecessor,
	//		shouldUpdateValueForPred, phiReplacements);
	} else {
		bool bb0seen = false;
		//bool isExit1 = ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1];
		//auto mayNeedPhiForInput = !ctx.isProperlyDominatedByBB0(BB);
		//auto & Builder = ctx.Builder;
		for (const auto &[en, pred, shouldUpdate] :
			 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
			if (!shouldUpdate) {
				continue;
			}
			if (pred == &BB0) {
				size_t phiIndex = 0;
				for (auto *phi : bbPhis) {
					auto replacement = phiReplacements[phiIndex];
					if (replacement) {
						//if (mayNeedPhiForInput) {
						//	if (auto rI = dyn_cast<Instruction>(replacement)) {
						//		replacement = createPhiForNoDominatedSelectedUse(
						//			ctx, BB, *rI, Builder.getTrue(), Builder.getFalse());
						//	}
						//}
						phi->setIncomingValueForBlock(pred, replacement);
					} else {
						assert(phi->getIncomingValueForBlock(pred) == phi);
					}
					++phiIndex;
				}
				bb0seen = true;
			} else if (ctx.isInExit0Section(*pred)) {
			} else {
				// this predecessor is handled by already existing selects in
				// phiReplacements
				for (auto *phi : bbPhis) {
					// this operand is lowered to selects in exitBBs[1]
					// this path in CFG will handle only paths trough exitBBs[0]
					phi->removeIncomingValue(pred);
				}
			}
		}
		if (ctx.exitBBs.contains(&BB) && !bb0seen) {
			// from BB0 section predecessor will be replaced by the jump directly from the BB0
			size_t phiIndex = 0;
			for (auto *phi : bbPhis) {
				auto replacement = phiReplacements[phiIndex];
				phi->addIncoming(replacement, &BB0);
				++phiIndex;
			}
		}
		// SmallVector<PHINode *> mergePhis(bbPhis.size(), nullptr);
		//{
		//	size_t exit1PredCnt = pred_size(ctx.exitBBs[1]);
		//	size_t phiI = 0;
		//	IRBuilderBase::InsertPointGuard IG(Builder);
		//	Builder.SetInsertPoint(ctx.exitBBs[1]->getFirstInsertionPt());
		//	for (auto *_phi : bbPhis) {
		//		auto &phi = *_phi;
		//		PHINode *mergePhi = Builder.CreatePHI(phi.getType(),
		//exit1PredCnt, phi.getName());
		//		// ctx.exit1VersionOfValueDependentOnExit0[&phi] = mergePhi;
		//		// ctx.phiInExit1ForValuesFromExit0[&phi] = mergePhi;
		//		ctx.newPhisInExit1.insert(mergePhi);
		//		mergePhis[phiI] = mergePhi;
		//		phiI++;
		//	}
		// }
		//// populate operands of mergePhis
		////auto thisBBPos = std::find(ctx.allBBsOfRegion.begin(),
		///ctx.allBBsOfRegion.end(), &BB); /assert(thisBBPos !=
		///ctx.allBBsOfRegion.end());
		// for (auto exitPred: predecessors(ctx.exitBBs[1])) {
		//	//auto predBBPos = std::find(ctx.allBBsOfRegion.begin(),
		//ctx.allBBsOfRegion.end(), exitPred); 	if ((exitPred == ctx.exitBBs[0]
		//|| 		 ctx.betweenExitBBs.contains(exitPred))
		//		//(predBBPos != ctx.allBBsOfRegion.end() && // check that
		//exitPred is dominated by
		//		// predBBPos <= thisBBPos)
		//	 ) {
		//		for (const auto &[phi, mergePhi] : zip(bbPhis, mergePhis)) {
		//			// :attention: this is not final as the exitPred may not be
		//dominated by BB
		//			//             and it must be checked later once DT is
		//updated
		//			//             :see:
		//lowerPhisOfBlockInRegion_finalizeExit0AndBB0PathSelect
		//			mergePhi->addIncoming(phi, exitPred);
		//		}
		//	} else {
		//		// the value will be unused, the final select will select value
		//not coming from exitBB0 section 		for (auto *mergePhi : mergePhis) {
		//			mergePhi->addIncoming(PoisonValue::get(mergePhi->getType()),
		//exitPred);
		//		}
		//	}
		// }
	}
	//  else {
	// 	assert(ctx.exitBBs.size() == 1 && &BB == ctx.exitBBs[0]);
	// 	
	// 	// update incoming values for selected operands
	// 	size_t phiIndex = 0;
	// 	for (auto *phi : bbPhis) {
	// 		for (const auto &[en, pred, shouldUpdate] :
	// 			 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
	// 			if (!shouldUpdate) {
	// 				continue;
	// 			}
	// 			auto predI = phi->getBasicBlockIndex(pred);
	// 			auto replacement = phiReplacements[phiIndex];
	// 			if (replacement)
	// 				phi->setIncomingValue(predI, replacement);
	// 			phi->setIncomingBlock(predI, &BB0);
	// 		}
	// 		++phiIndex;
	// 	}
	// }
}


// :param BB: the block for which to lower the phis
// :returns: the enable condition for a given block
Value *lowerPhisOfBlockInRegion(LowerPhisToSelectInRegionContext &ctx,
								BasicBlock &BB) {
	// PHINode *useValFromPhi = nullptr;
	// if (predsWhichWillBePreserved.size() > 1) {
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
	// }
	if (isa<UnreachableInst>(BB.getTerminator())) {
		assert(BB.phis().empty());
		return nullptr;
	}

	auto &Builder = ctx.Builder;
	auto &BB0 = ctx.BB0;
	{
		auto curEn = ctx.bbEnableCache.find(&BB);
		assert(curEn == ctx.bbEnableCache.end());
	}
	if (ctx.betweenExitBBs.contains(&BB)) {
		// :note: now every block in betweenExitBBs should be dominated by exitBBs[0] and
		//        we are lowring only paths from BB0 to exitBBs
		return nullptr;
	}
	
	//bool bbIsExit0 = ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[0];
	//bool isPhiWithVersionForExit0;
	//if (ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1]) {
	//	// insert point will have to be set to bbExit1 because
	//	// some values will come from the bbExit0
	//	Builder.SetInsertPoint(ctx.bbExit1SelectInsertPos);
	//	// construct select only for incoming values from the
	//	// {allBBsOfRegion - betweenExitBBs}, keep rest as is do not update
	//	// uses
	//	isPhiWithVersionForExit0 = true;
	//} else {
	//	Builder.SetInsertPoint(ctx.bb0SelectInsertPos);
	//	isPhiWithVersionForExit0 = false;
	//}
	SmallVector<Value *> enFromPredecessor;
	SmallVector<bool> shouldUpdateValueForPred; // false for predecessors outside of region
	SetVector<BasicBlock *> BBPredecessors(pred_begin(&BB), pred_end(&BB));
	shouldUpdateValueForPred.reserve(BBPredecessors.size());
	bool canCompletlyRemovePhi = true;
	assert(&BB != &BB0 && "Can not remove phis in BB0 because if this is the loop the phi in header must remain");
	
	// The blocks which are part of betweenExitBBs will stay, but all phis in them need special handling.
	// Such phis will exits in 2 variants, the original will remain values only for betweenExitBBs and exitBBs
	// And second variant which will be lowered to select in BB0.
	// To merge these variant a phi has to be constructed in exitBBs[1],
	// :see: :class:`LowerPhisToSelectInRegionContext` phiInExit1ForValuesFromExit0

	lowerPhisOfBlockInRegion_construct_enFromPred(
		ctx, BB, BBPredecessors, enFromPredecessor, shouldUpdateValueForPred,
		canCompletlyRemovePhi);

	SmallVector<PHINode *> bbPhis;// backup needed because we may potentially create new phis
	for (auto & phi: BB.phis()) {
		if (!ctx.newPhisInExit1.contains(&phi))
			bbPhis.push_back(&phi);
	}
	//bool isExit1 = ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1];
	SmallVector<Value *> phiReplacingSelectsInBB0(bbPhis.size(), nullptr);
	if (is_contained(shouldUpdateValueForPred, true)) {
		lowerPhisOfBlockInRegion_construct_selectsInBB0(ctx, BB, bbPhis,
			//isPhiWithVersionForExit0 && !isExit1, // in exit1 we should not lower phis
			// because values may be coming from exit0 section which does not dominate exit1
			BBPredecessors, enFromPredecessor, shouldUpdateValueForPred,
			phiReplacingSelectsInBB0);
	}

	lowerPhisOfBlockInRegion_handePhiUpdate(
		ctx, BB, 
		bbPhis, /*isPhiWithVersionForExit0,*/ canCompletlyRemovePhi,
		BBPredecessors, enFromPredecessor, shouldUpdateValueForPred,
		phiReplacingSelectsInBB0);

	if (&BB == ctx.exitBBs.back()) { //  && !ctx.isBlockExit1WithConditionRequired(BB)
		// BBEn is nor required for any successor
		return nullptr;
	}
	Builder.SetInsertPoint(ctx.bb0SelectInsertPos);
	// create enable condition for this block (1 if block is reached without visiting exitBBs[0] first)
	Value *BBEn; //: note: for paths which do not lead trough exitBBs[0]
	SmallVector<Value *> _enFromPredecessor(enFromPredecessor);
	// delete enable for block predecessor which will be preserved
	llvm::erase_if(_enFromPredecessor, [](Value *v) { return v == nullptr; });
	if (_enFromPredecessor.empty()) {
		BBEn = nullptr; // this block is between exit blocks and have just same
						// blocks or exit blocks as predecessor
		// none of he predecessors was removed and phis were not removed or
		// updated as well the return value should never be used because this
		// block will not be removed as well
	} else {
		BBEn = Builder.CreateOr(_enFromPredecessor);
	}
	// errs() << "lowerPhisOfBlockInRegion done " << BB.getName() << "\n";
	if (BBEn) {
		if (auto cI = dyn_cast<Instruction>(BBEn)) {
			assert(cI->getParent());
		}
	}
	ctx.bbEnableCache[&BB] = BBEn;
	return BBEn;
}
}
