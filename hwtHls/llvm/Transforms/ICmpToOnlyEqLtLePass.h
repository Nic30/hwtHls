#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  A pass to rewrite NE(!=), GT(>), GE(>=) to EQ(==), LT(<), LE(<=) with optional NOT(x XOR -1)
 */
class IcmpToOnlyEqLtLePass: public llvm::PassInfoMixin<IcmpToOnlyEqLtLePass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
