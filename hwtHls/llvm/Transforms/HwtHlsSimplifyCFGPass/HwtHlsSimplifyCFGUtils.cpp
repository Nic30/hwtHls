#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

#include <llvm/IR/PatternMatch.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/IR/Module.h>

#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

unsigned skippedInstrFlags(Instruction *I) {
	unsigned Flags = 0;
	if (I->mayReadFromMemory())
		Flags |= SkipReadMem;
	// We can't arbitrarily move around allocas, e.g. moving allocas (especially
	// in alloca) across stacksave/stackrestore boundaries.
	if (I->mayHaveSideEffects() || isa<AllocaInst>(I))
		Flags |= SkipSideEffect;
	if (!isGuaranteedToTransferExecutionToSuccessor(I))
		Flags |= SkipImplicitControlFlow;
	return Flags;
}

// based on isSafeToHoistInstr from llvm-21.1.2 SimplifyCFG.cpp
// Returns true if it is safe to reorder an instruction across preceding
// instructions in a basic block.
bool isSafeToHoistInstr(Instruction *I, unsigned Flags, bool checkOperands) {
	// Don't reorder a store over a load.
	if ((Flags & SkipReadMem) && I->mayWriteToMemory())
		if (!hasMetadataSideeffectAllowHoist(*I))
			return false;

	// If we have seen an instruction with side effects, it's unsafe to reorder
	// an instruction which reads memory or itself has side effects.
	if ((Flags & SkipSideEffect) &&
		(I->mayReadFromMemory() || I->mayHaveSideEffects() ||
		 isa<AllocaInst>(I))) {
		if (!hasMetadataSideeffectAllowHoist(*I))
			return false;
	}
	if ((Flags & SkipSideEffect) && I->isIntDivRem())
		if (!hasMetadataSideeffectAllowHoist(*I))
			return false;

	// Reordering across an instruction which does not necessarily transfer
	// control to the next instruction is speculation.
	if ((Flags & SkipImplicitControlFlow) && !isSafeToSpeculativelyExecute(I))
		if (!hasMetadataSideeffectAllowHoist(*I))
			return false;

	// Hoisting of llvm.deoptimize is only legal together with the next return
	// instruction, which this pass is not always able to do.
	if (auto *CB = dyn_cast<CallBase>(I))
		if (CB->getIntrinsicID() == Intrinsic::experimental_deoptimize)
			return false;

	if (checkOperands) {
		// It's also unsafe/illegal to hoist an instruction above its
		// instruction operands
		BasicBlock *BB = I->getParent();
		for (Value *Op : I->operands()) {
			if (auto *J = dyn_cast<Instruction>(Op))
				if (J->getParent() == BB)
					return false;
		}
	}
	return true;
}

Value *CreateGlobalDataWithGEP(IRBuilder<> &builder, Module &M,
							   Value *switch_tableidx,
							   ArrayRef<Constant *> romData,
							   const Twine &ROMName, const Twine &IndexName,
							   const Twine &GepName) {
	auto *ArrayTy = ArrayType::get(romData[0]->getType(), romData.size());
	auto *newCRom = ConstantArray::get(ArrayTy, romData);
	auto *newArray = new GlobalVariable(M, ArrayTy, /*isConstant=*/
										true, GlobalVariable::PrivateLinkage,
										newCRom, ROMName);
	newArray->setUnnamedAddr(GlobalValue::UnnamedAddr::Global);
	// Set the alignment to that of an array items. We will be only loading one
	// value out of it.
	newArray->setAlignment(Align(1));
	// zext to assert the value is non negative
	auto *indexZext = builder.CreateZExt(
		switch_tableidx,
		Type::getIntNTy(M.getContext(),
						switch_tableidx->getType()->getIntegerBitWidth() + 1),
		IndexName);

	Value *GEPIndices[] = {builder.getInt32(0), indexZext};
	Value *newGep = builder.CreateInBoundsGEP(newArray->getValueType(),
											  newArray, GEPIndices, GepName);
	return newGep;
}

