#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>

#include <cassert>
#include <optional>

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
#include <llvm/Support/ErrorHandling.h>

using namespace llvm;

namespace hwtHls {

void collectBlocks(BasicBlock &src, llvm::SetVector<llvm::BasicBlock *> &seen,
				   std::function<bool(BasicBlock &)> predicate) {
	for (auto suc: successors(&src)) {
		if (seen.contains(suc)) {
			return;
		}			
		if (!predicate(*suc))
			return;
		seen.insert(suc);
		collectBlocks(*suc, seen, predicate);
	}		
}

bool LowerPhisToSelectInRegionContext::analyze() {
	// auto exitBBAfterPhis = exitBB.getFirstNonPHIIt();
	bbsWhichMustPreservePhis.insert(exitBBs.begin(), exitBBs.end());
	bbsWhichMustPreservePhis.insert(&BB0);
	topologicalSortForBlocks(allBBsOfRegion, &BB0);
	// errs() << "allBBsOfRegion\n";
	// for (auto *BB: allBBsOfRegion) {
	// 	errs() << "     ";
	// 	BB->printAsOperand(errs());
	// 	errs() << "\n";
	// }
	if (exitBBs.size() > 1) {
		assert(exitBBs.size() == 2);
		assert(!exitBBs.contains(&BB0) && "This is required because IP for select/phis would not be clearly defined");
		// assert that the exitBB0 is topologically before exitBB1
		if (hasSuccessorFromRegionExceptForUnreachable(exitBBs[1])) {
			// swap items in exitBBs
			auto e1 = exitBBs.pop_back_val();
			auto e0 = exitBBs.pop_back_val();
			// errs() << "LowerPhisToSelectInRegionContext::analyze\n";
			// e0->printAsOperand(errs());
			// errs() << "    " << hasSuccessorFromRegionExceptForUnreachable(e0) << "\n";
			// e1->printAsOperand(errs());
			// errs() << "    " << hasSuccessorFromRegionExceptForUnreachable(e1) << "\n";

			assert((e1 == &BB0 || !hasSuccessorFromRegionExceptForUnreachable(e0)) &&
				   "There should not be any loop between the exit blocks");
			exitBBs.insert(e1);
			exitBBs.insert(e0);
		}
		// localize blocks between exits
		// because we will have to sink part of instructions to exit1
		findBlocksBetweenExitBlocksOfRegion(BB0, allBBsOfRegion, exitBBs,
											betweenExitBBs);
		if (!betweenExitBBs.empty())
			topologicalSortForBlocks(betweenExitBBs);
		for (auto &I : *exitBBs[0]) {
			valuesAfffectedByExit0.insert(&I);
		}
		auto fromBB0ReachablePred = [this](BasicBlock &BB) {
			return !exitBBs.contains(&BB);
		};
		collectBlocks(BB0, blocksReachableFromBB0WithoutExit0,
					  fromBB0ReachablePred);
	}
	if (all_of(allBBsOfRegion,
			   [](BasicBlock *BB) { return BB->phis().empty(); })) {
		if (!hasPredecessorFromRegion(&BB0) || BB0.phis().empty()) {
			return false; // no phis to lower
		}
	}
	return true;
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

static Instruction *
createVariantForExit1Path(LowerPhisToSelectInRegionContext &ctx,
						  IRBuilderBase &Builder, Value *V) {
	if (auto condAsI = dyn_cast<Instruction>(V)) {
		auto existingVariant = ctx.exit1VersionOfValueDependentOnExit0.find(condAsI);
		if (existingVariant !=  ctx.exit1VersionOfValueDependentOnExit0.end())
			return existingVariant->second;
			
		auto defBB = condAsI->getParent();
		if (defBB == ctx.exitBBs.front() ||
			ctx.betweenExitBBs.contains(defBB)) {
			IRBuilderBase::InsertPointGuard IPG(Builder);
			Builder.SetInsertPoint(ctx.exitBBs.back()->getFirstInsertionPt());
			PHINode *exit0VersionOfVal =
				Builder.CreatePHI(condAsI->getType(), pred_size(ctx.exitBBs[1]),
								  condAsI->getName());
			ctx.exit1VersionOfValueDependentOnExit0[condAsI] =
				exit0VersionOfVal;
			ctx.newPhisInExit1.insert(exit0VersionOfVal);
			// populate operands of exit0VersionOfVal
			for (auto exitPred : predecessors(ctx.exitBBs[1])) {
				// auto predBBPos =
				// std::find(ctx.allBBsOfRegion.begin(),
				// ctx.allBBsOfRegion.end(), exitPred);
				if ((exitPred == ctx.exitBBs[0] ||
					 ctx.betweenExitBBs.contains(exitPred))) {
					exit0VersionOfVal->addIncoming(condAsI, exitPred);
				} else {
					// the value will be unused, the final select
					// will select value not coming from exitBB0
					// section
					exit0VersionOfVal->addIncoming(
						PoisonValue::get(exit0VersionOfVal->getType()),
						exitPred);
				}
			}
			if (!is_contained(predecessors(ctx.exitBBs[1]), &ctx.BB0)) {
				// because jump will be added later
				exit0VersionOfVal->addIncoming(
					PoisonValue::get(exit0VersionOfVal->getType()),
					&ctx.BB0);
			}
			return exit0VersionOfVal;
		}
	}
	return nullptr;
}

// construct enFromPred for path from BB0 (excluding path trough exitBBs[0] if there are multiple exits)
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
	for (BasicBlock *pred : BBPredecessors) {
		if (pred != &BB0 && (
			!ctx.allBBsOfRegion.contains(pred) || // case of bb0, exits with predec from outside
			pred == &BB // case of exit being self loop	
			
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
		bool _shouldUpdateValueForPred = true;
		bool predValWillStay = ctx.exitBBs.size() == 2 && ctx.isInExit0Section(*pred);
		if (predValWillStay) {
			canCompletlyRemovePhi = false;
			if (!ctx.blocksReachableFromBB0WithoutExit0.contains(pred)) {
				_shouldUpdateValueForPred = false;
			}
		}
		shouldUpdateValueForPred.push_back(_shouldUpdateValueForPred); 
		// resolve condition which is 1 if the block is entered from some
		// predecessor
		IRBuilderBase::InsertPointGuard IPG(Builder);
		//errs() << "br." + pred->getName() + ".enFor." + BB.getName() << "\n";

		std::optional<Value *> CondOverride;
		if ((ctx.exitBBs.size() > 1 && pred == ctx.exitBBs[0]) ||
			ctx.betweenExitBBs.contains(pred)) {
			Builder.SetInsertPoint(ctx.bbExit1SelectInsertPos);
			// if the condition value depends on the exitBB0 we have to
			// substitute it with the the phi constructed in the exitBB1
			// constructed for this term
			auto predTerm = pred->getTerminator();
			if (auto Br = dyn_cast<BranchInst>(predTerm)) {
				if (Br->isConditional()) {
					CondOverride = Br->getCondition();
				}
			} else if (auto Sw = dyn_cast<SwitchInst>(predTerm)) {
				CondOverride = Sw->getCondition();
			}
			if (CondOverride.has_value()) {
				if (auto exit0VersionOfVal = createVariantForExit1Path(ctx, Builder, CondOverride.value())) {
					CondOverride = exit0VersionOfVal;
				}
			}
		} else {
			Builder.SetInsertPoint(ctx.bb0SelectInsertPos);
		}
		if (ctx.exitBBs.size() == 2 &&  // there are multiple exits
				//!BBIsExit1WithRequiredCond &&  // we can use exitBBs[0] en cond
				ctx.isInExit0Section(*pred) && 
				!ctx.blocksReachableFromBB0WithoutExit0.contains(pred)) {
		 	// the bbEn condition is build only for exit1 path, )
			enFromPredecessor.push_back(nullptr);
			continue;
		 }
		
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
				cI->setName("fewExitSw.sucSel.en." + pred->getName() + "." + BB.getName());
			}
		}
		enFromPredecessor.push_back(enFromPred);
	}
	assert(enFromPredecessor.size() == BBPredecessors.size());
	assert(shouldUpdateValueForPred.size() == BBPredecessors.size());
}

// Construct selects to emulate original phi behavior
// :attention: phiReplacements must be preallocated initialized to nullptrs
static void lowerPhisOfBlockInRegion_construct_selects(LowerPhisToSelectInRegionContext &ctx,
		BasicBlock & BB, const SmallVector<PHINode *> &bbPhis, bool isPhiWithVersionForExit0,
		const SetVector<BasicBlock *>& BBPredecessors,
		const SmallVector<Value *> &enFromPredecessor,
		const SmallVector<bool> &shouldUpdateValueForPred, // false for predecessors outside of region
		SmallVector<Value *>& phiReplacements
	) {
	auto &Builder = ctx.Builder;
	// build a SelectInst tree from enFromPredecessor and phi operands
	for (const auto &[en, pred, shouldUpdate] :
		 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
		if (!shouldUpdate) {
			continue;
		}
		if (!en) {
			assert(ctx.isInExit0Section(*pred) && "This could happen only for BBs in exit0 section which are unreachable from BB0");
			continue;
		}
		if (isPhiWithVersionForExit0 &&
			(&BB != ctx.exitBBs[1] && ctx.isInExit0Section(*pred))) {
			continue; // this operand will not be part of select tree and
					  // will stay in phi as is
		}

		
		assert(en != nullptr);
		size_t phiIndex = 0;
		for (auto &_phi : bbPhis) {
			auto &phi = *_phi;
			Value *prevVal = phiReplacements[phiIndex];
			Value *val = phi.getIncomingValueForBlock(pred);
			if (auto valAsPhi = dyn_cast<PHINode>(val)) {
				auto replacementForBB0Path =
					ctx.exit1VersionOfValueDependentOnExit0.find(valAsPhi);
				if (replacementForBB0Path !=
					ctx.exit1VersionOfValueDependentOnExit0.end()) {
					val = replacementForBB0Path->second;
				}
			}
			if (prevVal == nullptr) {
				// the case of the first pred, which we will use as a default
				phiReplacements[phiIndex] = val;
			} else {
				// all other preds
				assert(prevVal->getType() == phi.getType());
				assert(val->getType() == phi.getType());
				phiReplacements[phiIndex] =
					Builder.CreateSelect(en, val, prevVal);
			}
			phiIndex++;
		}
	}
}

static void lowerPhisOfBlockInRegion_handePhiUpdate(
	LowerPhisToSelectInRegionContext &ctx, BasicBlock &BB,
	const SmallVector<PHINode *> &bbPhis, bool isPhiWithVersionForExit0,
	bool canCompletlyRemovePhi, const SetVector<BasicBlock *> &BBPredecessors,
	const SmallVector<Value *> &enFromPredecessor,
	const SmallVector<bool>
		&shouldUpdateValueForPred, // false for predecessors outside of region
	const SmallVector<Value *> &phiReplacements) {
	auto &BB0 = ctx.BB0;
	auto &Builder = ctx.Builder;
#ifndef NDEBUG
	for (auto *_phi : bbPhis) {
		assert(!ctx.newPhisInExit1.contains(_phi));
	}
#endif
	if (isPhiWithVersionForExit0) {
		assert(ctx.exitBBs.size() == 2);
		if (&BB == ctx.exitBBs[1]) {
			// update original phis to use values for bb0 to exitbb1 path
			{
				for (auto *phi : bbPhis) {
					for (const auto &[en, pred, shouldUpdate] :
						 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
						if (!shouldUpdate) {
							continue;
						}
						auto predIsForExit0Section = pred == ctx.exitBBs[0] || ctx.betweenExitBBs.contains(pred);
						auto predI = phi->getBasicBlockIndex(pred);
						if (predIsForExit0Section) {
							// the phi will exits only for select from blocks in exit0 section
						} else {
							phi->setIncomingValue(predI, PoisonValue::get(phi->getType()));// we will use select to decide this
							phi->setIncomingBlock(predI, &BB0);
						}
					}
				}
			}
			{
				// IRBuilderBase::InsertPointGuard IPG(Builder);
				size_t phiIndex = 0;
				// construct select for selection between exit0-exit1 paths
				auto _exit0en = ctx.bbEnableCache.find(ctx.exitBBs[0]);
				assert(_exit0en != ctx.bbEnableCache.end() && "We were walking topologically sorted blocks and "
					"now we are at ctx.exitBBs[1] we had to see ctx.exitBBs[0] already");
				for (auto *phi : bbPhis) {
					auto replacement = phiReplacements[phiIndex];
					auto finalReplacement = Builder.CreateSelect(_exit0en->second, phi, replacement);	
					finalReplacement->takeName(phi);
					phi->replaceUsesWithIf(finalReplacement, [finalReplacement](Use &U) {
						return U.getUser() != finalReplacement;
					});
					++phiIndex;
				}
			}
		} else {
			for (const auto &[en, pred, shouldUpdate] :
				 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
				if (!shouldUpdate) {
					continue;
				}
				if(pred == &BB0) {
					size_t phiIndex = 0;
					for (auto *phi : bbPhis) {
						phi->setIncomingValueForBlock(pred, phiReplacements[phiIndex]);
						++phiIndex;
				    }
					continue;
				}
				if (pred == ctx.exitBBs[0] || ctx.betweenExitBBs.contains(pred)) {
					continue;
				}
				for (auto *phi : bbPhis) {
					// this operand is lowered to selects in exitBBs[1]
					// this path in CFG will handle only paths trough exitBBs[0]
					phi->removeIncomingValue(pred);
				}
			}
			SmallVector<PHINode *> mergePhis(bbPhis.size(), nullptr);
			{
				size_t exit1PredCnt = pred_size(ctx.exitBBs[1]);
				size_t phiI = 0;
				IRBuilderBase::InsertPointGuard IG(Builder);
				Builder.SetInsertPoint(ctx.exitBBs[1]->getFirstInsertionPt());
				for (auto *_phi : bbPhis) {
					auto &phi = *_phi;
					PHINode *mergePhi = Builder.CreatePHI(phi.getType(), exit1PredCnt, phi.getName());
					ctx.exit1VersionOfValueDependentOnExit0[&phi] = mergePhi;
					ctx.phiInExit1ForValuesFromExit0[&phi] = mergePhi;
					ctx.newPhisInExit1.insert(mergePhi);
					mergePhis[phiI] = mergePhi;
					phiI++;
				}
			}
			// populate operands of mergePhis
			//auto thisBBPos = std::find(ctx.allBBsOfRegion.begin(), ctx.allBBsOfRegion.end(), &BB);
			//assert(thisBBPos != ctx.allBBsOfRegion.end());
			for (auto exitPred: predecessors(ctx.exitBBs[1])) {
				//auto predBBPos = std::find(ctx.allBBsOfRegion.begin(), ctx.allBBsOfRegion.end(), exitPred);
				if ((exitPred == ctx.exitBBs[0] ||
					 ctx.betweenExitBBs.contains(exitPred))
					//(predBBPos != ctx.allBBsOfRegion.end() && // check that exitPred is dominated by 
					// predBBPos <= thisBBPos)
				 ) {
					for (const auto &[phi, mergePhi] : zip(bbPhis, mergePhis)) {
						// :attention: this is not final as the exitPred may not be dominated by BB
						//             and it must be checked later once DT is updated
						//             :see: lowerPhisOfBlockInRegion_finalizeExit0AndBB0PathSelect
						mergePhi->addIncoming(phi, exitPred);
					}
				} else {
					// the value will be unused, the final select will select value not coming from exitBB0 section
					for (auto *mergePhi : mergePhis) {
						mergePhi->addIncoming(PoisonValue::get(mergePhi->getType()), exitPred);
					}
				}
			}
		}
	} else if (canCompletlyRemovePhi) {
		// replace phis with SelectInst
		size_t phiIndex = 0;
		for (auto *phi : bbPhis) {
			Value *replacement = phiReplacements[phiIndex];
			assert(replacement->getType() == phi->getType());
			replacement->takeName(phi);
			phi->replaceAllUsesWith(replacement);
			phi->eraseFromParent();
			// assert(loweredPhiCache.find(&phi) == loweredPhiCache.end());
			// loweredPhiCache[&phi] = replacement;
			phiIndex++;
		}
	} else {
		// update incoming values for selected operands
		size_t phiIndex = 0;
		for (auto *phi : bbPhis) {
			for (const auto &[en, pred, shouldUpdate] :
				 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
				if (!shouldUpdate) {
					continue;
				}
				auto predI = phi->getBasicBlockIndex(pred);
				phi->setIncomingValue(predI, phiReplacements[phiIndex]);
				phi->setIncomingBlock(predI, &BB0);
			}
			++phiIndex;
		}
	}
}

// :param BB0: the top block of region, which dominates all block in
//             allBBsOfRegion except the exit blocks
// :param BB: the block for which to lower the phis

// :returns: the enable condition for a given block
Value *lowerPhisOfBlockInRegion(LowerPhisToSelectInRegionContext &ctx,
		BasicBlock &BB, bool isPhiWithVersionForExit0) {
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

	SmallVector<Value *> phiReplacements(llvm::range_size(BB.phis()), nullptr);
	SmallVector<PHINode *> bbPhis;// backup needed because we may potentially create new phis
	for (auto & phi: BB.phis()) {
		if (!ctx.newPhisInExit1.contains(&phi))
			bbPhis.push_back(&phi);
	}
	bool isExit1 = ctx.exitBBs.size() == 2 && &BB == ctx.exitBBs[1];
	lowerPhisOfBlockInRegion_construct_selects(
		ctx, BB, bbPhis,
		isPhiWithVersionForExit0 && !isExit1, // in exit1 we should lower phis
		BBPredecessors, enFromPredecessor, shouldUpdateValueForPred,
		phiReplacements);

	lowerPhisOfBlockInRegion_handePhiUpdate(
		ctx, BB, bbPhis, isPhiWithVersionForExit0, canCompletlyRemovePhi,
		BBPredecessors, enFromPredecessor, shouldUpdateValueForPred,
		phiReplacements);
	if (&BB == ctx.exitBBs.back()) { //  && !ctx.isBlockExit1WithConditionRequired(BB)
		// BBEn is nor required for any successor
		return nullptr;
	}
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
