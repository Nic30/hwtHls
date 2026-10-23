#pragma once

#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 * This pass detect phis which are likely to encode the state of FSM and
 * converts them and all related values from binary encoding to one-hot
 * encoding. with an independent variable for each bit.
 *
 * :note: This then allow other optimizations to analyze the behavior of program
 * 	with a greater detail. and the encoding of state variable can then be also
 * 	optimized further.
 *
 * :note: It is recommended to start FSM optimizations with
 * 	binary encoded state and only once all optimizations are finished ten apply
 * 	this. Because if complex FSM is immediately bit-blasted to one-hot
 * 	representations it often results in code explosion.
 */
class FsmStateBinToOneHotPass
	: public llvm::PassInfoMixin<FsmStateBinToOneHotPass> {

public:
	llvm::PreservedAnalyses run(llvm::Function &F,
								llvm::FunctionAnalysisManager &AM);
};

}