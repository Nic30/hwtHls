#include <hwtHls/llvm/Transforms/utils/inLoopConditionalExecution.h>
#include <unordered_set>
#include <map>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/IRBuilder.h>
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

SmallVector<AllocaInst*> makeSectionOfLoopConditionalyReexecuted(
		llvm::Loop &parentLoop, llvm::BasicBlock *prequelBlock,
		llvm::BasicBlock *bypassSuccessor,
		llvm::SetVector<llvm::BasicBlock*> sectionToExtract,
		llvm::Value *condition, llvm::DomTreeUpdater &DTU, llvm::LoopInfo &LI,
		llvm::MemorySSAUpdater *MSSAU, llvm::BlockFrequencyInfo *BFI,
		llvm::BranchProbabilityInfo *BPI, llvm::AssumptionCache *AC,
		bool conditionIsNegated) {
	// everything defined in begin section, used somewhere else in begin section potentially requires PHIs
	auto inSectionDefProps = collectInSectionDefProps(sectionToExtract,
			parentLoop);
	std::unordered_set<Instruction*> inSectionDefs(inSectionDefProps.size());
	for (auto &p : inSectionDefProps) {
		inSectionDefs.insert(p.def);
	}

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
			Builder.SetInsertPoint(preheaderTerm);
			auto Ty = p.def->getType();
			auto Name = p.def->getName();
			auto Alloca = Builder.CreateAlloca(Ty, 0, Name);
			Allocas.push_back(Alloca);
			if (!p.usedOutsideOfParentLoop)
				Builder.CreateLifetimeStart(Alloca);
			Builder.SetInsertPoint(p.def->getNextNode());
			Builder.CreateStore(p.def, Alloca);

			std::map<BasicBlock*, LoadInst*> tmpDefs;
			auto getValInBlock = [&](BasicBlock *BB) {
				LoadInst *newV;
				auto curReplacement = tmpDefs.find(BB);
				if (curReplacement == tmpDefs.end()) {
					Builder.SetInsertPoint(BB->getFirstNonPHI());
					newV = Builder.CreateLoad(Ty, Alloca, Name + ".reload");
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
	// :note: inspired by BlockExtractor::runOnModule
	//CodeExtractorAnalysisCache CEAC(*prequelBlock->getParent());
	//SetVector<Value*> inputs;
	//SetVector<Value*> outputs;
	//if (DTU.hasPendingUpdates())
	//	DTU.flush();
	//llvm::DominatorTree *DT = &DTU.getDomTree();
	//CodeExtractor CE(sectionToExtract.getArrayRef(), DT, /*AggregateArgs*/false,
	//		BFI, BPI, AC);
	//assert(CE.isEligible());
	//Function *F = CE.extractCodeRegion(CEAC, inputs, outputs);
	//assert(F);

	//auto *CB = dyn_cast<CallBase>(F->getUniqueUndroppableUser());
	//assert(CB);
	//BasicBlock *beginSection = CB->getParent();
	//BasicBlock *afterSection = SplitBlock(beginSection, CB->getNextNode(), &DTU,
	//		&LI, MSSAU);
	//auto beginSectionTerm = beginSection->getTerminator();
	auto prequelTerm = dyn_cast<BranchInst>(prequelBlock->getTerminator());
	assert(!prequelTerm->isConditional());
	auto entryBlock = prequelTerm->getSuccessor(0);
	prequelTerm->eraseFromParent();

	if (conditionIsNegated) {
		prequelTerm = BranchInst::Create(bypassSuccessor, entryBlock, condition,
				prequelBlock);
	} else {
		prequelTerm = BranchInst::Create(entryBlock, bypassSuccessor, condition,
				prequelBlock);
	}
	{
		SmallVector<DominatorTree::UpdateType, 1> Updates;
		Updates.push_back( { DominatorTree::Insert, prequelBlock,
				bypassSuccessor });
		if (MSSAU) {
			if (DTU.hasPendingUpdates())
				DTU.flush();
			MSSAU->applyUpdates(Updates, DTU.getDomTree());
		} else {
			DTU.applyUpdates(Updates);
		}
	}
	// :note: inspired by InlinerPass::run
	// Setup the data structure used to plumb customization into the
	// `InlineFunction` routine.
	//if (DTU.hasPendingUpdates())
	//	DTU.flush();
	//InlineFunctionInfo IFI(nullptr, /*PSI*/nullptr, BFI,
	///*CalleeBFI*/nullptr);
	//
	//InlineResult IR = InlineFunction(*CB, IFI, /*MergeAttributes=*/true,
	///*CalleeAAR*/nullptr);
	//assert(IR.isSuccess());
	//if (MSSAU) {
	//	llvm_unreachable("NotImplemented");
	//} else {
	//	// [todo] update from inlined function
	//	DT->recalculate(*prequelBlock->getParent());
	//}

	return Allocas;
}

}
