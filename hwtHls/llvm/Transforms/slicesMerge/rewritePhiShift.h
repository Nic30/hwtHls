#pragma once
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

/*
 * Create one wider PHINode from group of phis
 * */
llvm::PHINode* mergePhisToWiderPhi(llvm::IRBuilderBase &builder,
		const llvm::Twine &nameStem, const std::vector<llvm::PHINode*> &phis);

}
