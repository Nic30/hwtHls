#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass.h>

#include <algorithm>
#include <map>
#include <limits>

#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Analysis/LazyBlockFrequencyInfo.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/LoopPass.h>
#include <llvm/Analysis/MemorySSA.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/InitializePasses.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Transforms/Scalar.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>
#include <llvm/Transforms/Utils/LoopUtils.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>

#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/utils/inLoopConditionalExecution.h>
#include <hwtHls/llvm/Transforms/utils/loopMerging.h>
#include <hwtHls/llvm/Transforms/utils/loopHwtHlsMetadata.h>

// #define LoopFlattenUsingIfPass_TRACE

#ifdef LoopFlattenUsingIfPass_TRACE
#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#endif

using namespace llvm;

#define DEBUG_TYPE "loop-fusion-usingif"

namespace hwtHls {

#ifdef LoopFlattenUsingIfPass_TRACE
static size_t dbgCntr = 0;
#endif

PHINode* createIsChildLoopPhiInHeader(llvm::LoopStandardAnalysisResults &AR,
		DomTreeUpdater &DTU, MemorySSAUpdater *MSSAU, llvm::Loop &LParent,
		llvm::Loop &LChild, BasicBlock *header, BasicBlock *childHeader) {
	auto &Ctx = header->getContext();
	auto int1Ty = IntegerType::getInt1Ty(Ctx);
	auto *isChildLoop = PHINode::Create(int1Ty,
			pred_size(header) + pred_size(childHeader),
			"isChildLoop." + childHeader->getName(), &*header->begin());
	for (auto pred : predecessors(header)) {
		if (!LParent. contains(pred))
			isChildLoop->addIncoming(ConstantInt::get(int1Ty, 0), pred);
	}
	for (auto *childHeadPred : predecessors(childHeader)) {
		assert(
				childHeadPred != header
						&& "LoopSimplify normal form requires preheader");
		if (llvm::any_of(predecessors(header), [childHeadPred](BasicBlock *BB) {
			return BB == childHeadPred;
		})) {
			// if it was already a successor create a new block for current exitBB, because of PHIs
			if (DTU.hasPendingUpdates())
				DTU.flush();
			CriticalEdgeSplittingOptions Options(&DTU.getDomTree(), &AR.LI,
					MSSAU, &DTU.getPostDomTree());
			childHeadPred = SplitCriticalEdge(childHeadPred, childHeader,
					Options);
		} else {
			assert(
					(LChild.contains(childHeadPred)
							|| LParent.contains(childHeadPred)));
		}
	}
	return isChildLoop;
}

void collectBlocksUntilSrcBlock(BasicBlock &untilBlock,
		SetVector<BasicBlock*> &seen, BasicBlock &current) {
	if (&current == &untilBlock || seen.contains(&current))
		return;
	seen.insert(&current);
	for (auto *pred : predecessors(&current)) {
		collectBlocksUntilSrcBlock(untilBlock, seen, *pred);
	}
}

/*
 * :param childPreHeader: original child loop preheader (the childHeader now has 2 because it has new edge
 *     which implements skip of parent loop begin section)
 * :param parentBeginSectionEnd: block at the end of section in parent loop which was just
 * 		made conditional, values coming from there are alloca loads if they are generated
 * 		by that section
 * */
void rerouteChildBackedgeAndTransferChildPhis(BasicBlock *childPreHeader,
		BasicBlock *childHeader, BasicBlock *extractedSectionGuard,
		llvm::Loop &LChild, BasicBlock *oldLatchBlock,
		BasicBlock *newLatchBlock, BasicBlock *header, llvm::Loop &LParent,
		PHINode *phiInLatchDrivingBranch,
		Value *valueForPhiInLatchCausingReenter, PHINode &isChildLoop,
		const std::map<PHINode*, PHINode*> &associatedPhis,
		MemorySSAUpdater *MSSAU, DomTreeUpdater &DTU) {
	// :note: because we split parent latch and reroute child backedge to it
	//    some variables defined in parent loop may not dominate all uses
	//    parent header PHIs. For them we have to create a new phi in new
	//    latch block to select undef if loop executes in child loop mode.
	//    (the predecessor of new latch is a child latch)

	// reroute all continue edges in child loop to jump to newLatchBlock
	// with value asserting that it will jump to parent loop header
	//DTU.flush();
	auto childLatch = LChild.getLoopLatch();
	assert(
			childLatch
					&& "LoopSimplify normal form specifies just 1 backedge and 1 latch block");

	// for each child phi
	auto headerPredCnt = llvm::pred_size(newLatchBlock);
	auto *firstNonPhiOfHeader = &*header->getFirstNonPHI();
	auto *firstNonPhiOfNewLatch = &*newLatchBlock->getFirstNonPHI();
	auto *childHeaderFirstNonPhi = childHeader->getFirstNonPHI();
	for (PHINode &childPhi : make_early_inc_range(childHeader->phis())) {
		// create a phi in parent header which will switch between undef on enter and value from prev iteration
		auto Ty = childPhi.getType();
		auto existingParentPhi = associatedPhis.find(&childPhi);
		bool reusingParentPhi = existingParentPhi != associatedPhis.end();
		PHINode *headerPhi;
		if (reusingParentPhi) {
			headerPhi = existingParentPhi->second;
		} else {
			headerPhi = PHINode::Create(Ty, headerPredCnt, childPhi.getName(),
					firstNonPhiOfHeader);
		}
		auto parentPreheader = LParent.getLoopPreheader();
		assert(
				parentPreheader
						&& "LoopSimplify normal form specifies that there must be preheader");
		if (!reusingParentPhi)
			headerPhi->addIncoming(PoisonValue::get(Ty), parentPreheader); // value for child loop is undef in first iteration

		// create a phi in newLatchBlock which will switch between undef and value from the child loop body
		auto childBackedgeVal = childPhi.getIncomingValueForBlock(childLatch);
		PHINode *latchPhi;
		bool latchPhiIsNew = true;
		if (auto oldLatchPhi = dyn_cast<PHINode>(childBackedgeVal)) {
			if (oldLatchPhi->getParent() == newLatchBlock) {
				assert(newLatchBlock == oldLatchBlock);
				latchPhi = oldLatchPhi;
				latchPhiIsNew = false;
			}
		}
		if (latchPhiIsNew) {
			latchPhi = PHINode::Create(Ty, 2, childPhi.getName(),
					firstNonPhiOfNewLatch);
		}
		latchPhi->addIncoming(childBackedgeVal, childLatch);

		auto valFromExtractedSection = childPhi.getIncomingValueForBlock(
				childPreHeader);
		childPhi.removeIncomingValue(childLatch); // remove value for removed backedge
		// add value for edge which is used if parent loop is running ind child loop mode
		childPhi.addIncoming(headerPhi, extractedSectionGuard);

		auto valFromExtractedSectionAsInst = dyn_cast<LoadInst>(
				valFromExtractedSection);
		if (valFromExtractedSectionAsInst
				&& isa<AllocaInst>(
						valFromExtractedSectionAsInst->getPointerOperand())) {
			// move alloca load to this block and use it instead of this phi
			auto ld = valFromExtractedSectionAsInst->clone();
			ld->insertBefore(childHeaderFirstNonPhi);
			valFromExtractedSection = ld;
		} else {
			// the value is not generated by extracted block and we can use it instead of this phi
		}
		//childPhi.replaceAllUsesWith(valFromExtractedSection);
		//childPhi.eraseFromParent();

		// if value from extracted section is load of alloca, clone load of alloca and use it
		// else this is not variable generated by extracted section and we can use it as is
		//childPhi.addIncoming(V, BB)
		//for (int Idx = childPhi.getNumIncomingValues() - 1; Idx > 0;
		//		--Idx) {
		//	childPhi.removeIncomingValue(Idx, /*DeletePHIIfEmpty*/
		//	false);
		//}
		//for (auto _childHeadPred : predecessors(childHeader)) {
		//	if (_childHeadPred != childHeadPred) {
		//		latchPhi->addIncoming(headerPhi, _childHeadPred);
		//	}
		//}
		// newLatchBlock can not have childHeadPred as a predecessor because it is latch and child has to have loopexit block
		if (latchPhiIsNew) {
			for (auto latchPred : predecessors(newLatchBlock)) {
				assert(latchPred != newLatchBlock);
				// value for child loop is undef once code exited child loop
				latchPhi->addIncoming(PoisonValue::get(Ty), latchPred);
			}
		}
		if (reusingParentPhi)
			headerPhi->setIncomingValueForBlock(newLatchBlock, latchPhi);
		else
			headerPhi->addIncoming(latchPhi, newLatchBlock);
	}
	childLatch->getTerminator()->replaceUsesOfWith(childHeader, newLatchBlock);
	if (phiInLatchDrivingBranch) {
		assert(valueForPhiInLatchCausingReenter);
		phiInLatchDrivingBranch->addIncoming(valueForPhiInLatchCausingReenter,
				childLatch);
	}
	if (newLatchBlock == oldLatchBlock) {
		// if reusing old latch block we may not update
		// all phis because some of them may not be related
		// to phis in childHeader
		size_t predCnt = pred_size(oldLatchBlock);
		for (auto &latchPhi : oldLatchBlock->phis()) {
			size_t valCnt = latchPhi.getNumIncomingValues();
			if (valCnt != predCnt) {
				assert(predCnt == valCnt + 1);
				assert(latchPhi.getBasicBlockIndex(childHeader) < 0);
				latchPhi.addIncoming(PoisonValue::get(latchPhi.getType()),
						childLatch);
			}
		}
	}

	SmallVector<DominatorTree::UpdateType, 2> Updates;
	Updates.push_back( { DominatorTree::Delete, childLatch, childHeader });
	Updates.push_back( { DominatorTree::Insert, childLatch, newLatchBlock });
	if (MSSAU) {
		if (DTU.hasPendingUpdates())
			DTU.flush();
		MSSAU->applyUpdates(Updates, DTU.getDomTree());
	} else {
		DTU.applyUpdates(Updates);
		DTU.flush();
	}
	IRBuilder<> Builder(newLatchBlock->getFirstNonPHI());
	auto &DT = DTU.getDomTree();
	for (auto &phi : header->phis()) {
		if (&phi == &isChildLoop)
			continue;
		auto latchVal = phi.getIncomingValueForBlock(newLatchBlock);
		if (auto latchValI = dyn_cast<Instruction>(latchVal)) {
			auto latchValDefBB = latchValI->getParent();
			if (!DT.dominates(latchValDefBB, newLatchBlock)) {
				auto Ty = latchValI->getType();
				auto newLatchPhi = Builder.CreatePHI(Ty,
						pred_size(newLatchBlock), latchValI->getName());
				if (newLatchBlock == oldLatchBlock)
					llvm_unreachable("NotImplemented");
				newLatchPhi->addIncoming(latchVal, oldLatchBlock);
				newLatchPhi->addIncoming(PoisonValue::get(Ty), childLatch); // undef if looping in child loop mode
				phi.setIncomingValueForBlock(newLatchBlock, newLatchPhi);
			}
		}
	}

	auto &Ctx = header->getContext();
	auto int1Ty = IntegerType::getInt1Ty(Ctx);
	auto *isChildLoopInLatch = PHINode::Create(int1Ty, pred_size(newLatchBlock),
			"isChildLoopInLatch." + childHeader->getName(),
			newLatchBlock->getFirstNonPHI());
	isChildLoop.addIncoming(isChildLoopInLatch, newLatchBlock);
	for (auto latchPred : predecessors(newLatchBlock)) {
		isChildLoopInLatch->addIncoming(
				ConstantInt::get(int1Ty, latchPred != oldLatchBlock),
				latchPred);
	}
}

std::pair<BasicBlock*, BasicBlock*> prepareNewLatchBlock(llvm::Loop &LParent,
		DomTreeUpdater &DTU, llvm::LoopStandardAnalysisResults &AR,
		MemorySSAUpdater *MSSAU, PHINode *&phiInLatchDrivingBranch,
		Value *&valueForPhiInLatchCausingReenter, BasicBlock *header) {
	BasicBlock *oldLatchBlock = LParent.getLoopLatch();
	BasicBlock *newLatchBlock = oldLatchBlock;

	auto &Ctx = header->getContext();
	auto int1Ty = IntegerType::getInt1Ty(Ctx);

	assert(
			newLatchBlock
					&& "Must be present because this is in LoopSimplify normal form");
	for (Instruction &I : *oldLatchBlock) {
		if (isa<PHINode>(I))
			continue;

		Instruction *Term;
		if (I.isTerminator()) {
			// block contains only PHIs and terminator
			auto BR = dyn_cast<BranchInst>(&I);
			if (BR && !BR->isConditional()) {
				break; // we can reuse this block because it has unconditional branch
			}
			Term = &I;
		} else {
			Term = &I;
			do {
				Term = Term->getNextNode();
			} while (!Term->isTerminator());
		}
		if (DTU.hasPendingUpdates()) {
			DTU.flush();
		}
		oldLatchBlock = SplitBlock(oldLatchBlock, Term, &DTU, &AR.LI, MSSAU,
				oldLatchBlock->getName() + ".oldLatch", /*Before*/
				true);

		if (BranchInst *BR = dyn_cast<BranchInst>(Term)) {
			if (BR->isConditional()) {
				phiInLatchDrivingBranch = PHINode::Create(int1Ty, 2, "continue",
						&*newLatchBlock->begin());
				phiInLatchDrivingBranch->addIncoming(BR->getCondition(),
						oldLatchBlock);
				BR->setCondition(phiInLatchDrivingBranch);
				valueForPhiInLatchCausingReenter = ConstantInt::get(int1Ty,
						BR->getSuccessor(0) == header);
			} else {
				break; // no need to resolve valueForPhiInLatchCausingReenter
			}
		} else if (SwitchInst *SW = dyn_cast<SwitchInst>(Term)) {
			auto Cond = SW->getCondition();
			phiInLatchDrivingBranch = PHINode::Create(Cond->getType(), 2,
					"continue", &*newLatchBlock->begin());
			phiInLatchDrivingBranch->addIncoming(Cond, oldLatchBlock);
			BR->setCondition(phiInLatchDrivingBranch);
			for (auto &SwCase : SW->cases()) {
				if (SwCase.getCaseSuccessor() == header) {
					valueForPhiInLatchCausingReenter = SwCase.getCaseValue();
					break;
				}
			}
			if (!valueForPhiInLatchCausingReenter)
				llvm_unreachable(
						"NotImplemented: backedge is switch default branch, need to infer value for condition");
		} else {
			Term->dump();
			llvm_unreachable("Unsupported type of terminator");
		}

		break;
	}
	return {newLatchBlock, oldLatchBlock};
}

//void promoteAllocasForBeginSectionLiveouts(BasicBlock *beginSectionBegin,
//		BasicBlock *beginSectionEnd, llvm::Loop &LParent, DomTreeUpdater &DTU,
//		llvm::LoopStandardAnalysisResults &AR) {
//	// handle lifetime of variables defined in begin section (they are alive during iteration of child loop,
//	// and now they are alive also during parent loop)
//	// rm Intrinsic::lifetime_start
//	for (auto &I : make_early_inc_range(*beginSectionBegin)) {
//		if (isa<PHINode>(&I)) {
//		} else if (auto C = dyn_cast<CallInst>(&I)) {
//			if (C->getCalledFunction()->getIntrinsicID()
//					== Intrinsic::lifetime_start) {
//				C->eraseFromParent();
//			}
//		} else {
//			break;
//		}
//	}
//	// move all Intrinsic::lifetime_end to exits of parent loop
//	// (lifetime_ends are at the end of the block just before terminator)
//	Instruction *lifetime_end_begin = nullptr;
//	Instruction *lifetime_end_end = beginSectionEnd->getTerminator();
//	if (lifetime_end_end != &*beginSectionEnd->begin()) {
//		for (auto *I = lifetime_end_end->getPrevNode();
//				I != &*beginSectionEnd->begin(); I = I->getPrevNode()) {
//			if (auto C = dyn_cast<CallInst>(I)) {
//				if (C->getCalledFunction()->getIntrinsicID()
//						== Intrinsic::lifetime_end) {
//					lifetime_end_begin = I;
//					continue;
//				}
//			}
//			break;
//		}
//		if (lifetime_end_begin) {
//			SmallVector<BasicBlock*> ExitBlocks;
//			LParent.getUniqueExitBlocks(ExitBlocks);
//			auto lifemtime_ends = make_range(lifetime_end_begin->getIterator(),
//					lifetime_end_end->getIterator());
//			SmallVector<AllocaInst*> Allocas;
//			for (Instruction &I : lifemtime_ends) {
//				auto C = dyn_cast<CallInst>(&I);
//				assert(C);
//				auto A = dyn_cast<AllocaInst>(C->getArgOperand(1));
//				assert(A);
//				Allocas.push_back(A);
//			}
//			for (auto exit : ExitBlocks) {
//				// copy Intrinsic::lifetime_end after phis
//				auto insertPoint = exit->getFirstNonPHI();
//				for (Instruction &I : lifemtime_ends) {
//					auto newI = I.clone();
//					newI->insertBefore(insertPoint);
//				}
//			}
//			// remove Intrinsic::lifetime_end from beginSectionEnd
//			for (Instruction &I : make_early_inc_range(lifemtime_ends)) {
//				I.eraseFromParent();
//			}
//			if (DTU.hasPendingUpdates())
//				DTU.flush();
//
//			// construct PHIs for variables defined in loop begin section which are now alive trough iteration
//			// of parent loop because it was merged with child loop
//			PromoteMemToReg(Allocas, DTU.getDomTree(), &AR.AC);
//		}
//	}
//}

void collectBlocksUntilLoopEnd(llvm::Loop &L, SetVector<BasicBlock*> &seen,
		BasicBlock &BB) {
	if (&BB == L.getHeader())
		return; // header is start of new iteration, which is after loop end
	if (seen.insert(&BB)) {
		// analyzing also loop exit block, which is not part of the loop
		if (!L.contains(&BB))
			return;
		for (auto Suc : successors(&BB)) {
			collectBlocksUntilLoopEnd(L, seen, *Suc);
		}
	}
}
struct ScoreAndRank {
	size_t score; // main score, more = better
	size_t rank; // order of original item to make winner selection deterministic
};

void countHowManytimesValueIsDrivenFromPhi(llvm::Loop &L, llvm::Instruction &I,
		size_t exprDepth, std::set<Instruction*> &seen,
		std::map<Instruction*, ScoreAndRank> &score) {
	if (!L.contains(I.getParent()))
		return; // driver outside of parent loop, this can not lead to parent phi

	auto _score = score.find(&I);

	if (_score != score.end()) {
		size_t curScore = _score->second.score;
		size_t thisScore = std::numeric_limits<size_t>::max() - exprDepth;
		_score->second.score = std::max(curScore, thisScore);
		return;
	}

	if (seen.find(&I) != seen.end()) {
		return;
	} else {
		seen.insert(&I);
	}

	for (Use &Op : I.operands()) {
		if (Op.get()->getType() == I.getType())
			if (auto OpI = dyn_cast<Instruction>(Op.get())) {
				countHowManytimesValueIsDrivenFromPhi(L, *OpI, exprDepth + 1,
						seen, score);
			}
	}
}

/*
 * The parent PHI is associated with child PHI if:
 *  * it does not live trough child loop
 *  * has the same type
 *  * there is a path in expression from parent PHI to child PHI
 * */
std::map<PHINode*, PHINode*> findAssociatedPhis(llvm::Loop &LParent,
		llvm::Loop &LChild) {
	std::map<PHINode*, PHINode*> childToParentPhi;
	auto childHeader = LChild.getHeader();
	auto childPhis = childHeader->phis();
	if (childPhis.begin() == childPhis.end()) {
		// there is nothing to associate with
		return childToParentPhi;
	}

	SetVector<BasicBlock*> blocksAfterChildLoop;
	SmallVector<BasicBlock*> ExitBlocks;
	LChild.getExitBlocks(ExitBlocks);
	for (auto BB : ExitBlocks)
		collectBlocksUntilLoopEnd(LParent, blocksAfterChildLoop, *BB);

	// :note: except for PHI incoming values from outside of after child loop section
	// :note: this expects LoopSimplify normal form where all loop liveouts have phi in exit block
	auto isUsedAfterChildLoop = [&](PHINode &phi) {
		for (auto &U : phi.uses()) {
			if (auto UInst = dyn_cast<Instruction>(U.getUser())) {
				auto Ubb = UInst->getParent();
				if (auto UPhi = dyn_cast<PHINode>(UInst)) {
					if (!LParent.contains(Ubb)) {
						// this is liveout of parent loop
						return true;
					} else {
						for (size_t i = 0; i < UPhi->getNumIncomingValues();
								++i) {
							if (UPhi->getIncomingValue(i) == &phi
									&& blocksAfterChildLoop.contains(Ubb)) {
								return true; // used internally in phi inside of after child loop section
							}
						}
						// used only on edge from child loop or section before it
					}
				} else {
					if (blocksAfterChildLoop.contains(Ubb))
						return true; // used internally in section after loop
				}
			}
		}
		return false;
	};

	using ScoreDict = std::map<Instruction*, ScoreAndRank>;
	ScoreDict availablePhiScore;
	size_t rank = 0;
	for (PHINode &parentPhi : LParent.getHeader()->phis()) {
		if (!isUsedAfterChildLoop(parentPhi))
			availablePhiScore[&parentPhi] = { rank++, 0 };
	}
	if (availablePhiScore.size()) {
		for (PHINode &childPhi : childHeader->phis()) {
			std::set<Instruction*> seen;
			countHowManytimesValueIsDrivenFromPhi(LParent, childPhi, 0, seen,
					availablePhiScore);

			auto bestCandidate = std::max_element(availablePhiScore.begin(),
					availablePhiScore.end(),
					[](ScoreDict::reference &v0, ScoreDict::reference &v1) {
						if (v0.second.score == v1.second.score)
							return v0.second.rank < v1.second.rank;
						else
							return v0.second.score < v1.second.score;
					});

			if (bestCandidate->second.score) {
				childToParentPhi[&childPhi] = dyn_cast<PHINode>(
						bestCandidate->first);
				availablePhiScore.erase(bestCandidate);
			}

			if (availablePhiScore.empty())
				break;
			for (auto &score : availablePhiScore) {
				score.second.score = 0;
			}
		}
	}

	return childToParentPhi;
}

bool LoopFlattenUsingIfPass_flatten(llvm::Loop &LParent, llvm::Loop &LChild,
		llvm::LoopStandardAnalysisResults &AR, DomTreeUpdater &DTU,
		MemorySSAUpdater *MSSAU, llvm::LPMUpdater &LPMU) {

	{
		auto* F = LParent.getHeader()->getParent();
		using namespace ore;
		OptimizationRemark Remark(DEBUG_TYPE, "FlattenedUsingIf",
				LChild.getStartLoc(), LChild.getHeader());
		OptimizationRemarkEmitter ORE(F, AR.BFI);
		Remark << "Flattened using \"if\" into outer loop";
		ORE.emit(Remark);
	}

	bool Changed = false;
#ifdef LoopFlattenUsingIfPass_TRACE
	writeCFGToDotFile(*LParent.getHeader()->getParent(),
			"LoopFlattenUsingIfPass." + std::to_string(dbgCntr++)
					+ "-start.dot", AR.BFI, AR.BPI);
#endif
	auto associatedPhis = findAssociatedPhis(LParent, LChild);

	BasicBlock *header = LParent.getHeader();
	BasicBlock *childPreHeader = LChild.getLoopPreheader();
	BasicBlock *childHeader = LChild.getHeader();
	auto *isChildLoop = createIsChildLoopPhiInHeader(AR, DTU, MSSAU, LParent,
			LChild, header, childHeader);

	Instruction *headerPhisEnd = header->getFirstNonPHI();
	IRBuilder<> Builder(headerPhisEnd);
	// create if (!isChildLoop) sectionFromParentHeaderToChildHeader();
	BasicBlock *loopBegin = SplitBlock(header, headerPhisEnd, &DTU, &AR.LI,
			MSSAU);

#ifdef LoopFlattenUsingIfPass_TRACE
	writeCFGToDotFile(*LParent.getHeader()->getParent(),
			"LoopFlattenUsingIfPass." + std::to_string(dbgCntr++)
					+ "-after-initNormalization.dot", AR.BFI, AR.BPI);
#endif

	// Blocks reachable from child loop header until parent loop header;
	SetVector<BasicBlock*> parenLoopBeginBlocks;
	// because the top most block must be the first
	parenLoopBeginBlocks.insert(loopBegin);
	for (auto pred : predecessors(childHeader)) {
		if (!LChild.contains(pred))
			collectBlocksUntilSrcBlock(*header, parenLoopBeginBlocks, *pred);
	}

	//BasicBlock *beginSectionBegin;
	//BasicBlock *beginSectionEnd;
	//std::tie(beginSectionBegin, beginSectionEnd) =
	auto tmpAllocas = makeSectionOfLoopConditionalyReexecuted(LParent, header,
			childHeader, parenLoopBeginBlocks, isChildLoop, DTU, AR.LI, MSSAU,
			AR.BFI, AR.BPI, &AR.AC, /*conditionIsNegated*/true);
#ifdef LoopFlattenUsingIfPass_TRACE
	writeCFGToDotFile(*LParent.getHeader()->getParent(),
			"LoopFlattenUsingIfPass." + std::to_string(dbgCntr++)
					+ "-after-makeSectionOfLoopConditionalyReexecuted.dot",
			AR.BFI, AR.BPI);
#endif

	// :note: LoopSimplify normal form requires that there is a single backedge and latch block
	// :note: LCSSA pass transforms loops by placing phi nodes at the end of the loops for
	//   all values that are live across the loop boundary (and defined in the loop)
	// :note: The liveins and liveouts of child loop which are defined in parent loop needs to have a phi in new header
	//   which switches the value previously defined value defined in the parent loop begin and undef if this is a first iteration.
	// :note: liveouts are noted in PHIs created by LCSSA on every exit block, liveins are in PHIs of child block
	//   plus uses in child loop which are defined in parent loop

	// Cases which needs to be handled when rerouting child loop:
	// * value is defined in parent begin (which can be skipped) and is used in parent end
	//    * A tmp phi must be created in header to hold the value during iterations of child loop
	//    * There may be block which are not in parent begin or child loop section and
	//      can still reach end section.
	//    * An additional PHI must be constructed on every path which is merging value from parent begin and child loop section.
	//      This must be done recursively also for new PHIs.
	//    * If block is dominated by child loop it should use only PHI in child header
	PHINode *phiInLatchDrivingBranch = nullptr;
	Value *valueForPhiInLatchCausingReenter = nullptr;
	//DTU.flush();
	BasicBlock *newLatchBlock;
	BasicBlock *oldLatchBlock;
	std::tie(newLatchBlock, oldLatchBlock) = prepareNewLatchBlock(LParent, DTU,
			AR, MSSAU, phiInLatchDrivingBranch,
			valueForPhiInLatchCausingReenter, header);
#ifdef LoopFlattenUsingIfPass_TRACE
	writeCFGToDotFile(*LParent.getHeader()->getParent(),
			"LoopFlattenUsingIfPass." + std::to_string(dbgCntr++)
					+ "-after-prepareNewLatchBlock.dot", AR.BFI, AR.BPI);
#endif
	//DTU.flush();
	// reroute all continue edges in child loop to jump to newLatchBlock
	// with value asserting that it will jump to parent loop header
	rerouteChildBackedgeAndTransferChildPhis(childPreHeader, childHeader,
			header, LChild, oldLatchBlock, newLatchBlock, header, LParent,
			phiInLatchDrivingBranch, valueForPhiInLatchCausingReenter,
			*isChildLoop, associatedPhis, MSSAU, DTU);
#ifdef LoopFlattenUsingIfPass_TRACE
	writeCFGToDotFile(*LParent.getHeader()->getParent(),
			"LoopFlattenUsingIfPass." + std::to_string(dbgCntr++)
					+ "-after-rerouteChildBackedgeAndTransferChildPhis.dot",
			AR.BFI, AR.BPI);
#endif

	if (DTU.hasPendingUpdates())
		DTU.flush();

	// construct PHIs for variables defined in loop begin section which are now alive trough iteration
	// of parent loop because it was merged with child loop
	PromoteMemToReg(tmpAllocas, DTU.getDomTree(), &AR.AC);
	//promoteAllocasForBeginSectionLiveouts(beginSectionBegin, beginSectionEnd,
	//		LParent, DTU, AR);
	mergeNestedLoops(AR.LI, &AR.SE, LPMU, &LChild, &LParent);
#ifdef LoopFlattenUsingIfPass_TRACE
	writeCFGToDotFile(*LParent.getHeader()->getParent(),
			"LoopFlattenUsingIfPass." + std::to_string(dbgCntr++) + "-end.dot",
			AR.BFI, AR.BPI);
#endif
	Changed = true;
	return Changed;
}


llvm::PreservedAnalyses LoopFlattenUsingIfPass::run(llvm::Loop &L,
		llvm::LoopAnalysisManager &AM, llvm::LoopStandardAnalysisResults &AR,
		llvm::LPMUpdater &U) {
	auto passEn = getOptionalIntHwtHlsLoopAttribute(&L, "hwthls.loop.flattenusingif.enable");
	bool Changed = false;
	if (passEn.has_value() && passEn.value()) {
		auto& F = *L.getHeader()->getParent();
		std::optional<MemorySSAUpdater> MSSAU;
		if (AR.MSSA)
			MSSAU = MemorySSAUpdater(AR.MSSA);

		DomTreeUpdater DTU(AR.DT, DomTreeUpdater::UpdateStrategy::Lazy);
		auto parentLoop = L.getParentLoop();
		if (!parentLoop) {
			throw std::runtime_error("hwthls.loop.flattenusingif.enable in loop without parent (no parent to flatten this loop into)");
		}
		Loop_setHwtHlsLoopID(L, nullptr); // current loop will be flattened into parent
		Changed = LoopFlattenUsingIfPass_flatten(*parentLoop, L, AR, DTU,
				MSSAU ? &*MSSAU : nullptr, U);

		if (Changed) {
			assert(!verifyFunction(F, &errs()));
			U.markLoopNestChanged(true);
		}
		for (auto &L0 : AR.LI) {
			L0->verifyLoop();
		}
	}
	if (!Changed)
		return PreservedAnalyses::all();

	if (AR.MSSA && VerifyMemorySSA)
		AR.MSSA->verifyMemorySSA();
	PreservedAnalyses PA;
	return PA;
}

}
