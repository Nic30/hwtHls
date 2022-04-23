#pragma once
#include <llvm/Pass.h>
#include "genericFpgaTargetMachine.h"

namespace llvm {
llvm::FunctionPass* createGenericFpgaISelDag(GenericFpgaTargetMachine &TM,
		llvm::CodeGenOpt::Level OptLevel);
}
