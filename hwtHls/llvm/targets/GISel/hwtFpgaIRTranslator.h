#pragma once
#include <llvm/CodeGen/GlobalISel/IRTranslator.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>

namespace hwtHls {

/*
 * * SwitchInst lowering optimizations like binary search tree are disabled
 *   because hardware can perform jump resolution in parallel (so it is useless)
 *   And it confuses if conversion because various things may move in decision tree
 *   and the order of if conversion is sub-optimal which results in some block
 *   to be not able to ifconvert.
 * */
class HwtFpgaIRTranslator: public llvm::IRTranslator {
public:
	using llvm::IRTranslator::IRTranslator;

	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
};

}
