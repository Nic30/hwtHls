#include "LoopRotationNormalizationPass.h"

#include <map>

#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Analysis/LazyBlockFrequencyInfo.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/LoopPass.h>
#include <llvm/Analysis/MemorySSA.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
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
#include <llvm/Transforms/Utils/LoopRotationUtils.h>

#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/utils/loopMerging.h>
#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

using namespace llvm;

#define DEBUG_TYPE "loop-rotation-normalization"
// #define DEBUG_DUMP_CFG_AFTER_EACH_STEP
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(x) x

namespace hwtHls {

BasicBlock::const_iterator skipSingleEntryPhis(BasicBlock::const_iterator it) {
	while (true) {
		if (auto *phi = dyn_cast<PHINode>(&*it)) {
			if (phi->getNumIncomingValues() == 1) {
				++it;
				continue;
			}
		}
		return it;
	}
}

bool isEmptyLinearlyConnectedBlock(const llvm::BasicBlock &BB) {
	return &*skipSingleEntryPhis(BB.begin()) == BB.getTerminator()
			&& BB.getSingleSuccessor() && BB.getSinglePredecessor();
}
/*
 * Check if two expressions are the same but input terms may differ
 * :param valueMap: dictionary mapping expression parts from v0 to v1
 * :param isHandle0: predicate to check if the instructions a boundary of searched expression  (in search use->def) for v0
 * :param isHandle1: same as isHandle0 but for v1
 * */
bool matchSameExpression(std::map<Value*, Value*> &valueMap, Value *v0,
		Value *v1, std::function<bool(Instruction&)> isHandle0,
		std::function<bool(Instruction&)> isHandle1) {
	if (v0 == v1)
		return true;

	auto curMatch = valueMap.find(v0);
	if (curMatch != valueMap.end())
		return curMatch->second == v1;

	Constant *c0 = dyn_cast<Constant>(v0);
	Constant *c1 = dyn_cast<Constant>(v1);
	if (c0 && c1) {
		return c0 == c1;
	} else if (c0 || c1) {
		return false;
	}
	auto i0 = dyn_cast<Instruction>(v0);
	auto i1 = dyn_cast<Instruction>(v1);
	if (i0 == nullptr || i1 == nullptr) {
		return false;
	}
	// check for handles
	if (isHandle0(*i0)) {
		if (isHandle1(*i1)) {
			// checked that the there is no valueMap[v0] in the beginning of this function
			valueMap[v0] = v1;
			return true;
		} else {
			return false;
		}

	} else if (isHandle1(*i1)) {
		return false;
	}
	if (i0->getOpcode() != i1->getOpcode()
			|| i0->getNumOperands() != i1->getNumOperands())
		return false;
	auto i1op = i1->operand_values().begin();
	for (Value *i0op : i0->operand_values()) {
		if (!matchSameExpression(valueMap, i0op, *i1op, isHandle0, isHandle1)) {
			return false;
		}
		++i1op;
	}
	valueMap[v0] = v1;
	return true;
}

struct RotatedLoopAssociatedPHIs {
	Value *inGuard; // guard may contain PHI for this variable but it may not be there
	PHINode *inLoopHeader; // must be there because value trough loop iteration
	Value *inLoopExit; // should be created by LCSSA or constant
	PHINode *inGuardExit; // select between value computed by loop and from early exit
	RotatedLoopAssociatedPHIs() :
			inGuard(nullptr), inLoopHeader(nullptr), inLoopExit(nullptr), inGuardExit(
					nullptr) {
	}
	void print(llvm::raw_ostream &OS) const {
		OS << "{\n";
		auto printPair = [&OS](Value *v, const std::string &name) {
			OS << "    " << name << ": ";
			if (v) {
				OS << *v << "\n";
			} else {
				OS << "nullptr\n";
			}
		};
		printPair(inGuard, "inGuard");
		printPair(inLoopHeader, "inLoopHeader");
		printPair(inLoopExit, "inLoopExit");
		printPair(inGuardExit, "inGuardExit");
		OS << "}";
	}
};

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::RotatedLoopAssociatedPHIs &V) {
	V.print(OS);
	return OS;
}

