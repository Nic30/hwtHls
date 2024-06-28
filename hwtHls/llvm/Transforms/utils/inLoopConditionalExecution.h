#pragma once
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/ADT/SetVector.h>

namespace llvm {
class Loop;
}

namespace hwtHls {

/*
 * Conditionally enter the section specified and use PHINodes in loop header to store previously
 * computed liveouts for others to use.
 *
 * :param parentLoop: parent loop where this section is
 * :param prequelBlock: block which dominates all blocks in section and has a single successor
 *  	which is in the section
 * :param bypassSuccessor: the target block where code should jump if this section is not enabled
 * :param condition: condition enabling the execution of the section (may be inverted see conditionIsNegated)
 * :param conditionIsNegated: if true the condition meaning is inverted, if false section
 * 		is executed if condition is resolved to be true
 *
 * :return: vector of newly created alloca instructions for values define in section which have use
 *     where become not dominated by its def after guard "if" was added for section.
 * */
llvm::SmallVector<llvm::AllocaInst*> makeSectionOfLoopConditionalyReexecuted(
		llvm::Loop &parentLoop, llvm::BasicBlock *prequelBlock,
		llvm::BasicBlock *bypassSuccessor,
		llvm::SetVector<llvm::BasicBlock*> sectionToExtract,
		llvm::Value *condition, llvm::DomTreeUpdater &DTU, llvm::LoopInfo &LI,
		llvm::MemorySSAUpdater *MSSAU, llvm::BlockFrequencyInfo *BFI,
		llvm::BranchProbabilityInfo *BPI, llvm::AssumptionCache *AC,
		bool conditionIsNegated = false);

}
