#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/ADT/SmallVector.h>

namespace hwtHls {

/*
 * Structure for pattern with linear sequence of blocks with a common successor which is on T branch,
 * exit can has only BB0-n predecessors:
 * .. code-block::text
 *      BB0-BB1 ...
 *        \ |  /
 *        exit
 * */
struct CfgFragmentChainOfblocksWithSameSucc {
public:
	struct BasicBlockAndBrCond {
		llvm::BasicBlock *BB;
		llvm::Value *toExitBrCond;
		bool toExitBrCondIsNegated;
		BasicBlockAndBrCond(llvm::BasicBlock *BB, llvm::Value *toExitBrCond,
				bool toExitBrCondIsNegated) :
				BB(BB), toExitBrCond(toExitBrCond), toExitBrCondIsNegated(
						toExitBrCondIsNegated) {
		}
	};

	llvm::SmallVector<BasicBlockAndBrCond> blocks;
	llvm::BasicBlock *exit;

	CfgFragmentChainOfblocksWithSameSucc();
	static std::optional<CfgFragmentChainOfblocksWithSameSucc> detect(
			llvm::BasicBlock &exitBB);
};

}