bool collectAssociatedPHIs(llvm::Loop &L, BasicBlock *Guard,
		BasicBlock *LoopHeader, BasicBlock *LoopExit, BasicBlock *GuardExit,
		SmallVector<RotatedLoopAssociatedPHIs> &result) {
	std::set<Value*> inLoopHeaderResolved;
	// handle variables modified in loop and live after loop exit
	for (PHINode &phi : GuardExit->phis()) {
		if (phi.getNumIncomingValues() != 2 || phi.getIncomingBlock(0) != Guard
				|| phi.getIncomingBlock(1) != LoopExit) {
			return false;
		}
		RotatedLoopAssociatedPHIs res;
		res.inGuardExit = &phi;
		res.inLoopExit = phi.getIncomingValueForBlock(LoopExit);
		res.inGuard = phi.getIncomingValueForBlock(Guard);

		if (auto *inLoopExit = dyn_cast<PHINode>(res.inLoopExit)) {
			if (inLoopExit->getParent() == LoopExit) {
				if (inLoopExit->getNumIncomingValues() != 1) {
					// [todo] find the phi in loopHeader for this loopExit phi
					return false;
				}
				BasicBlock *exitingBlock = inLoopExit->getIncomingBlock(0);
				auto *fromLoopV = inLoopExit->getIncomingValue(0);
				auto *fromLoopVConst = dyn_cast<Constant>(fromLoopV);
				if (fromLoopVConst == nullptr) {
					for (PHINode &phi1 : LoopHeader->phis()) {
						if (inLoopHeaderResolved.find(&phi1)
								!= inLoopHeaderResolved.end())
							continue;
						if (phi1.getIncomingValueForBlock(exitingBlock)
								== fromLoopV) {
							inLoopHeaderResolved.insert(&phi1);
							res.inLoopHeader = &phi1;
							break;
						}
					}
					// if value is always computed new in each iteration inLoopHeader is nullptr
				}
			}
		}
		result.push_back(res);
	}
	// handle variables live and modified between loop iterations and dead after loop
	for (PHINode &phi1 : LoopHeader->phis()) {
		if (inLoopHeaderResolved.find(&phi1) != inLoopHeaderResolved.end())
			continue;
		llvm_unreachable(
				"NotImplemented var local to loop live between iterations");
	}
	// [fixme] check that the loop exit contains only compatible PHIs
	return true;
}

void moveBlockBetweenLoops(LoopInfo &LI, BasicBlock *BB, llvm::Loop *Lsrc,
		llvm::Loop *Ldst) {
	Ldst->addBlockEntry(BB);
	//Lsrc->removeBlockFromLoop(BB);
	//LI.changeLoopFor(BB, Ldst);
}

BasicBlock* moveGuardAndGuardExitBlocksToLoop(llvm::Loop **L, LoopInfo &LI,
		ScalarEvolution *SE, LPMUpdater &LPMU, BasicBlock *Guard,
		BasicBlock *LoopHeader, BasicBlock *LoopExit, BasicBlock *GuardExit) {
	//auto L0 = LI.getLoopFor(Guard);
	//if (!L0 || L0->getHeader() != Guard) {
	//	auto SplitPoint = Guard->begin();
	//	while (isa<PHINode>(SplitPoint)) {
	//		++SplitPoint;
	//	}
	//	//create a new preheader before guard block, because Guard was not originally a loop header
	//	SplitBlock(Guard, &*SplitPoint, (DomTreeUpdater*)nullptr, &LI, nullptr, Guard->getName() + ".preheader");
	//}
	// move Guard, GuardExit into loop
	SmallVector<BasicBlock*> blocksToMoveIntoLoop;
	SmallVector<BasicBlock*> blocksToSearch;
	BasicBlock *originalPreHeader = nullptr; // last block in linear sequence of blocks between Guard and LoopHeader

	blocksToSearch.push_back(Guard);
	for (; blocksToSearch.size();) {
		BasicBlock *BB = blocksToSearch.pop_back_val();
		if (BB == LoopHeader || BB == GuardExit)
			continue;
		originalPreHeader = BB;
		blocksToMoveIntoLoop.push_back(BB);
		for (auto *SucBB : successors(BB)) {
			blocksToSearch.push_back(SucBB);
		}
	}
	bool guardLoopWasUsed = false;
	for (auto *BB : blocksToMoveIntoLoop) {
		auto L0 = LI.getLoopFor(BB);
		if (L0 == *L) {
			// already in this loop
		} else if (L0 != nullptr) {
			if (L0->getHeader() == Guard) {
				LLVM_DEBUG(
						dbgs() << "LoopUnroll: Merging loops " << **L
								<< "\n -> \n" << *L0 << "\n");
				// merge to parent loop
				mergeNestedLoops(LI, SE, LPMU, *L, L0);
				*L = L0;
				guardLoopWasUsed = true;
			} else {
				assert(L0->contains(*L));
				assert(BB != L0->getHeader());
				LLVM_DEBUG(
						dbgs() << "LoopUnroll: Move between loops "
								<< BB->getName() << " \n" << *L0 << " -> "
								<< **L << "\n");
				moveBlockBetweenLoops(LI, BB, L0, *L);
			}
		} else {
			assert(!(*L)->contains(BB));
			(*L)->addBlockEntry(BB);
		}
	}
	if (!guardLoopWasUsed)
		(*L)->moveToHeader(Guard);
	return originalPreHeader;
}

