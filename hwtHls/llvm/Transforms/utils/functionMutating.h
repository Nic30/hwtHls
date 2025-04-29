#pragma once
#include <map>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {
llvm::Function* mutateFunctionAddArg(llvm::Function &F, llvm::Type *ParamTy,
		const llvm::Twine &ParamName);

/*
 * Mutate type of pointer instructions to use new address space
 * */
void rewriteAddressSpace(llvm::IRBuilder<> &Builder,
		std::map<llvm::Value*, llvm::Value*> replacements, llvm::Value &V,
		llvm::Type *NewPtrTy, std::function<bool(llvm::User *)>* userFilter);

void replaceAlUsesOfArgumentWithPotentiallyChangedAddressSpace(
		llvm::IRBuilder<> &Builder, llvm::Argument &Arg,
		llvm::Argument &NewArg, std::function<bool(llvm::User *)>* userFilter);
llvm::Function* mutateFunctionShuffleArgs(llvm::Function &F,
		const std::vector<std::size_t> &newOrder);
}
