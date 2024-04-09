#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFGUtils.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/IRBuilder.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;
namespace hwtHls {

unsigned skippedInstrFlags(Instruction *I) {
	unsigned Flags = 0;
	if (I->mayReadFromMemory())
		Flags |= SkipReadMem;
	// We can't arbitrarily move around allocas, e.g. moving allocas (especially
	// inalloca) across stacksave/stackrestore boundaries.
	if (I->mayHaveSideEffects() || isa<AllocaInst>(I))
		Flags |= SkipSideEffect;
	if (!isGuaranteedToTransferExecutionToSuccessor(I))
		Flags |= SkipImplicitControlFlow;
	return Flags;
}

// Returns true if it is safe to reorder an instruction across preceding
// instructions in a basic block.
bool isSafeToHoistInstr(Instruction *I, unsigned Flags) {
	// Don't reorder a store over a load.
	if ((Flags & SkipReadMem) && I->mayWriteToMemory())
		return false;

	// If we have seen an instruction with side effects, it's unsafe to reorder an
	// instruction which reads memory or itself has side effects.
	if ((Flags & SkipSideEffect)
			&& (I->mayReadFromMemory() || I->mayHaveSideEffects()))
		return false;

	// Reordering across an instruction which does not necessarily transfer
	// control to the next instruction is speculation.
	if ((Flags & SkipImplicitControlFlow) && !isSafeToSpeculativelyExecute(I))
		return false;

	// Hoisting of llvm.deoptimize is only legal together with the next return
	// instruction, which this pass is not always able to do.
	if (auto *CB = dyn_cast<CallBase>(I))
		if (CB->getIntrinsicID() == Intrinsic::experimental_deoptimize)
			return false;

	// It's also unsafe/illegal to hoist an instruction above its instruction
	// operands
	BasicBlock *BB = I->getParent();
	for (Value *Op : I->operands()) {
		if (auto *J = dyn_cast<Instruction>(Op))
			if (J->getParent() == BB)
				return false;
	}

	return true;
}

Value* CreateGlobalDataWithGEP(IRBuilder<> &builder, Module &M,
		Value *switch_tableidx, const SmallVector<Constant*> &romData,
		const Twine &ROMName, const Twine &IndexName, const Twine &GepName) {
	auto *ArrayTy = ArrayType::get(romData[0]->getType(), romData.size());
	auto *newCRom = ConstantArray::get(ArrayTy, romData);
	auto *newArray = new GlobalVariable(M, ArrayTy, /*isConstant=*/
	true, GlobalVariable::PrivateLinkage, newCRom, ROMName);
	newArray->setUnnamedAddr(GlobalValue::UnnamedAddr::Global);
	// Set the alignment to that of an array items. We will be only loading one
	// value out of it.
	newArray->setAlignment(Align(1));
	// zext to assert the value is non negative
	auto *indexZext = builder.CreateZExt(switch_tableidx,
			Type::getIntNTy(M.getContext(),
					switch_tableidx->getType()->getIntegerBitWidth() + 1),
			IndexName);

	Value *GEPIndices[] = { builder.getInt32(0), indexZext };
	Value *newGep = builder.CreateInBoundsGEP(newArray->getValueType(),
			newArray, GEPIndices, GepName);
	return newGep;
}


bool IsCheapInstruction(Instruction &I) {
	if (auto *CI = dyn_cast<CallInst>(&I)) {
		return IsBitConcat(CI) || IsBitRangeGet(CI);
	} else if (isa<BinaryOperator>(&I)) {
		return true;
	} else if (isa<CmpInst>(&I)) {
		return true;
	} else if (isa<CastInst>(&I)) {
		return true;
	} else if (isa<SelectInst>(&I)) {
		return true;
	} else {
		return false;
	}
}

bool tryHoistCheapInstsAtBlockBegin(BasicBlock &BB, Instruction *MovePos) {
	bool Changed = false;
	for (Instruction &I : make_early_inc_range(BB)) {
		if (I.isTerminator())
			break;
		if (!IsCheapInstruction(I)) {
			return Changed;
		}
		I.moveBefore(MovePos);
		Changed = true;
	}
	return Changed;
}


}