void runDCEOnLoopConditions(
		SmallVector<std::pair<Value*, LoadInst*>, 4> &VolatileLoadsInCondExpr,
		TargetLibraryInfo &TLI, Value *LoopHeaderExitCondition) {
	// cleanup dead condition expression for LoopHeader
	DceWorklist dce(&TLI);
	BasicBlock::iterator curI; // dummy value
	if (auto I = dyn_cast<Instruction>(LoopHeaderExitCondition)) {
		dce.tryRemoveIfDead(*I, curI);
	}
	for (;;) {
		dce.runToCompletition(curI);
		// handle the case for volatile load which would not normally be removed
		for (auto &ld : VolatileLoadsInCondExpr) {
			if (ld.second != nullptr) {
				if (!ld.second->use_empty()) {
					ld.second->replaceAllUsesWith(ld.first);
				}
				for (Use &U : ld.second->operands()) {
					if (auto *I = dyn_cast<Instruction>(U.get())) {
						dce.insert(*I);
					}
				}
				ld.second->eraseFromParent();
				ld.second = nullptr;
				dce.runToCompletition(curI);
			}
		}
		if (dce.empty())
			break;
	}
}

void rerouteJumpsToLoopHeaderToGuardBlock(llvm::Loop &L, DomTreeUpdater &DTU, MemorySSAUpdater *MSSAU, BasicBlock *Guard,
		BasicBlock *LoopHeader, BasicBlock *LoopExit,
		BasicBlock *originalPreHeader,
		SmallVector<BasicBlock*, 4> &reentrySources) {
	// reroute all jumps to header to jump unconditionally to guard

	// case where LoopHeader jumps to Guard
	if (any_of(predecessors(Guard), [LoopHeader](BasicBlock *BB) {
		return BB == LoopHeader;
	})) {
		for (PHINode &PHI : Guard->phis()) {
			PHI.replaceIncomingBlockWith(LoopHeader, Guard);
		}
	}
	for (auto pred : predecessors(Guard)) {
		assert(pred != LoopHeader);
		assert(pred != LoopExit);
	}
	SmallVector<DominatorTree::UpdateType, 2> Updates;

	for (BasicBlock *HeaderPred : make_early_inc_range(predecessors(LoopHeader))) {
		if (HeaderPred != Guard && HeaderPred != originalPreHeader
				&& L.contains(HeaderPred)) {
			assert(HeaderPred != LoopExit);
			bool guardAlreadyHasThisPredec = any_of(predecessors(Guard),
					[HeaderPred](BasicBlock *BB) {
						return BB == HeaderPred;
					});

			Updates.push_back( { DominatorTree::Delete, HeaderPred, LoopHeader });
			Updates.push_back( { DominatorTree::Insert, HeaderPred, Guard });
			// DTU, MSSAU update as done in llvm::splitBlockBefore
			DTU.applyUpdates(Updates);
			DTU.flush();
			if (MSSAU) {
				MSSAU->applyUpdates(Updates, DTU.getDomTree());
			}
			Updates.clear();

			HeaderPred->getTerminator()->eraseFromParent();

			IRBuilder<> Builder(HeaderPred);
			Builder.CreateBr(Guard);
			reentrySources.push_back(HeaderPred);
			// when re-routing LoopHeader predecessors to Guard we have to update PHIs there
			if (!guardAlreadyHasThisPredec) {
				//if (HeaderPred != LoopHeader) {
				//	// else this would be added as re-entry later
				for (PHINode &PHI : Guard->phis()) {
					PHI.addIncoming(&PHI, HeaderPred);
				}
				//}
			}
		}
	}
}

