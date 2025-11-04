#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/ThreadExtractIoFsmPass.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Module.h>
#include <llvm/Transforms/Utils/Cloning.h>
#include <llvm/Transforms/Utils/CodeExtractor.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/utils/functionMutating.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/separateInstructionsAssociatedWithIoFsm.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/formDedicatedLatchUniqueExitingBlock.h>

using namespace llvm;

namespace hwtHls {

const std::string ThreadExtractIoFsmMetadata::METADATA_NAME =
		"hwthls.thread.extractiofsm";

ThreadExtractIoFsmMetadata::ThreadExtractIoFsmMetadata(llvm::MDTuple *md) :
		md(md) {
	assert(md->getNumOperands() == 3);
	auto getUint = [md](size_t opI) {
		auto buffCapVmd = dyn_cast<ValueAsMetadata>(md->getOperand(opI).get());
		assert(buffCapVmd);
		auto buffCapC = dyn_cast<ConstantInt>(buffCapVmd->getValue());
		assert(buffCapC);
		return buffCapC->getValue().getZExtValue();
	};
	inputBufferCapacity = getUint(1);
	outputBufferCapacity = getUint(2);
}

std::optional<ThreadExtractIoFsmMetadata> ThreadExtractIoFsmMetadata::find(
		HwtHlsIoMetadata &ioMd) {
	for (auto &md : ioMd.unparsedMd) {
		if (auto mdTuple = dyn_cast<MDTuple>(md)) {
			if (mdTuple->getNumOperands() > 1
					&& mdTuple->getOperand(0).equalsStr(METADATA_NAME)) {
				return ThreadExtractIoFsmMetadata(mdTuple);
			}
		}
	}
	return {};
}

void ThreadExtractIoFsmMetadata::erase(HwtHlsIoMetadata& iomd) {
	iomd.unparsedMd.erase(std::find(iomd.unparsedMd.begin(), iomd.unparsedMd.end(), md));
	md = nullptr;
}

llvm::PreservedAnalyses ThreadExtractIoFsmPass::run(llvm::Module &M,
		llvm::ModuleAnalysisManager &AM) {
	//errs() << "Before ThreadExtractIoFsmPass:\n";
	//M.dump();
	bool Changed = false;
	auto &FAM =
			AM.getResult<FunctionAnalysisManagerModuleProxy>(M).getManager();
	auto LookupDomTree = [&FAM](Function &F) -> DominatorTree& {
		return FAM.getResult<DominatorTreeAnalysis>(F);
	};
	auto LookupLoopInfo = [&FAM](Function &F) -> LoopInfo& {
		return FAM.getResult<LoopAnalysis>(F);
	};
	//auto LookupAssumptionCache = [&FAM](Function &F) -> AssumptionCache* {
	//	return FAM.getCachedResult<AssumptionAnalysis>(F);
	//};
	SmallVector<Function*> oldFunctions;
	for (Function &F : M)
		oldFunctions.push_back(&F);
	IRBuilder<> Builder(M.getContext());
	for (Function *F : oldFunctions) {
		if (F->isDeclaration())
			continue;
		SmallVector<ArgToAddToParentFn> argsToAddToOldFn;
		auto arg = F->arg_begin();
		SmallVector<Function*> newFunctions;
		auto fnIoMds = HwtHlsIoMetadata_get(*F);
		for (HwtHlsIoMetadata& md : fnIoMds) {
			assert(arg != F->arg_end());
			auto _extractIoFsmMd = ThreadExtractIoFsmMetadata::find(md);
			if (!_extractIoFsmMd.has_value()) {
				++arg;
				continue;
			}
			ThreadExtractIoFsmMetadata& extractIoFsmMd = _extractIoFsmMd.value();
			// delete metadata because transformation is going to be performed
			// and the numbering of io arguments will change
			extractIoFsmMd.erase(md);
			HwtHlsIoMetadata_set(*F, arg->getArgNo(), md);

			auto &DT = LookupDomTree(*F);
			auto &LI = LookupLoopInfo(*F);
			//AssumptionCache *AC = LookupAssumptionCache(F);
			DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
			formDedicatedUniqueLoopExitingAndLatchBB(Builder, DTU, LI);
			DTU.flush();
			ValueToValueMapTy VMap;
			Function *extractedFn = CloneFunction(F, VMap);
			extractedFn->setName(
					F->getName() + ".ioFsmExtract." + arg->getName());
			SmallVector<ArgToAddToParentFn> argsToAddToNewFn;
			separateInstructionsAssociatedWithIoFsm(Builder, *arg, *F,
					*extractedFn, VMap, DTU, LI, argsToAddToOldFn,
					argsToAddToNewFn);
			assert(argsToAddToOldFn.size() == argsToAddToNewFn.size());
			for (const auto & [oldFnArgMd, newFnArgMd]: zip(argsToAddToOldFn, argsToAddToNewFn)) {
				assert(oldFnArgMd.metadata.direction == IODirection_reverse(newFnArgMd.metadata.direction));
				if (newFnArgMd.metadata.direction == IODirection::IO_DIR_IN) {
					oldFnArgMd.metadata.bufferCapacity =extractIoFsmMd.inputBufferCapacity;
				} else {
					assert(newFnArgMd.metadata.direction == IODirection::IO_DIR_OUT);
					newFnArgMd.metadata.bufferCapacity =extractIoFsmMd.outputBufferCapacity;
				}
			}

			// promote alloca to Function io arguments and connect them with channel
			auto &extractedFnWithNewArgs = updateArgsOfParentFunction(Builder,
					*extractedFn, argsToAddToNewFn, /*removeUnusedArgs*/
					false); // :note: can not remove unused args
			// yet because it would break argument index in argsToAddToOldFn
			newFunctions.push_back(&extractedFnWithNewArgs);
			// :note: update required because the medatada is not yet set on parent function and thus replacing function in LLVM IR has no effect on this vector
			for (auto &a : argsToAddToOldFn) {
				if (a.metadata.otherThreadFn == extractedFn) {
					a.metadata.otherThreadFn = &extractedFnWithNewArgs;
				}
			}
			Changed = true;
			// F->dump();
			// extractedFn->dump();
			++arg;
		}

		if (argsToAddToOldFn.size()) {
			// promote alloca to Function io arguments and connect them with channel
			updateArgsOfParentFunction(Builder, *F, argsToAddToOldFn);
			for (auto newF : newFunctions) {
				removeUnusedArgsOfParentFunction(*newF);
			}
			// :note: update of HwtHlsIoMetadata of connected functions is not required as it is updated when the function is replaced
			//for (auto a: argsToAddToOldFn) {
			//	if (a.metadata.otherThreadFn) {
			//		// update function pointer
			//		auto md = HwtHlsIoMetadata_get(*a.metadata.otherThreadFn, a.metadata.otherArgIndex);
			//		assert(md.has_value());
			//		md.value().otherThreadFn = &FWithNewArgs;
			//		HwtHlsIoMetadata_set(*a.metadata.otherThreadFn, a.metadata.otherArgIndex, md.value());
			//	}
			//}
		}
		if (verifyHwtHlsIoMetadata(M, false, &errs())) {
			M.dump();
			llvm_unreachable(
					"ThreadExtractIoFsmPass::run broke HwtHlsIoMetadata");
		}
	}

	//errs() << "After ThreadExtractIoFsmPass:\n";
	//M.dump();
	if (Changed) {
		PreservedAnalyses PA;
		PA.preserve<DominatorTreeAnalysis>();
		PA.preserve<LoopAnalysis>();
		return PreservedAnalyses::none();
	} else {
		return PreservedAnalyses::all();
	}

}

}
