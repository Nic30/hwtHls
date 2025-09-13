#pragma once
#include <map>
#include <set>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

llvm::Function* mutateFunctionAddArgs(llvm::Function &F,
		llvm::ArrayRef<llvm::Type*> ParamTys,
		llvm::ArrayRef<llvm::Twine> ParamNames);
llvm::Function* mutateFunctionAddArg(llvm::Function &F, llvm::Type *ParamTy,
		const llvm::Twine &ParamName);

/*
 * Mutate type of pointer instructions to use new address space
 * */
void rewriteAddressSpace(llvm::IRBuilder<> &Builder,
		std::map<llvm::Value*, llvm::Value*> replacements, llvm::Value &V,
		llvm::Type *NewPtrTy, std::function<bool(llvm::User*)> *userFilter);

void replaceAlUsesOfPointerWithPotentiallyChangedAddressSpace(
		llvm::IRBuilder<> &Builder, llvm::Value &V, llvm::Value &NewV,
		std::function<bool(llvm::User*)> *userFilter);

// :see: :func:`reorder` for meaning of the newOrder (vector of indices where the item should be put in output in current index)
// :param shouldUpdateOfOtherFnMd: a predicate function to decide if update metadata of other function connected to arg of this fn
llvm::Function* mutateFunctionShuffleArgs(llvm::Function &F,
		const std::vector<std::size_t> &newOrder,
		size_t argsToDiscardFromEndCnt=0,
		std::optional<std::function<bool(const llvm::Function&)>> shouldUpdateOfOtherFnMd = {});

}