void movePHIFromGuardExitToGuardBlock(RotatedLoopAssociatedPHIs &phis,
		BasicBlock *GuardExit, BasicBlock *Guard, BasicBlock *LoopExit,
		const SmallVector<BasicBlock*, 4> &reentrySources,
		const SmallVector<BasicBlock*, 4> &OriginalGuardPredecessors) {
	if (phis.inGuardExit) {
		// expected format %v2 = phi i8 [%v1, %guard], [%v.lcssa, %loopExit]
		// collect all data from inGuardExit phi for new phi
		auto phi = phis.inGuardExit;
		assert(phi->getParent() == GuardExit);
		assert(phi->getNumIncomingValues() == 2);
		auto fromGuardPredVal = phi->getIncomingValueForBlock(Guard);
		assert(fromGuardPredVal);
		//if (auto* fromGuardPredValPHI = dyn_cast<PHINode>(fromGuardPredVal)) {
		//	if (fromGuardPredValPHI->getNumIncomingValues() == 1) {
		//		fromGuardPredVal = fromGuardPredValPHI->getIncomingValue(0);
		//	}
		//}
		auto *fromLoopReentryVal = phi->getIncomingValueForBlock(LoopExit);
		assert(fromLoopReentryVal);
		assert(fromLoopReentryVal == phis.inLoopExit);
		auto Name = phi->getName();
		if (auto fromLoopReentryValPhi = dyn_cast<PHINode>(
				fromLoopReentryVal)) {
			if (fromLoopReentryValPhi->getParent() == LoopExit) {
				assert(fromLoopReentryValPhi->getNumIncomingValues() == 1);
				fromLoopReentryVal = fromLoopReentryValPhi->getIncomingValue(0);
			}
		}
		bool livesTroughIterations = phis.inLoopHeader != nullptr
				&& fromLoopReentryVal != fromGuardPredVal;
		LLVM_DEBUG(dbgs() << phis << "\n" << //
				"livesTroughIterations:" << livesTroughIterations << "\n" << //
				"fromGuardPredVal:" << *fromGuardPredVal << "\n" << //
				"fromLoopReentryVal:" << *fromLoopReentryVal << "\n");
		auto *GuardPhi = dyn_cast<PHINode>(fromGuardPredVal);
		if (GuardPhi) {
			if (GuardPhi->getParent() != Guard) {
				GuardPhi = nullptr;
			}
		}

		Value *phiReplacement = nullptr;
		if (livesTroughIterations) {
			// construct phi replacement in Guard block
			IRBuilder<> Builder(Guard, Guard->begin());
			bool GuardPhiExits = GuardPhi != nullptr;
			if (!GuardPhiExits)
				GuardPhi = Builder.CreatePHI(fromGuardPredVal->getType(), 2,
						Name);

			phiReplacement = GuardPhi;
			if (!GuardPhiExits) {
				assert(OriginalGuardPredecessors.size() != 0);
				for (BasicBlock *Pred : OriginalGuardPredecessors) {
					GuardPhi->addIncoming(fromGuardPredVal, Pred);
				}
			}
			for (BasicBlock *ReentryPred : reentrySources)
				GuardPhi->addIncoming(fromLoopReentryVal, ReentryPred);
		} else {
			phiReplacement = fromGuardPredVal;
		}
		// update all phi values to use new phi
		if (phi != phiReplacement) {
			phi->replaceAllUsesWith(phiReplacement);
			phi->eraseFromParent();
		}
		if (phis.inGuard && phiReplacement != phis.inGuard) {
			if (auto inGuardPHI = dyn_cast<PHINode>(phis.inGuard)) {
				if (inGuardPHI->getParent() == Guard) {
					phis.inGuard->replaceAllUsesWith(phiReplacement);
					inGuardPHI->eraseFromParent();
					phis.inGuard = nullptr;
				}
			}
		}
		if (phis.inLoopExit && phiReplacement != phis.inLoopExit) {
			if (auto fromLoopReentryValPhi = dyn_cast<PHINode>(
					phis.inLoopExit)) {
				fromLoopReentryValPhi->replaceAllUsesWith(phiReplacement);
				fromLoopReentryValPhi->eraseFromParent();
				phis.inLoopExit = nullptr;
			}
		}
		if (phis.inLoopHeader && phiReplacement != phis.inLoopHeader) {
			phis.inLoopHeader->replaceAllUsesWith(phiReplacement);
			phis.inLoopHeader->eraseFromParent();
			phis.inLoopHeader = nullptr;
		}
	} else {
		throw std::runtime_error(
				"NotImplemented - loop private variable with dependency between iterations");
	}
}

