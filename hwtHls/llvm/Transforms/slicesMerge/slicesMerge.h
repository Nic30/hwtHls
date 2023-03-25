#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>

namespace hwtHls {
/**
 * If consequent slices of a bit vector are used by same types of instructions, merge slices together to reduce duplicated instructions.
 * */
class SlicesMergePass: public llvm::PassInfoMixin<SlicesMergePass> {

public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
