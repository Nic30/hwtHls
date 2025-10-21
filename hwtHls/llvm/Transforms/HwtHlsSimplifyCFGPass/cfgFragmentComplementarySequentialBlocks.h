#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>

#include <optional>

namespace hwtHls {
/**
 * This is detect the fragment as depicted in following figure
 * .. code-block:: text
 *       bb0
 *       |  \
 *     bb.c0 |
 *       |  /
 *       bb1
 *       |  \
 *       | bb.c1
 *       |   |
 *
 *  * bb0 must dominate all blocks (and no other predecessors for bb.c0, bb1 or bb.c1 are allowed)
 *  * bb0 and bb1 condition must be the same and if bb.c0 is true successor
 *    the bb.c1 must be false successor and similarly for opposite case with bb.c1 as true successor
 *
 * */
class CfgFragmentComplementarySequentialBlocks {
public:
	bool bbC0isTrueSuccessor;
	llvm::BasicBlock *bb0;
	llvm::BasicBlock *bbC0;
	llvm::BasicBlock *bb1;
	llvm::BasicBlock *bbC1;
	CfgFragmentComplementarySequentialBlocks();
	static std::optional<CfgFragmentComplementarySequentialBlocks> detect(
			llvm::DominatorTree &DT, llvm::BasicBlock &BB0);
};

}