struct LoopAnalysisResultIfDoWhile {
	std::map<Value*, Value*> valueMap; // ConditionValueMap
	BasicBlock *Guard;
	BasicBlock *LoopHeader;
	BasicBlock *LoopExit;
	BasicBlock *GuardExit;
	SmallVector<RotatedLoopAssociatedPHIs> associatedPHIs;
	Value *PreHeaderExitCond; // GuardBranchCondition
	Value *ToExitCond; // LoopHeaderExitCondition
};

/*
 * Rewrite
 *
 * Guard:
 * if (cond()) {
 *   // there may be potential loop preheader
 *   do {
 *   	LoopHeader:
 *   	body:
 *   } while (cond());
 *   LoopExit:
 * }
 * GuardExit:
 *
 * to
 * Guard:
 * while (cond()) {
 *   LoopHeader:
 *   body:
 * }
 * GuardExit:
 *
 * :note: LoopSimplify format specifies that loop has pre header is a preheader
 *
 * */
void rewriteGuardedDoWhileToWhile(llvm::Loop *L, LoopInfo &LI,
		TargetLibraryInfo &TLI, ScalarEvolution *SE, DomTreeUpdater &DTU, MemorySSAUpdater *MSSAU, llvm::LPMUpdater &LPMU,
		LoopAnalysisResultIfDoWhile &analysisRes) {
	auto origL = L;
	auto *originalPreHeader = moveGuardAndGuardExitBlocksToLoop(&L, LI, SE,
			LPMU, analysisRes.Guard, analysisRes.LoopHeader,
			analysisRes.LoopExit, analysisRes.GuardExit);

	assert(analysisRes.Guard != analysisRes.LoopExit);
	// remove LoopExit because we remove it completely from IR
	auto L1 = LI.getLoopFor(analysisRes.LoopExit);
	if (L1 != nullptr) {
		LI.removeBlock(analysisRes.LoopExit);
		//L1->removeBlockFromLoop(LoopExit);
		if (L1->block_begin() == L1->block_end()) {
			//LI.removeBlock(LoopExit);
			LI.erase(L1);
		}
	}

	SmallVector<BasicBlock*, 4> OriginalGuardPredecessors;
	for (auto *Pred : predecessors(analysisRes.Guard)) {
		OriginalGuardPredecessors.push_back(Pred);
	}
	SmallVector<BasicBlock*, 4> reentrySources;
	rerouteJumpsToLoopHeaderToGuardBlock(*L, DTU, MSSAU, analysisRes.Guard,
			analysisRes.LoopHeader, analysisRes.LoopExit, originalPreHeader,
			reentrySources);

	// LoopHeader condition cleanup
	// volatile loads in condition expression in loopHeader block
	// for those we must check if they are used after DCE, because DCE would not remove them automatically
	SmallVector<std::pair<Value*, LoadInst*>, 4> VolatileLoadsInCondExpr;
	for (auto &item : analysisRes.valueMap) {
		auto e = item.second;
		if (LoadInst *l = dyn_cast<LoadInst>(e)) {
			if (l->isVolatile()) {
				VolatileLoadsInCondExpr.push_back( { item.first, l });
			}
		}
	}

	// cleanup dead condition expression for LoopHeader
	runDCEOnLoopConditions(VolatileLoadsInCondExpr, TLI,
			analysisRes.ToExitCond);

	// move PHIs from guardExit to guard and update their operands
	for (auto &phis : analysisRes.associatedPHIs) {
		movePHIFromGuardExitToGuardBlock(phis, analysisRes.GuardExit,
				analysisRes.Guard, analysisRes.LoopExit, reentrySources,
				OriginalGuardPredecessors);
	}

	// LoopHeader is now behind Guard
	assert(analysisRes.LoopHeader->hasNPredecessors(1));
	//L->removeBlockFromLoop(LoopHeader);
	//LI.removeBlock(LoopHeader);
	//LoopHeader->eraseFromParent();
	// LoopExit is now replaced by GuardExit
	assert(analysisRes.LoopExit->hasNPredecessors(0));
	//auto LExit = LI.getLoopFor(LoopExit);
	//if (LExit)
	//	LI.removeBlock(LoopExit);
	if (MSSAU) {
		SmallSetVector<BasicBlock *, 8> removedBlocks;
		removedBlocks.insert(analysisRes.LoopExit);
		MSSAU->removeBlocks(removedBlocks);
	}
	DTU.deleteBB(analysisRes.LoopExit);
	DTU.flush();
    if (SE) {
      // Merging blocks may remove blocks reference in the block disposition cache. Clear the cache.
      SE->forgetBlockAndLoopDispositions();
    }
	// analysisRes.LoopExit->eraseFromParent(); // done in DTU.deleteBB
	//L->verifyLoop();

	if (origL == L) {
		//// Anything ScalarEvolution may know about this loop or the PHI nodes
		//// in its header will soon be invalidated. We should also invalidate
		//// all outer loops because insertion and deletion of blocks that happens
		//// during the rotation may violate invariants related to backedge taken
		//// infos in them.
		if (SE) {
			SE->forgetTopmostLoop(L);
			// We may hoist some instructions out of loop. In case if they were cached
			// as "loop variant" or "loop computable", these caches must be dropped.
			// We also may fold basic blocks, so cached block dispositions also need
			// to be dropped.
			SE->forgetBlockAndLoopDispositions();
		}
		LPMU.markLoopNestChanged(true);
	}
}

