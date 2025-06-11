#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/IR/IRBuilder.h>

namespace llvm {
class TargetFolder;
class ICmpInst;
}

namespace hwtHls {

/**
 *  A pass to rewrite NE(!=), GT(>), GE(>=) to EQ(==), LT(<), LE(<=) with optional NOT(x XOR -1)
 */
class ICmpToOnlyEqLtLePass: public llvm::PassInfoMixin<ICmpToOnlyEqLtLePass> {
	bool rangeCmpWithoutAdd;
	llvm::Value* _tryRewriteRangeCheckTo2xCmp(
			llvm::IRBuilder<llvm::TargetFolder> &Builder, llvm::ICmpInst &CMP);
public:
	ICmpToOnlyEqLtLePass(bool rangeCmpWithoutAdd = true) :
			rangeCmpWithoutAdd(rangeCmpWithoutAdd) {
	}
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
