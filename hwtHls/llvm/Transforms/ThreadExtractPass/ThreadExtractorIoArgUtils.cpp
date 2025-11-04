#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractorIoArgUtils.h>
#include <hwtHls/llvm/Transforms/utils/functionMutating.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Module.h>

using namespace llvm;

namespace hwtHls {

Function& updateArgsOfParentFunction(IRBuilder<> &Builder, Function &F,
		const SmallVector<ArgToAddToParentFn> &argsToAddToParentFn,
		bool removeUnusedArgs,
		std::optional<std::function<bool(const llvm::Function&)>> shouldUpdateOfOtherFnMd) {
	auto &M = *F.getParent();
	Function *newFn = &F;
	if (argsToAddToParentFn.size()) {
		llvm::SmallVector<llvm::Type*> ParamTys;
		llvm::SmallVector<llvm::Twine> ParamNames;
		auto ioMds = HwtHlsIoMetadata_get(F);
		size_t argI = F.arg_size() + 1;
		for (auto a : argsToAddToParentFn) {
			ParamTys.push_back(PointerType::get(M.getContext(), argI));
			assert(a.parentFnTmp);
			ParamNames.push_back(a.parentFnTmp->getName());
			//assert(
			//		a.metadata.otherThreadFn
			//				&& "newly added parameter is expected to be channel to extracted function");
			ioMds.push_back(a.metadata);
			argI++;
		}
		F.setMetadata(HwtHlsIoMetadata::METADATA_NAME, nullptr);
		size_t originalArgSize = F.arg_size();
		newFn = mutateFunctionAddArgs(F, ParamTys, ParamNames);
		HwtHlsIoMetadata_set(*newFn, ioMds);
		auto newArgIt = newFn->arg_begin() + originalArgSize;
		for (auto &a : argsToAddToParentFn) {
			assert(newArgIt != newFn->arg_end());
			assert(a.parentFnTmp);
			for (auto *u : a.parentFnTmp->users()) {
				if (auto ui = dyn_cast<Instruction>(u)) {
					assert(
							ui->getParent()->getParent() == newFn
									&& "AllocaInst generated as tmp variable for new IO should now have uses only in this function");
				}
			}
			replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace(Builder,
					*a.parentFnTmp, *newArgIt, nullptr);
			newArgIt++;
			assert(a.parentFnTmp->hasNUses(0));
			a.parentFnTmp->eraseFromParent();
		}
	}
	if (removeUnusedArgs) {
		newFn = &removeUnusedArgsOfParentFunction(*newFn, shouldUpdateOfOtherFnMd);
	}
	return *newFn;
}

llvm::Function& removeUnusedArgsOfParentFunction(Function &F,
		std::optional<std::function<bool(const llvm::Function&)>> shouldUpdateOfOtherFnMd) {
	auto &M = *F.getParent();
	auto *newFn = &F;
	// drop unused args
	llvm::SetVector<size_t> argsToRm;
	for (Argument &A : newFn->args()) {
		if (!A.hasNUndroppableUsesOrMore(1)) {
			argsToRm.insert(A.getArgNo());
		}
	}
	if (argsToRm.size()) {
		std::vector<std::size_t> newArgOrder;
		size_t removedSoFar = 0;
		for (size_t srcI = 0; srcI < newFn->arg_size(); srcI++) {
			if (argsToRm.contains(srcI)) {
				continue;
			}
			size_t dstI = srcI - removedSoFar;
			newArgOrder.push_back(dstI);
		}
		newArgOrder.insert(newArgOrder.end(), argsToRm.begin(), argsToRm.end());
		newFn = mutateFunctionShuffleArgs(*newFn, newArgOrder, argsToRm.size(),
				shouldUpdateOfOtherFnMd);
		assert(newFn->getParent() == &M);
	}
	return *newFn;
}

}