std::optional<LoopAnalysisResultIfDoWhile> analyzeLoopForIfDoWhile(
		llvm::Loop &L) {
	// if (!L.isCanonical(*SE))
	//	return Changed;

	// Detect rotated loops in format:
	// ..code-block ::C
	//     if (x) {
	//       do {
	//       } while (x);
	//     }
	LoopAnalysisResultIfDoWhile res;
	BasicBlock *ExitBlock = L.getExitBlock();
	if (!ExitBlock)
		return std::nullopt;

	BasicBlock *PreHeader = L.getLoopPreheader();
	if (!PreHeader)
		return std::nullopt;
	while (isEmptyLinearlyConnectedBlock(*ExitBlock)) {
		// skip empty linear blocks between exit block and the potential block where loop guard jumps
		ExitBlock = ExitBlock->getSingleSuccessor();
	}
	llvm::SmallVector<BasicBlock*, 4> PreHeaderBlocks;
	while (isEmptyLinearlyConnectedBlock(*PreHeader)) {
		// skip linear blocks between header(body) block and the
		PreHeaderBlocks.push_back(PreHeader);
		PreHeader = PreHeader->getSinglePredecessor();
	}
	PreHeaderBlocks.push_back(PreHeader);
	if (succ_size(PreHeader) != 2) {
		return std::nullopt;
	}
	auto PreHeaderTerm = PreHeader->getTerminator();
	res.PreHeaderExitCond = nullptr;
	bool PreHeaderExitCondIsBreak;
	if (auto *PreHeaderBr = dyn_cast<BranchInst>(PreHeaderTerm)) {
		assert(PreHeaderBr->getNumOperands() == 3);
		res.PreHeaderExitCond = PreHeaderBr->getCondition();
		if (PreHeaderBr->getSuccessor(0) == ExitBlock) {
			PreHeaderExitCondIsBreak = true; // condition in used as loop break
		} else if (PreHeaderBr->getSuccessor(1) == ExitBlock) {
			PreHeaderExitCondIsBreak = false; // condition in used as loop continue
		} else {
			// the successor is not exit block which means this is not a loop guard
			return std::nullopt;
		}
	} else {
		throw std::runtime_error(
				"NotImplementedError LoopUnrotatePass: unknown type of terminator in pre header block");
	}
	SmallVector<llvm::Loop::Edge, 1> ExitEdges;
	L.getExitEdges(ExitEdges);
	if (ExitEdges.size() != 1) {
		// there are multiple jumps from loop body to loop exit, the analysis for this is not implemented
		return std::nullopt;
	}

	res.ToExitCond = nullptr;
	bool ToExitCondIsBreak;
	if (auto *ToExitTerm = dyn_cast<BranchInst>(
			ExitEdges[0].first->getTerminator())) {
		res.ToExitCond = ToExitTerm->getCondition();
		if (ToExitTerm->getSuccessor(0) == L.getHeader()) {
			ToExitCondIsBreak = false;
		} else if (ToExitTerm->getSuccessor(1) == L.getHeader()) {
			ToExitCondIsBreak = false;
		} else {
			// latch block somehow does not have jump back to header of the loop
			return std::nullopt;
		}
	} else {
		throw std::runtime_error(
				"NotImplementedError " DEBUG_TYPE ": unknown type of terminator in latch block");
	}

	std::map<Value*, Value*> &valueMap = res.valueMap;
	auto isOutsideOfLoop = [&L](Instruction &I) {
		return !L.contains(I.getParent());
	};
	auto isOutsideOfPreHeader = [&PreHeaderBlocks](Instruction &I) {
		return std::find(PreHeaderBlocks.begin(), PreHeaderBlocks.end(),
				I.getParent()) == PreHeaderBlocks.end();
	};
	if (PreHeaderExitCondIsBreak != ToExitCondIsBreak) {
		return std::nullopt; // not implemented operand polarity swap
	}

	if (!matchSameExpression(valueMap, res.PreHeaderExitCond, res.ToExitCond,
			isOutsideOfPreHeader, isOutsideOfLoop)) {
		return std::nullopt;
	}
	for (auto &PHI : ExitBlock->phis()) {
		if (any_of(PHI.incoming_values(), [PreHeader, &valueMap](const Use &u) {
			if (auto *I = dyn_cast<Instruction>(u.get())) {
				if (I->getParent() == PreHeader && !isa<PHINode>(I) && // for phi we can merge operands
						valueMap.find(I) == valueMap.end()) {
					// [todo] some PHI of exit block uses value defined in preheader block
					// we can not move this PHI as is and instead we have to use SelectInst to select correct
					// value for first iteration
					return true;
				}
			}
			return false;
		})) {
			return std::nullopt;
		}
	}
	LLVM_DEBUG(dbgs() << "LoopUnrotate: loop:" << L << "\n");
	LLVM_DEBUG(dbgs() << "PreHeader: " << PreHeader->getName() << "\n");
	LLVM_DEBUG(dbgs() << "ExitBlock: " << ExitBlock->getName() << "\n");
	LLVM_DEBUG(
			dbgs() << "PreHeaderExitCondIsBreak: " << PreHeaderExitCondIsBreak
					<< " ToExitCondIsBreak: " << ToExitCondIsBreak << "\n");
	LLVM_DEBUG(
			dbgs() << "PreHeaderExitCond: " << *res.PreHeaderExitCond << "\n");
	LLVM_DEBUG(dbgs() << "ToExitCond: " << *res.ToExitCond << "\n");
	LLVM_DEBUG(dbgs() << "valueMap\n");
#ifndef NDEBUG
	if (::llvm::DebugFlag && ::llvm::isCurrentDebugType(DEBUG_TYPE)) {
		for (auto v : valueMap) {
			dbgs() << "    " << *v.first << "\n";
			dbgs() << "        " << *v.second << "\n";
		}
	}
#endif
	res.Guard = PreHeader;
	res.LoopHeader = L.getHeader();
	res.LoopExit = L.getExitBlock();
	res.GuardExit = ExitBlock;

	if (!collectAssociatedPHIs(L, res.Guard, res.LoopHeader, res.LoopExit,
			res.GuardExit, res.associatedPHIs)) {
		return std::nullopt;
	}
	return res;
}

