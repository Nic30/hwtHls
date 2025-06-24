#pragma once
#include <llvm/IR/Instructions.h>

namespace hwtHls {

/*
 * Structure for pattern:
 * .. code-block::text
 *      guard
 *      /   |
 *    write |
 *      \   |
 *       exit
 * :note: guard is optional, if it is null the write is mandatory write and getWriteEnableCondition returns i1 1
 * */
struct OptionalStreamWriteCFGFragment {
public:
	llvm::BasicBlock *guard;
	llvm::CallInst *write;
	llvm::BasicBlock *exit;

	OptionalStreamWriteCFGFragment();
	OptionalStreamWriteCFGFragment(llvm::BasicBlock *guard,
			llvm::CallInst *write, llvm::BasicBlock *exit);

	static std::optional<OptionalStreamWriteCFGFragment> detect(
			llvm::BasicBlock &BlockWithWrite);
	// :returns: true if guard, exit and block with write contains only write and branches and optional llvm.assume
	bool containsOnlyStreamWrite(bool allowNonEmptyGuard = false) const;
	bool _blockContainsOnlyWriteAndAssumeAndTerminator(llvm::BasicBlock &BB) const;
	std::pair<llvm::Value*, bool> getWriteEnableCondition() const;
};

}
