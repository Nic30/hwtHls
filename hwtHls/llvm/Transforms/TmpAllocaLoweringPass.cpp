#include <hwtHls/llvm/Transforms/TmpAllocaLoweringPass.h>

#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>

using namespace llvm;

namespace hwtHls {

const std::string TmpAllocaLoweringPass::HwtHlsTmpAllocaName =
		"hwtHls.tmp.alloca";


const std::string TmpAllocaLoweringPass::HwtHlsTmpPropagateNoSplitName = "hwtHls.tmp.propagateNoSplit";

void propagateNoSplitOnUserPhis(Instruction &I, MDNode *NoSplitMD) {
	// if this is some form of bit manipulation propagate use->def
	if (auto CI = dyn_cast<CallInst>(&I)) {
		if (IsBitConcat(CI) || IsBitRangeGet(CI)) {
			for (Use &_Op : CI->args()) {
				auto Op = _Op.get();
				if (auto OpI = dyn_cast<Instruction>(Op)) {
					if (OpI->getMetadata(
							SlicesToIndependentVariablesPass::metadataName_NoSplit))
						continue;
					OpI->setMetadata(
							SlicesToIndependentVariablesPass::metadataName_NoSplit,
							NoSplitMD);
					propagateNoSplitOnUserPhis(*OpI, NoSplitMD);
				}
			}
		}
	} else if (auto cast = dyn_cast<CastInst>(&I)) { // ZExtInst, SExtInst, ...
		if (auto src = dyn_cast<Instruction>(cast->getOperand(0))) {
			propagateNoSplitOnUserPhis(*src, NoSplitMD);
		}
	}
	// propagate def->use
	for (User *U : I.users()) {
		if (auto UI = dyn_cast<Instruction>(U)) {
			if (UI->getMetadata(
					SlicesToIndependentVariablesPass::metadataName_NoSplit))
				continue;
			UI->setMetadata(
					SlicesToIndependentVariablesPass::metadataName_NoSplit,
					NoSplitMD);
		} else {
			continue;
		}
		if (auto Phi = dyn_cast<PHINode>(U)) {
			assert(
					Phi != &I
							&& "This should not happen because propagateNoSplitOnUserPhis is called only on instructions with NoSplit");
			propagateNoSplitOnUserPhis(*Phi, NoSplitMD);
		} else if (auto cast = dyn_cast<CastInst>(U)) { // ZExtInst, SExtInst, ...
			propagateNoSplitOnUserPhis(*cast, NoSplitMD);
		} else if (auto call = dyn_cast<CallInst>(U)) {
			if (IsBitConcat(call) || IsBitRangeGet(call)) {
				propagateNoSplitOnUserPhis(*call, NoSplitMD);
			}
		}
	}
}

MDNode* collectInstructionsForNoSplitPropagation(AllocaInst &Alloca) {
	auto _noSplit = Alloca.getMetadata(
			SlicesToIndependentVariablesPass::metadataName_NoSplit);
	if (!_noSplit)
		return nullptr;
	// copy noSplit metadata to all stored values
	for (User *U : Alloca.users()) {
		if (isa<Instruction>(U)) {
			if (isa<LoadInst>(U)) {
			} else if (auto ST = dyn_cast<StoreInst>(U)) {
				if (auto StoredValueInstr = dyn_cast<Instruction>(
						ST->getValueOperand())) {
					StoredValueInstr->setMetadata(
							SlicesToIndependentVariablesPass::metadataName_NoSplit,
							_noSplit);
					StoredValueInstr->setMetadata(TmpAllocaLoweringPass::HwtHlsTmpPropagateNoSplitName, _noSplit);
				}
			} else {
				U->dump();
				llvm_unreachable("NotImplementedError");
			}
		}
	}
	return _noSplit;
}
llvm::PreservedAnalyses TmpAllocaLoweringPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	auto &DT = AM.getResult<llvm::DominatorTreeAnalysis>(F);
	auto *AC = AM.getCachedResult<llvm::AssumptionAnalysis>(F);

	std::vector<AllocaInst*> TmpAllocas;
	std::vector<ZExtInst*> TmpZExts;
	std::vector<TruncInst*> TmpTrucncs;

