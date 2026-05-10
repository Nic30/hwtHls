#pragma once

#include <map>

#include <llvm/IR/Dominators.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Transforms/Utils/ValueMapper.h>

#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractorIoArgUtils.h>

namespace hwtHls {

// :note: beforeHeader, beforeExit contain instructions from old function
struct LoopExports {
	// values which will need to be exported to new function before header of this loop
	llvm::SetVector<llvm::Instruction*> beforeHeaderExports;
	llvm::AllocaInst *beforeHeaderInOld;
	llvm::AllocaInst *beforeHeaderInNew;
	llvm::SetVector<llvm::BasicBlock*> beforeHeaderSection;

	// values which will need to be exported to new function before all exits of this loop
	llvm::SetVector<llvm::Instruction*> beforeExitOrLatchExports;
	llvm::AllocaInst *beforeExitOrLatchInOld;
	llvm::AllocaInst *beforeExitOrLatchInNew;
	llvm::SetVector<llvm::BasicBlock*> beforeExitOrLatchSection;
};

void resolveExportedValues(llvm::LoopInfo& LI, llvm::Loop *L,
		/*const*/ llvm::ValueToValueMapTy &VMap,
		/*const*/ llvm::ValueToValueMapTy &VMapNewToOld,
		const llvm::SetVector<llvm::Value*> &newInstructionsInNewFn,
		std::map<llvm::Loop*, LoopExports> &loopExports); // 		std::unordered_set<llvm::Instruction*> & alreadyExported

void constructCommunicationBetweenOriginalAndExtractedLoop(
		llvm::IRBuilder<> &Builder, llvm::Function &F,
		llvm::DominatorTree & DT, // (for F)
		llvm::Function &extractedF,
		llvm::SmallVector<ArgToAddToParentFn> &argsToAddToOldFn,
		llvm::SmallVector<ArgToAddToParentFn> &argsToAddToNewFn,
		std::map<llvm::Loop*, LoopExports> &loopExports,
		llvm::SetVector<llvm::Instruction*> &alreadyExported,
		llvm::ValueToValueMapTy &VMap, llvm::ValueToValueMapTy &VMapNewToOld,
		llvm::BasicBlock::iterator allocaInsertPointInOld,
		llvm::BasicBlock::iterator allocaInsertPointInNew, llvm::Loop *L,
		llvm::SetVector<llvm::Value*> &newInstructionsInNewFn);

}