bool headerForRotationIsCostly(llvm::Loop &L) {
	// for header and linear sequence of blocks after it check the cost of instructions
	auto Header = L.getHeader();
	while (Header) {
		for (Instruction& I: *Header) {
			//TTI.getInstructionCost(U, Operands, CostKind)
			if (I.mayReadOrWriteMemory())
				return true;
		}
		Header = Header->getUniqueSuccessor();
	}
	return false;
}

bool LoopRotationNormalizationPass::processLoop(llvm::Loop &L, llvm::LoopStandardAnalysisResults &AR,
		DomTreeUpdater &DTU, MemorySSAUpdater *MSSAU, llvm::LPMUpdater &LPMU) {
	bool Changed = false;
	auto analysis = analyzeLoopForIfDoWhile(L);
#ifdef DEBUG_DUMP_CFG_AFTER_EACH_STEP
		auto &F = *L.getHeader()->getParent();
		if (dbgCntr == 0)
			writeCFGToDotFile(*L.getHeader()->getParent(), DEBUG_TYPE "." + std::to_string(dbgCntr++) + ".dot",
					AR.BFI, AR.BPI);
#endif

	if (analysis.has_value()) {
		LoopAnalysisResultIfDoWhile &analysisRes = analysis.value();
#ifdef DEBUG_DUMP_CFG_AFTER_EACH_STEP
		writeCFGToDotFile(F, DEBUG_TYPE "." + std::to_string(dbgCntr++) + ".unrotate-before.dot", AR.BFI, AR.BPI);
		if (verifyFunction(F, &errs())) {
			throw std::runtime_error("Function broken by LoopRotationNormalizationPass");
		}
#endif
		rewriteGuardedDoWhileToWhile(&L, AR.LI, AR.TLI, &AR.SE, DTU, MSSAU, LPMU,
				analysisRes);
		Changed = true;
#ifdef DEBUG_DUMP_CFG_AFTER_EACH_STEP
		writeCFGToDotFile(F, DEBUG_TYPE "." + std::to_string(dbgCntr++) + ".unrotate.dot", AR.BFI, AR.BPI);
		if (verifyFunction(F, &errs())) {
			throw std::runtime_error("Function broken by LoopRotationNormalizationPass");
		}
#endif
	} else {
		bool EnableHeaderDuplication = !headerForRotationIsCostly(L);
		// The default maximum header size for automatic loop rotation
		int DefaultRotationThreshold = 0xffff;
		// Run loop-rotation in the prepare-for-lto stage. This option should be used for testing only.
		bool PrepareForLTO = false;
		// Vectorization requires loop-rotation. Use default threshold for loops the
		// user explicitly marked for vectorization, even when header duplication is
		// disabled.
		int Threshold =
				EnableHeaderDuplication
						|| hasVectorizeTransformation(&L) == TM_ForcedByUser ?
						DefaultRotationThreshold : 0;
		const DataLayout &DL = L.getHeader()->getModule()->getDataLayout();
		const SimplifyQuery SQ = getBestSimplifyQuery(AR, DL);
		DTU.flush();
		Changed |= LoopRotation(&L, &AR.LI, &AR.TTI, &AR.AC, &AR.DT, &AR.SE,
				MSSAU, SQ, false, Threshold, false, PrepareForLTO);
#ifdef DEBUG_DUMP_CFG_AFTER_EACH_STEP
		writeCFGToDotFile(F, DEBUG_TYPE "." + std::to_string(dbgCntr++) + ".rotate.dot", AR.BFI, AR.BPI);
#endif
	}

	if (!Changed)
		return Changed;

	// :attention: loop L can now be deleted

	// take PHIs from loop header, take PHIs from exit block and merge and move them to guard block,
	// replace PHIs in exit block with a value which is coming from the loop body

	if (MSSAU && VerifyMemorySSA)
		MSSAU->getMemorySSA()->verifyMemorySSA();
	return Changed;
}

