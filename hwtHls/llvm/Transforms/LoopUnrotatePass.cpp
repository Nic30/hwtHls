#include <hwtHls/llvm/Transforms/LoopUnrotatePass.h>

#include <map>
#include <llvm/Analysis/AssumptionCache.h>
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
#include <llvm/Transforms/Utils/LoopUtils.h>

#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

using namespace llvm;
#define DEBUG_TYPE "loop-unrotate"

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

void rewriteGuardedDoWhileToWhile(llvm::Loop &L, LoopInfo &LI,
		TargetLibraryInfo &TLI, std::map<Value*, Value*> ConditionValueMap,
		BasicBlock *Guard, BasicBlock *LoopHeader, BasicBlock *LoopExit,
		BasicBlock *GuardExit,
		SmallVector<RotatedLoopAssociatedPHIs> &associatedPHIs,
		Value *GuardBranchCondition, Value *LoopHeaderExitCondition) {
	L.addBasicBlockToLoop(Guard, LI);
	auto L1 = LI.getLoopFor(LoopExit);
	if (L1 != nullptr) {
		L1->removeBlockFromLoop(LoopExit);
		if (L1->block_begin() == L1->block_end())
			LI.erase(L1);
	}

	// reroute all jumps to header to jump unconditionally to guard
	SmallVector<BasicBlock*, 4> OriginalGuardPredecessors;
	for (auto *Pred : predecessors(Guard)) {
		OriginalGuardPredecessors.push_back(Pred);
	}
	SmallVector<BasicBlock*, 4> reentrySources;
	for (BasicBlock *HeaderPred : make_early_inc_range(predecessors(LoopHeader))) {
		if (L.contains(HeaderPred)) {
			HeaderPred->getTerminator()->eraseFromParent();
			IRBuilder<> Builder(HeaderPred);
			Builder.CreateBr(Guard);
			reentrySources.push_back(HeaderPred);
		}
	}
	// LoopHeader condition cleanup

	// volatile loads in condition expression in loopHeader block
	// for those we must check if they are used after DCE, because DCE would not remove them automatically
	SmallVector<std::pair<Value*, LoadInst*>, 4> VolatileLoadsInCondExpr;
	for (auto &item : ConditionValueMap) {
		auto e = item.second;
		if (LoadInst *l = dyn_cast<LoadInst>(e)) {
			if (l->isVolatile()) {
				VolatileLoadsInCondExpr.push_back( { item.first, l });
			}
		}
	}

	// cleanup dead condition expression for LoopHeader
	DceWorklist dce(&TLI, nullptr);
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

	// move PHIs from guardExit to guard and update their operands
	for (auto &phis : associatedPHIs) {
		if (phis.inGuardExit) {
			// expected format %v2 = phi i8 [%v1, %guard], [%v.lcssa, %loopExit]
			// collect all data from inGuardExit phi for new phi
			auto phi = phis.inGuardExit;
			assert(phi->getNumIncomingValues() == 2);
			auto fromGuardPredVal = phi->getIncomingValueForBlock(Guard);

			assert(fromGuardPredVal);
			auto *fromLoopReentryVal = phi->getIncomingValueForBlock(LoopExit);
			assert(fromLoopReentryVal);
			assert(fromLoopReentryVal == phis.inLoopExit);
			auto Name = phi->getName();

			if (auto fromLoopReentryValPhi = dyn_cast<PHINode>(
					fromLoopReentryVal)) {
				assert(fromLoopReentryValPhi->getNumIncomingValues() == 1);
				fromLoopReentryVal = fromLoopReentryValPhi->getIncomingValue(0);
			}
			bool livesTroughIterations = phis.inLoopHeader != nullptr
					&& fromLoopReentryVal != fromGuardPredVal;
			// errs() << phis << "\n";
			// errs() << "livesTroughIterations:" << livesTroughIterations << "\n";
			// errs() << "fromGuardPredVal:" << *fromGuardPredVal << "\n";
			// errs() << "fromLoopReentryVal:" << *fromLoopReentryVal << "\n";

			Value *phiReplacement = nullptr;
			if (livesTroughIterations) {
				// construct phi replacement in Guard block
				IRBuilder<> Builder(Guard, Guard->begin());
				auto *newPhi = Builder.CreatePHI(fromGuardPredVal->getType(), 2,
						Name);
				phiReplacement = newPhi;
				assert(OriginalGuardPredecessors.size() != 0);
				for (BasicBlock *Pred : OriginalGuardPredecessors) {
					newPhi->addIncoming(fromGuardPredVal, Pred);
				}
				for (BasicBlock *ReentryPred : reentrySources)
					newPhi->addIncoming(fromLoopReentryVal, ReentryPred);
			} else {
				phiReplacement = fromGuardPredVal;
			}
			// update all phi values to use new phi
			phi->replaceAllUsesWith(phiReplacement);
			phi->eraseFromParent();

			if (phis.inGuard) {
				if (auto inGuardPHI = dyn_cast<PHINode>(phis.inGuard)) {
					if (inGuardPHI->getParent() == Guard) {
						phis.inGuard->replaceAllUsesWith(phiReplacement);
						inGuardPHI->eraseFromParent();
						phis.inGuard = nullptr;
					}
				}
			}
			if (auto fromLoopReentryValPhi = dyn_cast<PHINode>(
					phis.inLoopExit)) {
				fromLoopReentryValPhi->replaceAllUsesWith(phiReplacement);
				fromLoopReentryValPhi->eraseFromParent();
				phis.inLoopExit = nullptr;
			}
			if (phis.inLoopHeader) {
				phis.inLoopHeader->replaceAllUsesWith(phiReplacement);
				phis.inLoopHeader->eraseFromParent();
				phis.inLoopHeader = nullptr;
			}
		} else {
			throw std::runtime_error(
					"NotImplemented - loop private variable with dependency between iterations");
		}
	}
	assert(LoopExit->hasNPredecessors(0));
	LoopExit->eraseFromParent();
}

