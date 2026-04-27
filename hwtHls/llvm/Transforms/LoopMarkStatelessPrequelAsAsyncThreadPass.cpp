#include <hwtHls/llvm/Transforms/LoopMarkStatelessPrequelAsAsyncThreadPass.h>

#include <unordered_set>

#include <llvm/ADT/STLExtras.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/LoopPass.h>
#include <llvm/Analysis/MemorySSA.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/utils/loopHwtHlsMetadata.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>


using namespace llvm;

#define DEBUG_TYPE "loop-mark-stateless-prequel"
// #define DEBUG_DUMP_CFG_AFTER_EACH_STEP
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(x) x

namespace hwtHls {

const std::string LoopMarkStatelessPrequelAsAsyncThreadPass::METADATA_NAME = "hwthls.loop.mark_stateless_prequel";
const std::string LoopMarkStatelessPrequelAsAsyncThreadPass::METADATA_NAME_followup = LoopMarkStatelessPrequelAsAsyncThreadPass::METADATA_NAME + ".followup";
	
void findIndependentInstr(llvm::LoopInfo &LI, Loop &L, BasicBlock &BB,
						  BasicBlock::iterator BBIt,
						  const std::unordered_set<Instruction *> &incompatible,
						  std::unordered_set<BasicBlock *> &seenBlocks,
						  std::unordered_set<Instruction *> &compatible) {
	seenBlocks.insert(&BB);
	auto T = BB.getTerminator();
	for (auto Iit = BBIt; Iit != BB.end(); ++Iit) {
		Instruction &I = *Iit;
		if (incompatible.contains(&I))
			continue;

		auto isTerm = &I == T;
		if (isTerm && Iit->mayHaveSideEffects() && !isa<LoadInst>(&I) &&
			!isa<StoreInst>(&I)) {
			// this is something unsupported because
			// we do not know if moving it does not cause an issue
			continue;
		}
		bool hasUseOfIncompatible = false;
		for (auto o : I.operand_values()) {
			if (auto oI = dyn_cast<Instruction>(o)) {
				hasUseOfIncompatible = !compatible.contains(oI);
				if (hasUseOfIncompatible)
					break;
			}
		}
		if (!hasUseOfIncompatible) {
			assert(!isa<PHINode>(&I));
			compatible.insert(&I);

			if (isTerm) {
				size_t instrCnt = compatible.size();
				for (auto suc : successors(&BB)) {
					if (suc == L.getHeader())
						continue;
					if (seenBlocks.contains(suc))
						continue;
					if (LI.getLoopFor(suc) != &L)
						continue;
					findIndependentInstr(LI, L, *suc, suc->begin(),
										 incompatible, seenBlocks, compatible);
				}
				if (instrCnt == compatible.size()) {
					// the blocks after this terminator do not contain any
					// relevant instruction, so it is pointless to add this
					// terminator
					compatible.erase(&*Iit);
				}
			}
		}
	}
}

/*
 * :param fn: function which is called for every selected instruction in DFS
 *            order
 */
void walkSelectedInstructions(llvm::LoopInfo &LI, Loop &L, BasicBlock &BB,
							  std::function<bool(Instruction &)> isSelectedfn,
							  std::unordered_set<BasicBlock *> &seenBBs,
							  std::function<void(Instruction &)> fn) {
	if (seenBBs.contains(&BB))
		return;
	seenBBs.insert(&BB);
	for (auto &I : BB) {
		if (!isSelectedfn(I))
			continue;
		fn(I);
		if (I.isTerminator()) {
			for (auto suc : successors(&BB)) {
				if (suc == L.getHeader())
					continue;
				if (LI.getLoopFor(suc) != &L)
					continue;
				walkSelectedInstructions(LI, L, *suc, isSelectedfn, seenBBs, fn);
			}
		}
	}
	return;
}

Value *LoopMarkPassPrototype::findIoDef(Value *io) {
	while (auto _io = dyn_cast<GetElementPtrInst>(io)) {
		io = _io->getPointerOperand();
	}
	return io;
}

void LoopMarkPassPrototype::walkAllUserGepLoadStoreInstructions(
	Value *io, std::function<void(Instruction &)> fn) {
	for (auto U : io->users()) {
		if (auto *UI = dyn_cast<Instruction>(U)) {
			if (isa<LoadInst>(UI) || isa<StoreInst>(UI)) {
				fn(*UI);
			} else if (auto gep = dyn_cast<GetElementPtrInst>(io)) {
				fn(*UI);
				walkAllUserGepLoadStoreInstructions(gep, fn);
			} else {
				llvm_unreachable(
					"NotImplementedError: unexpected IO instruction");
			}
		}
	}
}

bool LoopMarkPassPrototype::allLoadStoreInstrAreCompatible(
	Value *io, std::function<bool(Instruction &)> isCompatibleFn) {
	for (auto *u : io->users()) {
		if (auto UI = dyn_cast<Instruction>(u)) {
			if (auto _io = dyn_cast<GetElementPtrInst>(UI)) {
				if (!allLoadStoreInstrAreCompatible(_io, isCompatibleFn))
					return false;
			} else if (!isCompatibleFn(*UI)) {
				return false;
			}
		}
	}
	return true;
}

void LoopMarkPassPrototype::checkIoIsPrivateToSelectedRegion(
	llvm::LoopInfo &LI, Loop &L, BasicBlock &BB0,
	std::function<bool(Instruction &)> isSelectedFn,
	DenseMap<Value *, bool> &IOcompatibility) {
	std::unordered_set<BasicBlock *> seenBBs;
	auto collectIoUses = [&IOcompatibility, &isSelectedFn](Instruction &I) {
		Value *io;
		if (auto ld = dyn_cast<LoadInst>(&I)) {
			io = ld->getPointerOperand();
		} else if (auto st = dyn_cast<StoreInst>(&I)) {
			io = st->getPointerOperand();
		} else {
			return;
		}

		io = findIoDef(io);
		if (IOcompatibility.contains(io)) {
			return;
		}
		bool isCompatible = allLoadStoreInstrAreCompatible(io, isSelectedFn);
		IOcompatibility.insert({io, isCompatible});
	};
	walkSelectedInstructions(LI, L, BB0, isSelectedFn, seenBBs, collectIoUses);
}

void movePrequelSection(LoopInfo &LI, Loop &L, DomTreeUpdater &DTU,
						MemorySSAUpdater *MSSAU, IRBuilderBase &Builder,
						std::unordered_set<Instruction *> &compatible,
						DenseSet<BasicBlock *> &blocksToCopy,
						DenseMap<BasicBlock *, BasicBlock *> &blockMapOldToNew,
						BasicBlock &oldBB, BasicBlock &newBB,
						BasicBlock &oldEntry, BasicBlock &newExitBB) {
	// If the extracted section does not have a single exit it is not a problem
	// because by definition of the prequel there can not be any dependency
	// preventing jump to original header (from exit of extracted section) and
	// after original header the CFG is replicated so functionality will remain
	// same if all exits from extracted section will be rerouted to second half
	// of original header
	//
	auto isJumpFromSection = [&oldEntry, &blocksToCopy](BasicBlock *suc) {
		if (suc == &oldEntry)
			return true;
		return !blocksToCopy.contains(suc);
	};
	assert(compatible.size());
	// errs() << "extracting: \n";
	// for (auto *I : compatible) {
	// 	errs() << "    " << *I << "\n";
	// }
	{
		auto curT = newBB.getTerminator();
		if (curT) {
			// original terminator created by SplitBlock in BB0_1
			auto newTmpBr = dyn_cast<BranchInst>(curT);
			assert(newTmpBr);
			assert(!newTmpBr->isConditional());
			assert(newTmpBr->getSuccessor(0) == &newExitBB);
			curT->eraseFromParent();
			DTU.applyUpdates({{DominatorTree::Delete, &newBB, &newExitBB}});
		}
	}
	auto isExitDst = [&isJumpFromSection](BasicBlock *suc) {
		return isJumpFromSection(suc) ||
			   isa<UnreachableInst>(suc->getTerminator());
	};

	for (auto &I : make_early_inc_range(oldBB)) {
		if (compatible.contains(&I)) {
			if (I.isTerminator()) {
				bool allAreExits = true;
				for (auto *suc : successors(&oldBB)) {
					if (isExitDst(suc)) {
						continue;
					}

					allAreExits = false;
				}
				SmallVector<DomTreeUpdater::UpdateT, 8> dtUpdates;
				if (allAreExits) {
					Builder.SetInsertPoint(&newBB);
					Builder.CreateBr(&newExitBB);
					dtUpdates.push_back(
						{DominatorTree::Insert, &newBB, &newExitBB});
				} else {
					auto newTerm = I.clone();
					newTerm->moveBefore(newBB, newBB.end());
					auto sucCnt = newTerm->getNumSuccessors();
					for (unsigned sucI = 0; sucI < sucCnt; ++sucI) {
						auto suc = newTerm->getSuccessor(sucI);
						BasicBlock *newSuc;
						bool endsWithUnreachable =
							dyn_cast<UnreachableInst>(suc->getTerminator());
						if (!endsWithUnreachable && isExitDst(suc)) {
							newSuc = &newExitBB;
						} else {
							auto existingNewSuc = blockMapOldToNew.find(suc);
							if (existingNewSuc != blockMapOldToNew.end()) {
								newSuc = existingNewSuc->second;
							} else {
								newSuc = BasicBlock::Create(
									suc->getContext(),
									suc->getName() + ".slprequel",
									suc->getParent(), suc);
								L.addBasicBlockToLoop(newSuc, LI);
								blockMapOldToNew[suc] = newSuc;
								if (endsWithUnreachable) {
									Builder.SetInsertPoint(newSuc);
									Builder.CreateUnreachable();
								} else {
									movePrequelSection(
										LI, L, DTU, MSSAU, Builder, compatible,
										blocksToCopy, blockMapOldToNew, *suc,
										*newSuc, oldEntry, newExitBB);
								}
							}
						}

						if (suc != newSuc) {
							newTerm->setSuccessor(sucI, newSuc);
						}
						dtUpdates.push_back(
							{DominatorTree::Insert, &newBB, newSuc});
					}
				}
				DTU.applyUpdates(dtUpdates);
			} else {
				I.moveBefore(newBB, newBB.end());
			}
		} else if (I.isTerminator()) {
			Builder.SetInsertPoint(&newBB);
			Builder.CreateBr(&newExitBB);
			DTU.applyUpdates({{DominatorTree::Insert, &newBB, &newExitBB}});
		}
	}
}
// for blocks in the loop select blocks which contains any instruction and then
// walk up (use->def) and add all blocks until topBB which is typically a header
// of the loop :param instructions: selected instructions from any block in the
// loop :param blocks: an output set collected blocks
void findSelectedBlocks(BasicBlock &topBB,
						const std::unordered_set<Instruction *> instructions,
						DenseSet<BasicBlock *> &blocks) {

	SmallVector<BasicBlock *> worklist;
	for (Instruction *I : instructions) {
		BasicBlock *BB = I->getParent();
		assert(BB && "Instruction has no parent block");
		worklist.push_back(BB);
	}

	while (!worklist.empty()) {
		// :note: use->def iteration of blocks
		BasicBlock *BB = worklist.pop_back_val();
		if (!blocks.insert(BB).second) {
			continue; // already in blocks
		}
		if (BB == &topBB)
			continue;
		for (auto pred : predecessors(BB)) {
			// once all successors of the block are known to be in section the
			// block is known to be in section as well
			if (all_of(successors(pred), [&blocks](BasicBlock *predSuc) {
					return blocks.contains(predSuc);
				})) {
				worklist.push_back(pred);
			}
		}
	}
}

void LoopMarkPassPrototype::findIncopatibleIoInstr(
	llvm::LoopInfo &LI, llvm::Loop &L,
	std::unordered_set<Instruction *> compatible,
	std::unordered_set<Instruction *> incompatible,
	DenseMap<Value *, bool> IOcompatibility) {
	auto isSelectedFn = [&compatible](Instruction &I) {
		return compatible.contains(&I);
	};
	checkIoIsPrivateToSelectedRegion(LI, L, *L.getHeader(), isSelectedFn,
									 IOcompatibility);

	for (const auto &[io, isCompatible] : IOcompatibility) {
		if (!isCompatible) {
			walkAllUserGepLoadStoreInstructions(
				io,
				[&incompatible](Instruction &I) { incompatible.insert(&I); });
		}
	}
}

bool LoopMarkStatelessPrequelAsAsyncThreadPass::processLoop(llvm::LoopInfo &LI,
											   llvm::Loop &L,
											   DomTreeUpdater &DTU,
											   MemorySSAUpdater *MSSAU) {
	{
		const MDOperand *AttrMD =
		findStringMetadataForHwtHlsLoop(&L, METADATA_NAME).value_or(nullptr);
		if (!applyOnAll && !AttrMD)
			return false;
	}
	if (L.getHeader()->phis().empty())
		return false; // there is no state, everything would be extracted

	// Save loop properties before it is transformed.
	std::optional<MDNode *> llvmLoopMdFollowup = makeFollowupLoopID(
		L.getLoopID(), {METADATA_NAME_followup});
	L.setLoopID(nullptr); // temporary delete before CFG modifications
	auto returnBackLoopIDMdBeforeExit = [&llvmLoopMdFollowup, &L] {
		if (llvmLoopMdFollowup.has_value())
			// return id back after cfg modifications
			L.setLoopID(llvmLoopMdFollowup
							.value());
	};

	std::unordered_set<Instruction *> compatible;
	std::unordered_set<Instruction *> incompatible;
	DenseMap<Value *, bool> IOcompatibility;
	// first check which IOs are touched by prequel section
	for (;;) {
		std::unordered_set<BasicBlock *> seenBlocks;
		findIndependentInstr(LI, L, *L.getHeader(),
							 L.getHeader()->getFirstNonPHIIt(), incompatible,
							 seenBlocks, compatible);
		// :note: we can not just transitively erase uses of instruction once we
		//        resolve it to be incompatible,
		//        we need to also discard all instructions from successor blocks
		//        if Use is a terminator During discarding we also need to check
		//        that we are not discarding any IO instruction, because that
		//        would mean that potentially some other instructions become
		//        incompatible as well.
		auto incompatibleSize = incompatible.size();
		findIncopatibleIoInstr(LI, L, compatible, incompatible,
							   IOcompatibility);
		if (compatible.empty()) {
			returnBackLoopIDMdBeforeExit();
			return false;
		}
		if (incompatibleSize != incompatible.size()) {
			compatible.clear();
			// some new incompatible instructions were found we have
			// to construct compatible set again
			// perform the search again excluding IOs which are not private to
			// this section
			continue;
		}
		break;
	}
	// check if it is worth extracting
	if (all_of(compatible, [](Instruction *I) {
			if (IsFreeInstruction(*I)) {
				return true;
			} else if (auto ld = dyn_cast<LoadInst>(I)) {
				return ld->getPointerOperand()->getNumUses() == 1;
			} else if (auto st = dyn_cast<StoreInst>(I)) {
				return st->getPointerOperand()->getNumUses() == 1;
			} else if (auto gep = dyn_cast<GetElementPtrInst>(I)) {
				return gep->getPointerOperand()->getNumUses() == 1;
			} else if (auto br = dyn_cast<BranchInst>(I)) {
				return !br->isConditional();
			}
			return false;
		})) {
			returnBackLoopIDMdBeforeExit();
			return false;
	}

	auto BB0 = L.getHeader();
	DenseSet<BasicBlock *> blocksToCopy;
	findSelectedBlocks(*BB0, compatible, blocksToCopy);
	DTU.flush();
	IRBuilder<> Builder(BB0->getContext());
	// Insert empty block (BB0_1) after header PHIs where we will move extracted
	// code The move may require duplication of CFG if terminators were
	// extracted as well. If terminator is in extracted section, create its copy
	// (only branch condition will be passed from prequel to original code)
	auto BB0_1 = SplitBlock(BB0, BB0->getFirstNonPHIIt(), &DTU, &LI, MSSAU);
	// :note: BB0_orig now contains instructions of interest from original BB0
	// plus incompatible instructions
	//       we recursively everything to BB0_1 which is a new entry for to be
	//       extracted region
	auto BB0_orig = SplitBlock(BB0_1, BB0_1->begin(), &DTU, &LI, MSSAU);
	DenseMap<BasicBlock *, BasicBlock *> blockMapOldToNew;
	blockMapOldToNew[BB0_orig] = BB0_1;
	blocksToCopy.insert(BB0_orig);

	// add mark section boundaries

	// :note: based on IoLowerAxiMmPass/markReadConsummerSection
	ThreadSplitSectionMetadata threadMdObj("slprequel", true, true, true, /*endMayBeAsync*/ false,
										   0, 0);
	auto md = threadMdObj.toMetadata(Builder.getContext());
	Builder.SetInsertPoint(BB0_1->begin());
	CreateThreadSplitBegin(Builder, threadMdObj.name, md);

	Builder.SetInsertPoint(BB0_orig->begin());
	CreateThreadSplitEnd(Builder, threadMdObj.name, md);

	movePrequelSection(LI, L, DTU, MSSAU, Builder, compatible, blocksToCopy,
					   blockMapOldToNew, *BB0_orig, *BB0_1, *L.getHeader(),
					   *BB0_orig);
    returnBackLoopIDMdBeforeExit();
	return true;
}

llvm::PreservedAnalyses
LoopMarkPassPrototype::run(llvm::Loop &L, llvm::LoopAnalysisManager &AM,
						   llvm::LoopStandardAnalysisResults &AR,
						   llvm::LPMUpdater &U) {
	assert(!AR.BFI && !AR.BPI && "NotImplemented");
	std::optional<MemorySSAUpdater> MSSAU;
	if (AR.MSSA)
		MSSAU = MemorySSAUpdater(AR.MSSA);

	DomTreeUpdater DTU(AR.DT, DomTreeUpdater::UpdateStrategy::Lazy);
	bool Changed = processLoop(AR.LI, L, DTU, MSSAU ? &*MSSAU : nullptr);

	for (auto &L0 : AR.LI) {
		L0->verifyLoop();
	}
	DTU.flush();
	assert(AR.DT.verify());

	// AR.LI.verify(AR.DT);
	// AR.SE.verify();
	if (!Changed)
		return PreservedAnalyses::all();

	if (AR.MSSA && VerifyMemorySSA)
		AR.MSSA->verifyMemorySSA();

	// DominatorTreeAnalysis, LoopAnalysis, LoopAnalysisManagerFunctionProxy,
	// ScalarEvolutionAnalysis
	PreservedAnalyses PA = getLoopPassPreservedAnalyses();
	if (AR.MSSA)
		PA.preserve<MemorySSAAnalysis>();
	return PA;
}

llvm::PreservedAnalyses
LoopMarkPassPrototype::run(llvm::Module &M, llvm::ModuleAnalysisManager &AM) {
	auto &FAM =
		AM.getResult<FunctionAnalysisManagerModuleProxy>(M).getManager();
	bool Changed = false;
	for (auto &F : M) {
		if (F.isDeclaration())
			continue;
		MemorySSAAnalysis::Result *MSSA = nullptr;
		auto &LI = FAM.getResult<LoopAnalysis>(F);
		auto &DT = FAM.getResult<DominatorTreeAnalysis>(F);
		for (auto *L : LI.getLoopsInPreorder()) {
			// AssumptionCache *AC = LookupAssumptionCache(F);
			//  assert(!verifyFunction(*F, &errs()));
			//  writeCFGToDotFile(*F, "tmp/ThreadExtractIoFsmPass.0.dot", FAM);
			if (!MSSA)
				MSSA = FAM.getCachedResult<MemorySSAAnalysis>(F);
			std::optional<MemorySSAUpdater> MSSAU;
			if (MSSA) {
				MSSAU = MemorySSAUpdater(&MSSA->getMSSA());
			}
			DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
			Changed |= processLoop(LI, *L, DTU, MSSAU ? &*MSSAU : nullptr);
		}
		if (MSSA && VerifyMemorySSA)
			MSSA->getMSSA().verifyMemorySSA();
	}
	if (!Changed)
		return PreservedAnalyses::all();

	// DominatorTreeAnalysis, LoopAnalysis, LoopAnalysisManagerFunctionProxy,
	// ScalarEvolutionAnalysis
	PreservedAnalyses PA = getLoopPassPreservedAnalyses();
	PA.preserve<MemorySSAAnalysis>();
	return PA;
}
}