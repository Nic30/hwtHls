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

template<typename InstrT>
InstrT *findInstrAtSuccessorsBegin(
	llvm::BasicBlock &BB, bool exitOnFirstUnsupportedBlock,
	llvm::SmallVector<std::pair<llvm::BasicBlock *, InstrT *>> &toHoist,
	llvm::SmallVector<llvm::BasicBlock *>* unreachableBBs) {
	InstrT *representativeI = nullptr;
	for (auto *suc : successors(&BB)) {
		if (suc->hasNPredecessorsOrMore(2)) {
			if (exitOnFirstUnsupportedBlock) {
				return nullptr;
			} else {
				continue;
			}
		}
		if (llvm::isa<llvm::UnreachableInst>(suc->getTerminator())) {
			if (unreachableBBs)
				unreachableBBs->push_back(suc);
		}
		bool blockIsSupported = true;
		for (auto &I : *suc) {
			if (llvm::isa<llvm::PHINode>(&I)) {
				// [todo] maybe support 1 entry phis
				blockIsSupported = false;
				break;
			}
			if (auto st = dyn_cast<InstrT>(&I)) {
				if (representativeI) {
					if (!st->isSameOperationAs(representativeI) ||
						st->getPointerOperand() !=
							representativeI->getPointerOperand()) {
						blockIsSupported = false;
						break;
					}
				} else {
					representativeI = st;
				}
				toHoist.push_back({suc, st});
				break;
			}
			if (!isSafeToHoistInstr(&I, SkipFlags::NONE, false)) {
				// something with side-effect or store not found
				blockIsSupported = false;
				break;
			}
			if (auto CI = llvm::dyn_cast<llvm::CallInst>(&I)) {
				if (!CI->getCalledFunction()->hasFnAttribute(
						llvm::Attribute::AttrKind::Speculatable)) {
					blockIsSupported = false;
					break;
				}
			}
		}
		if (!blockIsSupported) {
			if (exitOnFirstUnsupportedBlock) {
				return nullptr;
			} else {
				continue;
			}
		}
	}
	return representativeI;
}
}