llvm::PreservedAnalyses LoopRotationNormalizationPass::run(llvm::Loop &L,
		llvm::LoopAnalysisManager &AM, llvm::LoopStandardAnalysisResults &AR,
		llvm::LPMUpdater &U) {
	assert(!AR.BFI && !AR.BPI && "NotImplemented");
	std::optional<MemorySSAUpdater> MSSAU;
	if (AR.MSSA)
		MSSAU = MemorySSAUpdater(AR.MSSA);

	DomTreeUpdater DTU(AR.DT, DomTreeUpdater::UpdateStrategy::Lazy);
	bool Changed = processLoop(L, AR, DTU, MSSAU ? &*MSSAU : nullptr, U);
	if (Changed) {
		U.markLoopNestChanged(true);
	}
	for (auto &L0 : AR.LI) {
		L0->verifyLoop();
	}
	DTU.flush();
	assert(AR.DT.verify());

	//AR.LI.verify(AR.DT);
	//AR.SE.verify();
	if (!Changed)
		return PreservedAnalyses::all();

	if (AR.MSSA && VerifyMemorySSA)
		AR.MSSA->verifyMemorySSA();
	PreservedAnalyses PA;
	//auto PA = getLoopPassPreservedAnalyses();
	//if (AR.MSSA)
	//	PA.preserve<MemorySSAAnalysis>();
	return PA;
}

}