bool processLoop(llvm::Loop &L, LoopInfo &LI, TargetLibraryInfo &TLI,
		ScalarEvolution *SE, MemorySSAUpdater *MSSAU) {
	bool Changed = false;
	// if (!L.isCanonical(*SE))
	//	return Changed;

	// Detect rotated loops in format:
	// ..code-block ::C
	//     if (x) {
	//       do {
	//       } while (x);
	//     }

	if (BasicBlock *ExitBlock = L.getExitBlock()) {
		if (BasicBlock *PreHeader = L.getLoopPreheader()) {
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
				return Changed;
			}
			auto PreHeaderTerm = PreHeader->getTerminator();
			Value *PreHeaderExitCond = nullptr;
			bool PreHeaderExitCondIsBreak;
			if (auto *PreHeaderBr = dyn_cast<BranchInst>(PreHeaderTerm)) {
				assert(PreHeaderBr->getNumOperands() == 3);
				PreHeaderExitCond = PreHeaderBr->getCondition();
				if (PreHeaderBr->getSuccessor(0) == ExitBlock) {
					PreHeaderExitCondIsBreak = true; // condition in used as loop break
				} else if (PreHeaderBr->getSuccessor(1) == ExitBlock) {
					PreHeaderExitCondIsBreak = false; // condition in used as loop continue
				} else {
					// the successor is not exit block which means this is not a loop guard
					return Changed;
				}
			} else {
				throw std::runtime_error(
						"NotImplementedError LoopUnrotatePass: unknown type of terminator in pre header block");
			}
			SmallVector<llvm::Loop::Edge, 1> ExitEdges;
			L.getExitEdges(ExitEdges);
			if (ExitEdges.size() != 1) {
				// there are multiple jumps from loop body to loop exit, the analysis for this is not implemented
				return Changed;
			}

			Value *ToExitCond = nullptr;
			bool ToExitCondIsBreak;
			if (auto *ToExitTerm = dyn_cast<BranchInst>(
					ExitEdges[0].first->getTerminator())) {
				ToExitCond = ToExitTerm->getCondition();
				if (ToExitTerm->getSuccessor(0) == L.getHeader()) {
					ToExitCondIsBreak = false;
				} else if (ToExitTerm->getSuccessor(1) == L.getHeader()) {
					ToExitCondIsBreak = false;
				} else {
					// latch block somehow does not have jump back to header of the loop
					return Changed;
				}
			} else {
				throw std::runtime_error(
						"NotImplementedError LoopUnrotatePass: unknown type of terminator in latch block");
			}

			std::map<Value*, Value*> valueMap;
			auto isOutsideOfLoop = [&L](Instruction &I) {
				return !L.contains(I.getParent());
			};
			auto isOutsideOfPreHeader = [&PreHeaderBlocks](Instruction &I) {
				return std::find(PreHeaderBlocks.begin(), PreHeaderBlocks.end(),
						I.getParent()) == PreHeaderBlocks.end();
			};
			if (PreHeaderExitCondIsBreak != ToExitCondIsBreak) {
				return Changed; // not implemented operand polarity swap
			}

			if (!matchSameExpression(valueMap, PreHeaderExitCond, ToExitCond,
					isOutsideOfPreHeader, isOutsideOfLoop)) {
				return Changed;
			}
			for (auto &PHI : ExitBlock->phis()) {
				if (any_of(PHI.incoming_values(), [PreHeader, &valueMap](const Use &u) {
					if (auto *I = dyn_cast<Instruction>(u.get())) {
						if (I->getParent() == PreHeader && valueMap.find(I) == valueMap.end()) {
							// [todo] some PHI of exit block uses value defined in preheader block
							// we can not move this PHI as is and instead we have to use SelectInst to select correct
							// value for first iteration
							return true;
						}
					}
					return false;
				})) {
					return Changed;
				}
			}
			//writeCFGToDotFile(*L.getHeader()->getParent(),
			//		"LoopUnrotatePass.dot", nullptr, nullptr);
			//errs() << "loop:" << L << "\n";
			//errs() << "PreHeader:" << PreHeader->getName() << "\n";
			//errs() << "ExitBlock:" << ExitBlock->getName() << "\n";
			//errs() << "PreHeaderExitCondIsBreak: "
			//		<< PreHeaderExitCondIsBreak << " ToExitCondIsBreak:"
			//		<< ToExitCondIsBreak << "\n";
			//errs() << "PreHeaderExitCond:" << *PreHeaderExitCond << "\n";
			//errs() << "ToExitCond:" << *ToExitCond << "\n";
			//errs() << "valueMap\n";
			//for (auto v : valueMap) {
			//	errs() << "    " << *v.first << "\n";
			//	errs() << "        " << *v.second << "\n";
			//}
			BasicBlock *Guard = PreHeader;
			BasicBlock *LoopHeader = L.getHeader();
			BasicBlock *LoopExit = L.getExitBlock();
			BasicBlock *GuardExit = ExitBlock;

			SmallVector<RotatedLoopAssociatedPHIs> associatedPHIs;
			if (!collectAssociatedPHIs(L, Guard, LoopHeader, LoopExit,
					GuardExit, associatedPHIs)) {
				return Changed;
			}
			rewriteGuardedDoWhileToWhile(L, LI, TLI, valueMap, Guard,
					LoopHeader, LoopExit, GuardExit, associatedPHIs,
					PreHeaderExitCond, ToExitCond);
			Changed = true;
			//writeCFGToDotFile(*L.getHeader()->getParent(),
			//		"LoopUnrotatePassUpdated.dot", nullptr, nullptr);
			Function &F = *L.getHeader()->getParent();
			assert(!llvm::verifyFunction(F, &errs()));
		}
	}
	if (!Changed)
		return Changed;
	// take PHIs from loop header, take PHIs from exit block and merge and move them to guard block,
	// replace PHIs in exit block with a value which is coming from the loop body

	//// Anything ScalarEvolution may know about this loop or the PHI nodes
	//// in its header will soon be invalidated. We should also invalidate
	//// all outer loops because insertion and deletion of blocks that happens
	//// during the rotation may violate invariants related to backedge taken
	//// infos in them.
	if (SE) {
		SE->forgetTopmostLoop(&L);
		// We may hoist some instructions out of loop. In case if they were cached
		// as "loop variant" or "loop computable", these caches must be dropped.
		// We also may fold basic blocks, so cached block dispositions also need
		// to be dropped.
		SE->forgetBlockAndLoopDispositions();
	}

	LLVM_DEBUG(dbgs() << "LoopUnrotation: unrotating "; L.dump());
	if (MSSAU && VerifyMemorySSA)
		MSSAU->getMemorySSA()->verifyMemorySSA();
	return Changed;
}

llvm::PreservedAnalyses LoopUnrotatePass::run(llvm::Loop &L,
		llvm::LoopAnalysisManager &AM, llvm::LoopStandardAnalysisResults &AR,
		llvm::LPMUpdater &U) {
	//const DataLayout &DL = L.getHeader()->getModule()->getDataLayout();
	//const SimplifyQuery SQ = getBestSimplifyQuery(AR, DL);

	//bool PrepareForLTO = false;
	std::optional<MemorySSAUpdater> MSSAU;
	if (AR.MSSA)
		MSSAU = MemorySSAUpdater(AR.MSSA);
	// maximum header size for automatic loop rotation
	//int Threshold = 16;
	//bool Changed = LoopRotation(&L, &AR.LI, &AR.TTI, &AR.AC, &AR.DT, &AR.SE,
	//                            MSSAU ? &*MSSAU : nullptr, SQ, false, Threshold,
	//                            false, PrepareForLTO);
	bool Changed = processLoop(L, AR.LI, AR.TLI, &AR.SE,
			MSSAU ? &*MSSAU : nullptr);
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

