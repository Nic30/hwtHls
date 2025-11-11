#pragma once
#include <llvm/IR/Instruction.h>
#include <llvm/IR/IRBuilder.h>
#include <optional>

namespace hwtHls {

enum SkipFlags {
	SkipReadMem = 1, SkipSideEffect = 2, SkipImplicitControlFlow = 4,
	NONE = SkipReadMem | SkipSideEffect | SkipImplicitControlFlow,
};

unsigned skippedInstrFlags(llvm::Instruction *I);
bool isSafeToHoistInstr(llvm::Instruction *I, unsigned Flags, bool checkOperands=true);

llvm::Value* CreateGlobalDataWithGEP(llvm::IRBuilder<> &builder,
		llvm::Module &M, llvm::Value *switch_tableidx,
		llvm::ArrayRef<llvm::Constant*> romData, const llvm::Twine &ROMName,
		const llvm::Twine &IndexName, const llvm::Twine &SwitchGepName);

bool IsCheapInstruction(llvm::Instruction &I);
bool tryHoistCheapInstsAtBlockBegin(llvm::BasicBlock &BB,
		llvm::BasicBlock::iterator MoveBeforePos,
		std::optional<std::function<bool(llvm::Instruction&)>> extraCheck = { });
bool simplifyBranchToSameDst(llvm::BasicBlock *BB);
void sortPhiOperands(llvm::BasicBlock &BB, bool removeRedundantOperands=false);
}
