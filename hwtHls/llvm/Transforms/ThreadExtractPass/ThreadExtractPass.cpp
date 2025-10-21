#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractPass.h>

#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallSet.h>

#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>

#include <llvm/Transforms/Utils/CodeExtractor.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>
#include <hwtHls/llvm/Transforms/utils/functionMutating.h>
#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>
#include <hwtHls/llvm/intrinsic/metadataThreadHwtComponent.h>

using namespace llvm;

namespace hwtHls {

/*
 * Common problems:
 *
 * * Extraction of non-const loop phi initialization value
 *   * if new sub-loop is created a variable suddenly becomes alive
 *     trough all iterations of parent loop
 *     because it is not known that it is just for initialization
 *     when the other thread is using it and it is referenced as a call
 *
 * */
// :attention: removes entry ThreadSplit intrinsics
llvm::PreservedAnalyses ThreadExtractPass::run(llvm::Module &M,
		llvm::ModuleAnalysisManager &AM) {
	bool Changed = false;
	auto &FAM =
			AM.getResult<FunctionAnalysisManagerModuleProxy>(M).getManager();
	auto LookupDomTree = [&FAM](Function &F) -> DominatorTree& {
		return FAM.getResult<DominatorTreeAnalysis>(F);
	};
	auto LookupLoopInfo = [&FAM](Function &F) -> LoopInfo& {
		return FAM.getResult<LoopAnalysis>(F);
	};
	auto LookupAssumptionCache = [&FAM](Function &F) -> AssumptionCache* {
		return FAM.getCachedResult<AssumptionAnalysis>(F);
	};
	SmallVector<ArgToAddToParentFn> argsToAddToParentFn;
	IRBuilder<> Builder(M.getContext());
	SmallVector<Function*> oldFunctions;
	for (Function &F : M)
		oldFunctions.push_back(&F);

	for (Function *_F : oldFunctions) {
		auto &F = *_F;
		if (F.isDeclaration() || F.hasMetadata(MetadataThreadHwtComponent::METADATA_NAME))
			continue;
		AssumptionCache *AC = LookupAssumptionCache(F);
		for (;;) {
			// the extraction breaks block iterators
			// thus we have to search always from the beginning to reliably find all ThreadSplitBegin instructions
			bool _Changed = false;
			for (BasicBlock &BB : F) {
				// :attention: the block may be split and current instruction removed
				//  the BB iterator would be broken without make_early_inc_range
				for (auto &I : BB) {
					if (auto *CI = dyn_cast<CallInst>(&I)) {
						if (IsThreadSplitBegin(CI)) {
							auto &DT = LookupDomTree(F);
							DomTreeUpdater DTU(DT,
									DomTreeUpdater::UpdateStrategy::Lazy);
							LoopInfo &LI = LookupLoopInfo(F);
							SmallVector<BasicBlock*> Blocks;
							auto sectionCfg = ThreadSplitGetSeparatedSection(
									DTU, LI, *CI, Blocks);
							bool extractedIsInLoop = true;
							extractSectionAsHwHlsThread(F, LI, DTU, AC,
									sectionCfg, Blocks, extractedIsInLoop,
									argsToAddToParentFn);
							_Changed = true;
							break; // current block was split
						}
					}
				}
				if (_Changed) {
					Changed = true;
					break;
				}
			}
			if (!_Changed)
				break;
		}
		updateArgsOfParentFunction(Builder, F, argsToAddToParentFn);
	}

	if (Changed) {
		return PreservedAnalyses::none();
	} else {
		return PreservedAnalyses::all();
	}
}

// based on LoopExtractor::extractLoop
bool ThreadExtractPass::extractSectionAsHwHlsThread(Function &Func,
		LoopInfo &LI, DomTreeUpdater &DTU, AssumptionCache *AC,
		const ThreadSplitSectionMetadata &cfg,
		const SmallVector<BasicBlock*> &Blocks, bool extractedIsInLoop,
		SmallVector<ArgToAddToParentFn> &argsToAddToParentFn) {
	// create a subloop for section after threadSplitInst
	// phi may be transfered to subloop if used only in new subloop
	// additional channel for phi init may be added
	hwtHls::CodeExtractorAnalysisCache CEAC(Func);

	HwtHlsCodeExtractor Extractor(Blocks,         //
			&DTU.getDomTree(),                    //
			/*beginMayBeAsync*/cfg.beginMayBeAsync,   //
			/*AggregateInputs*/cfg.aggregateInputs,   //
			/*endMayBeAsync*/cfg.endMayBeAsync,       //
			/*AggregateOutputs*/cfg.aggregateOutputs, //
			/*inputBufferCapacity*/cfg.inputBufferCapacity, //
			/*outputBufferCapacity*/cfg.outputBufferCapacity, //
			/*BlockFrequencyInfo*/nullptr,        //
			/*BranchProbabilityInfo*/nullptr,     //
			AC,                                   //
			/*AllocationBlock*/nullptr,           //
			/*Suffix*/cfg.name               //
			);
	HwtHlsCodeExtractor::ValueSet Inputs;
	HwtHlsCodeExtractor::ValueSet Outputs;
	Function *extractedFn = Extractor.extractCodeRegion(CEAC, extractedIsInLoop,
			Inputs, Outputs, argsToAddToParentFn);
	if (extractedFn) {
		//errs() << "after:\n";
		//Func.getParent()->dump();codeReplacerBB->getNodeParent()
		//LI.erase(L);
		return true;
	}
	return false;
}

}
