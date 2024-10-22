#include <hwtHls/llvm/Transforms/utils/inLoopConditionalExecution.h>
#include <unordered_set>
#include <map>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Intrinsics.h>
//#include <llvm/Transforms/Utils/Cloning.h>
//#include <llvm/Transforms/Utils/CodeExtractor.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

using namespace llvm;

namespace hwtHls {

struct InSectionDefProps {
	Instruction *def;
	// if true value needs to have tmp alloca, and all uses needs to be replaced
	// with load from that alloca (however the use in PHI for edge from section is allowed)
	bool usedOutsideOfSection;
	bool usedOutsideOfParentLoop; // if false the lifetime_end will not be added into parent loop exit block
	InSectionDefProps(Instruction &def) :
			def(&def), usedOutsideOfSection(false), usedOutsideOfParentLoop(
					false) {
	}
};

bool PHINode_valueIsUsedOnlyForSelectedBlocks(PHINode &phi, Value *V,
		llvm::SetVector<llvm::BasicBlock*> section) {
	for (size_t i = 0; i < phi.getNumIncomingValues(); ++i) {
		auto predV = phi.getIncomingValue(i);
		if (predV == V) {
			auto pred = phi.getIncomingBlock(i);
			if (!section.contains(pred))
				return false;
		}
	}
	return true;
}

std::vector<InSectionDefProps> collectInSectionDefProps(
		llvm::SetVector<llvm::BasicBlock*> section, llvm::Loop &parentLoop) {
	std::vector<InSectionDefProps> inSectionDefs;
	inSectionDefs.reserve(32);
	for (auto *BB : section) {
		for (auto &I : *BB) {
			InSectionDefProps props(I);
			for (Use &U : I.uses()) {
				if (auto useI = dyn_cast<Instruction>(U.getUser())) {
					auto *userBB = useI->getParent();
					if (!section.contains(userBB)) {
						props.usedOutsideOfSection = true;
						if (!parentLoop.contains(userBB)
								&& !(isa<PHINode>(useI)
										&& PHINode_valueIsUsedOnlyForSelectedBlocks(
												*dyn_cast<PHINode>(useI), &I,
												section))) {
							props.usedOutsideOfParentLoop = true;
							break; // no need to search further, all flags are known now
						}
					}
				}
			}
			inSectionDefs.push_back(props);
		}
	}

	return inSectionDefs;
}
llvm::MemoryAccess* MSSAU_createNewAccess(llvm::MemorySSAUpdater *MSSAU,
		Instruction *NewI) {
	const MemoryUseOrDef *FirstNonDom = nullptr;
	const auto *AL = MSSAU->getMemorySSA()->getBlockAccesses(NewI->getParent());

	// If there are accesses in the current basic block, find the first one
	// that does not come before NewS. The new memory access is inserted
	// after the found access or before the terminator if no such access is
	// found.
	if (AL) {
		for (const auto &Acc : *AL) {
			if (auto *Current = dyn_cast<MemoryUseOrDef>(&Acc))
				if (!Current->getMemoryInst()->comesBefore(NewI)) {
					FirstNonDom = Current;
					break;
				}
		}
	}

	MemoryAccess *NewMA;
	if (FirstNonDom)
		NewMA = MSSAU->createMemoryAccessBefore(NewI, nullptr,
				const_cast<MemoryUseOrDef*>(FirstNonDom));
	else
		NewMA = MSSAU->createMemoryAccessInBB(NewI, nullptr, NewI->getParent(),
				MemorySSA::BeforeTerminator);
	return NewMA;
}

// based on llvm::GVNPass::eliminatePartiallyRedundantLoad
void MSSAU_addNewLoad(llvm::MemorySSAUpdater *MSSAU, Instruction *OrigInstr,
		LoadInst *NewLoad) {
	NewLoad->setDebugLoc(OrigInstr->getDebugLoc());
	if (MSSAU) {
		auto *NewAccess = MSSAU_createNewAccess(MSSAU, NewLoad);
		if (auto *NewDef = dyn_cast<MemoryDef>(NewAccess))
			MSSAU->insertDef(NewDef, /*RenameUses=*/true);
		else
			MSSAU->insertUse(cast<MemoryUse>(NewAccess), /*RenameUses=*/true);
	}
}

// based on llvm::GVNPass::processAssumeIntrinsic
void MSSAU_addNewStore(llvm::MemorySSAUpdater *MSSAU, Instruction *OrigInstr,
		Instruction *NewStore) {
	NewStore->setDebugLoc(OrigInstr->getDebugLoc());
	if (MSSAU) {
		auto *NewDef = MSSAU_createNewAccess(MSSAU, NewStore);
		MSSAU->insertDef(cast<MemoryDef>(NewDef), /*RenameUses=*/true);
	}
}

void makeSectionOfLoopConditionalyReexecuted_rerouteExits(
		bool conditionIsNegated, llvm::BasicBlock *prequelBlock,
		llvm::BasicBlock *bypassSuccessor, llvm::Value *condition,
		llvm::DomTreeUpdater &DTU, llvm::MemorySSAUpdater *MSSAU) {
	// :note: inspired by BlockExtractor::runOnModule
	BranchInst *prequelTerm = dyn_cast<BranchInst>(
			prequelBlock->getTerminator());
	assert(!prequelTerm->isConditional());
	auto entryBlock = prequelTerm->getSuccessor(0);
	assert(entryBlock != bypassSuccessor);
	BasicBlock *prequelTSucc = entryBlock;
	BasicBlock *prequelFSucc = bypassSuccessor;
	prequelTerm->eraseFromParent();
	if (conditionIsNegated) {
		std::swap(prequelTSucc, prequelFSucc);
	}
	prequelTerm = BranchInst::Create(prequelTSucc, prequelFSucc, condition,
			prequelBlock);
	assert(
			!MSSAU && !bypassSuccessor->getUniquePredecessor()
					&& "MSSAU not supported because it does not construct MemoryPhi in bypassSuccessor correctly if it has multiple predecessors");
	{
		SmallVector<DominatorTree::UpdateType, 1> Updates;
		Updates.push_back( { DominatorTree::Insert, prequelBlock,
				bypassSuccessor });
		// done as in llvm::splitBlockBefore
		DTU.applyUpdates(Updates);
		//DTU.flush();
		if (MSSAU) {
			auto &DT = DTU.getDomTree();
			MSSAU->applyUpdates(Updates, DT);
		}
	}
}

SmallVector<AllocaInst*> makeSectionOfLoopConditionalyReexecuted(
		llvm::Loop &parentLoop, llvm::BasicBlock *prequelBlock,
		llvm::BasicBlock *bypassSuccessor,
		llvm::SetVector<llvm::BasicBlock*> sectionToExtract,
		llvm::Value *condition, llvm::DomTreeUpdater &DTU, llvm::LoopInfo &LI,
		llvm::MemorySSAUpdater *MSSAU, llvm::BlockFrequencyInfo *BFI,
		llvm::BranchProbabilityInfo *BPI, llvm::AssumptionCache *AC,
		bool conditionIsNegated) {
	auto &F = *DTU.getDomTree().getRoot()->getParent();
	assert(bypassSuccessor->getParent() == &F && "bypassSuccessor not removed");
	for (auto BB : sectionToExtract) {
		assert(BB->getParent() == &F && "sectionToExtract item not removed");
	}

	// everything defined in begin section, used somewhere else in begin section potentially requires PHIs
	auto inSectionDefProps = collectInSectionDefProps(sectionToExtract,
			parentLoop);
	//std::unordered_set<Instruction*> inSectionDefs(inSectionDefProps.size());
	//for (auto &p : inSectionDefProps) {
	//	inSectionDefs.insert(p.def);
	//}

	BasicBlock *preheader = parentLoop.getLoopPreheader();
	auto *preheaderTerm = preheader->getTerminator();
	IRBuilder<> Builder(preheaderTerm);
	SmallVector<AllocaInst*> Allocas;
	SmallVector<BasicBlock*> ExitBlocks;
	parentLoop.getUniqueExitBlocks(ExitBlocks);
	SmallVector<Instruction*> ExitBlockAfterPhi;
	for (auto BB : ExitBlocks) {
		ExitBlockAfterPhi.push_back(BB->getFirstNonPHI());
	}

	for (auto &p : inSectionDefProps) {
		if (p.usedOutsideOfSection) {
			// create tmp alloca in preheaderTerm
			Builder.SetInsertPoint(preheaderTerm);
			auto Ty = p.def->getType();
			auto Name = p.def->getName();
			auto Alloca = Builder.CreateAlloca(Ty, 0, Name);
			Allocas.push_back(Alloca);
			if (!p.usedOutsideOfParentLoop) {
				auto ls = Builder.CreateLifetimeStart(Alloca);
				MSSAU_addNewStore(MSSAU, p.def, ls);
			}
			assert(p.def->getNextNode() != nullptr);
			// create store to tmp alloca on original place where instuction is
			Builder.SetInsertPoint(p.def->getNextNode());
			auto newStore = Builder.CreateStore(p.def, Alloca);
			MSSAU_addNewStore(MSSAU, p.def, newStore);

			std::map<BasicBlock*, LoadInst*> tmpDefs;
			auto getValInBlock = [&](BasicBlock *BB) {
				LoadInst *newV;
				auto curReplacement = tmpDefs.find(BB);
				if (curReplacement == tmpDefs.end()) {
					Builder.SetInsertPoint(BB->getFirstNonPHI());
					newV = Builder.CreateLoad(Ty, Alloca, Name + ".reload");
					//MSSAUpdates.push_back({p.def, newV});
					MSSAU_addNewLoad(MSSAU, p.def, newV);
					tmpDefs[BB] = newV;
				} else {
					newV = curReplacement->second;
				}
				return newV;
			};
			for (auto U : make_early_inc_range(p.def->users())) {
				if (auto UInst = dyn_cast<Instruction>(U)) {
					auto BB = UInst->getParent();
					if (sectionToExtract.contains(BB))
						continue; // dominance is not changed so we do not need to update PHIs

					if (auto UPhi = dyn_cast<PHINode>(U)) {
						if (p.def == UPhi)
							continue; // do not need to update self references in child loops
						// for each predecessor, replace p.def with load constructed in predecessor
						for (size_t i = 0; i < UPhi->getNumIncomingValues();
								++i) {
							auto v = UPhi->getIncomingValue(i);
							if (v == p.def) {
								auto pred = UPhi->getIncomingBlock(i);
								if (sectionToExtract.contains(pred))
									continue; // defined in section and used only in PHI on the boundary, rewrite not required

								UPhi->setIncomingValue(i, getValInBlock(pred));
							}
						}
					} else {
						UInst->replaceUsesOfWith(p.def, getValInBlock(BB));
					}
				}
			}

			if (!p.usedOutsideOfParentLoop) {
				for (auto EbbAfterPhi : ExitBlockAfterPhi) {
					Builder.SetInsertPoint(EbbAfterPhi);
					Builder.CreateLifetimeEnd(Alloca);
				}
			}
		}
	}

	// must be called after creating allocas, because otherwise MSSA is not updated correctly
	// because the the dominance would be different and MemoryPhis would not get constructed correctly
	makeSectionOfLoopConditionalyReexecuted_rerouteExits(conditionIsNegated,
			prequelBlock, bypassSuccessor, condition, DTU, MSSAU);

	return Allocas;
}

}