	TmpAllocas.reserve(1024);
	TmpZExts.reserve(2 * 1024);
	TmpTrucncs.reserve(2 * 1024);
	IRBuilder<> Builder(F.getContext());
	SmallVector<Instruction*> toRm;
	MDNode *NoSplitMD = nullptr;
	for (auto &BB : F) {
		for (auto &I : make_early_inc_range(BB)) {
			if (auto AI = dyn_cast<AllocaInst>(&I)) {
				if (!AI->hasMetadata(HwtHlsTmpAllocaName)) {
					continue;
				}
				auto *AllocTy = AI->getAllocatedType();

				if (AllocTy->isArrayTy())
					continue; // keep as it is

				auto _noSplit = collectInstructionsForNoSplitPropagation(*AI);
				if (_noSplit && !NoSplitMD)
					NoSplitMD = _noSplit;
				if (AllocTy->isDoubleTy()) {
					TmpAllocas.push_back(AI);
					continue; // promote to reg
				}
				// reallocate if size is not %8==0 to prevent interference of allocas
				assert(AllocTy->isIntegerTy());
				size_t origAllocWidth = AllocTy->getIntegerBitWidth();
				if (origAllocWidth % 8 == 0) {
					TmpAllocas.push_back(AI);
					continue; // promote to reg
				}
				// mutate type of alloca to be aligned

				size_t allocSize = (origAllocWidth / 8) + 1;
				origAllocWidth = allocSize * 8;
				Builder.SetInsertPoint(AI);
				auto alignedAI = Builder.CreateAlloca(
						IntegerType::get(Builder.getContext(), origAllocWidth),
						AI->getAddressSpace());
				alignedAI->copyMetadata(*AI);
				AI->replaceAllUsesWith(alignedAI);
				std::string Name = AI->getName().str();
				AI->setName("");
				TmpAllocas.push_back(alignedAI);
				alignedAI->setName(Name); // transfer the name to new one

				toRm.push_back(AI);
				AI = alignedAI;
				AllocTy = AI->getAllocatedType();

				// if loads or stores to alloca are not working with alloca AllocatedType
				// they have to be rewritten before PromoteMemToReg
				for (User *U : AI->users()) {
					if (isa<Instruction>(U)) {
						if (auto LD = dyn_cast<LoadInst>(U)) {
							if (LD->getType() != AllocTy) {
								// load to trunc(load)
								assert(LD->getType()->isIntegerTy());
								size_t accessWidth =
										LD->getType()->getIntegerBitWidth();
								assert(origAllocWidth > accessWidth);

								Builder.SetInsertPoint(LD);
								auto NewLd = Builder.CreateLoad(AllocTy, AI,
										LD->isVolatile());
								NewLd->copyMetadata(*LD);
								auto replacement = Builder.CreateTrunc(NewLd,
										LD->getType(), LD->getName());
								LD->replaceAllUsesWith(replacement);

								toRm.push_back(LD);
								TmpTrucncs.push_back(
										dyn_cast<TruncInst>(replacement));
							}
						} else if (auto ST = dyn_cast<StoreInst>(U)) {
							if (ST->getAccessType() != AllocTy) {
								// store(v) to store(zext(v))
								auto src = ST->getValueOperand();
								assert(src->getType()->isIntegerTy());
								size_t accessWidth =
										src->getType()->getIntegerBitWidth();
								assert(origAllocWidth > accessWidth);

								Builder.SetInsertPoint(ST);
								auto srcZExt = Builder.CreateZExt(src, AllocTy);
								auto NewStore = Builder.CreateStore(srcZExt, AI,
										ST->isVolatile());

								NewStore->copyMetadata(*ST);
								toRm.push_back(ST);
								TmpZExts.push_back(dyn_cast<ZExtInst>(srcZExt));
							}
						} else {
							U->dump();
							llvm_unreachable("NotImplementedError");
						}
					}
				}

			}
		}
	}
	for (auto _I : toRm) {
		assert(_I->users().empty());
		_I->eraseFromParent();
	}
	if (TmpAllocas.size()) {
		llvm::PromoteMemToReg(TmpAllocas, DT, AC);
		for (auto &BB : F) {
			for (auto &I: BB) {
				if (I.hasMetadata(HwtHlsTmpPropagateNoSplitName)) {
					propagateNoSplitOnUserPhis(I, NoSplitMD);
					I.setMetadata(HwtHlsTmpPropagateNoSplitName, nullptr);
				}
			}
		}
		// Mark all the analyses that instcombine updates as preserved.
		PreservedAnalyses PA;
		PA.preserveSet<CFGAnalyses>();
		PA.preserve<AAManager>();
		PA.preserve<BasicAA>();
		PA.preserve<GlobalsAA>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}
}

}