bool IsFreeInstruction(Instruction &I) {
	Value * tmp;
	if (auto *CI = dyn_cast<CallInst>(&I)) {
		if (isa<AssumeInst>(&I)) {
			assert(hasMetadataSideeffectAllowHoist(
				I)); // because otherwise the fist branch should have been taken
			return true;
		}
		return IsBitConcat(CI) || IsBitRangeGet(CI);
	} else if (isa<SExtInst>(&I) || isa<ZExtInst>(&I) || isa<BitCastInst>(&I) ||
			   isa<AddrSpaceCastInst>(&I)) {
		return true;
	} else if (PatternMatch::match(&I, PatternMatch::m_Not(PatternMatch::m_Value(tmp)))) {
		return true;
	}
	return false;
}

bool IsCheapInstruction(Instruction &I) {
	if (I.mayHaveSideEffects() && !hasMetadataSideeffectAllowHoist(I)) {
		return false;
	} else if (auto *CI = dyn_cast<CallInst>(&I)) {
		if (isa<AssumeInst>(&I)) {
			assert(hasMetadataSideeffectAllowHoist(
				I)); // because otherwise the fist branch should have been taken
			return true;
		}
		return IsBitConcat(CI) || IsBitRangeGet(CI);
	} else if (isa<BinaryOperator>(&I)) {
		if (I.isIntDivRem() || I.isFPDivRem())
			return false;
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

bool tryHoistCheapInstsAtBlockBegin(
	BasicBlock &BB, BasicBlock::iterator MoveBeforePos,
	std::optional<std::function<bool(llvm::Instruction &)>> extraCheck) {
	bool Changed = false;
	for (Instruction &I : make_early_inc_range(BB)) {
		if (I.isTerminator())
			break;
		if (!IsCheapInstruction(I)) {
			return Changed;
		}
		if (extraCheck.has_value() && !extraCheck.value()(I))
			return Changed;
		I.moveBefore(MoveBeforePos);
		Changed = true;
	}
	return Changed;
}

bool simplifyBranchToSameDst(BasicBlock *BB) {
	auto ter = BB->getTerminator();
	auto br = dyn_cast<BranchInst>(ter);
	if (ter->getNumSuccessors() > 0) {
		BasicBlock *suc = BB->getTerminator()->getSuccessor(0);
		if ((!br || br->isConditional()) && all_equal(successors(BB))) {
			ter->eraseFromParent();
			BranchInst::Create(suc, BB);
			return true;
		}
	}
	return false;
}

void sortPhiOperands(BasicBlock &BB, bool removeRedundantOperands) {
	for (auto &phi : BB.phis()) {
		// :note: phi may have block as IncomingBlock multiple times
		// this may happen because of SwitchInst e.g.
		//  switch i8 %c, label %bb.dafault [
		//    i8 0, label %bb.0
		//    i8 1, label %bb.0
		//  ]

		// collect current values
		SmallVector<Value *> values;
		size_t predCnt = pred_size(&BB);
		values.reserve(predCnt);

		if (removeRedundantOperands) {
			assert(phi.getNumIncomingValues() >= predCnt);
		} else {
			assert(phi.getNumIncomingValues() == predCnt);
		}
		SmallVector<BasicBlock*> _predecessors(predecessors(&BB));
		for (auto pred : _predecessors) {
			auto curPredI = phi.getBasicBlockIndex(pred);
			if (curPredI < 0) {
				llvm_unreachable("PHINode should have one entry for each "
								 "predecessor of its parent basic block!");
			} else {
				auto curV = phi.getIncomingValue(curPredI);
				values.push_back(curV);
			}
		}
		// set original values with order
		size_t phiBlockI = 0;
		for (const auto &[pred, v] : zip(_predecessors, values)) {
			phi.setIncomingBlock(phiBlockI, pred);
			phi.setIncomingValue(phiBlockI, v);
			phiBlockI++;
		}
		if (removeRedundantOperands) {
			assert(phiBlockI >= predCnt);
			size_t toRmCnt = phi.getNumIncomingValues() - predCnt;
			for (size_t i = 0; i < toRmCnt; i++)
				phi.removeIncomingValue(predCnt);
		} else {
			assert(phiBlockI == predCnt);
		}
	}
}

}
