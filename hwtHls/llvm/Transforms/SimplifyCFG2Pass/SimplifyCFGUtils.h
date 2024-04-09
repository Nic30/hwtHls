#pragma once
#include <llvm/IR/Instruction.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {
enum SkipFlags {
	SkipReadMem = 1, SkipSideEffect = 2, SkipImplicitControlFlow = 4
};
unsigned skippedInstrFlags(llvm::Instruction *I);
bool isSafeToHoistInstr(llvm::Instruction *I, unsigned Flags);

llvm::Value* CreateGlobalDataWithGEP(llvm::IRBuilder<> &builder,
		llvm::Module &M, llvm::Value *switch_tableidx,
		const llvm::SmallVector<llvm::Constant*> &romData,
		const llvm::Twine &ROMName, const llvm::Twine &IndexName,
		const llvm::Twine &SwitchGepName);

bool IsCheapInstruction(llvm::Instruction &I);
bool tryHoistCheapInstsAtBlockBegin(llvm::BasicBlock &BB,
		llvm::Instruction *MovePos);

}
