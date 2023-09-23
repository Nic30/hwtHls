#pragma once
#include <llvm/IR/Instruction.h>

namespace hwtHls {
enum SkipFlags {
  SkipReadMem = 1,
  SkipSideEffect = 2,
  SkipImplicitControlFlow = 4
};
unsigned skippedInstrFlags(llvm::Instruction *I);
bool isSafeToHoistInstr(llvm::Instruction *I, unsigned Flags);
}
