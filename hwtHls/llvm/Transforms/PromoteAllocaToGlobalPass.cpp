#include <hwtHls/llvm/Transforms/PromoteAllocaToGlobalPass.h>

#include <set>

#include <llvm/IR/Instructions.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/DataLayout.h>

using namespace llvm;

namespace hwtHls {

bool discoverStoresToAddr(Instruction &AllocaI, bool &anyStoreSeen, TypeSize allocSize, Instruction &I,
		SmallVector<Instruction*> &defs, SmallVector<Instruction*>& partialDefs, std::set<Instruction*> &seen) {
	for (auto *U : I.users()) {
		if (auto UI = dyn_cast<Instruction>(U)) {
			if (seen.contains(UI))
				continue;
			seen.insert(UI);
		}

		if (isa<LoadInst>(U)) {
		} else if (auto *ST = dyn_cast<StoreInst>(U)) {
			auto StTy = ST->getAccessType();
			if (StTy->isAggregateType() || //
				StTy->isVectorTy() || //
				StTy->getScalarSizeInBits() == allocSize.getFixedValue() * 8) {
				// if whole alloca value is initialized
				defs.push_back(ST);
			} else {
				partialDefs.push_back(ST);
			}
			anyStoreSeen = true;
		} else if (auto *II = dyn_cast<IntrinsicInst>(U)) {
			switch (II->getIntrinsicID()) {
			// case Intrinsic::memmove:
			// case Intrinsic::memset:
			case Intrinsic::memcpy: {
				auto dst = II->getArgOperand(0);
				auto size = II->getArgOperand(2);
				if (dst == &AllocaI) {
					if (dyn_cast<ConstantInt>(size)
									&& dyn_cast<ConstantInt>(size)->getZExtValue()
											== allocSize.getFixedValue()) {
						defs.push_back(II);
					} else {
						partialDefs.push_back(II);
					}
				}
				anyStoreSeen = true;
				break;
			}
			default:
				errs() << I << "    " << *U << "\n";
				llvm_unreachable("NotImplemented");
			}
		} else if (auto *GEP = dyn_cast<GetElementPtrInst>(U)) {
			if (discoverStoresToAddr(AllocaI, anyStoreSeen, allocSize, *GEP,
					defs, partialDefs, seen))
				break;
		} else if (isa<ICmpInst>(U)) {
			//} else if (isa<BinaryOperator>(U) || isa<CastInst>(U)) {
		} else {
			errs() << I << "    " << *U << "\n";
			llvm_unreachable("NotImplemented");
		}
	}
	return false;
}

void rewriteAllocaInitToGlobalValue(BasicBlock::iterator &Iit, AllocaInst &AI,
		TypeSize allocSize, Instruction *def, bool isConstant) {
	GlobalValue *SrcAsGlobalVal = nullptr;
	if (auto *ST = dyn_cast<StoreInst>(def)) {
		// based on CreateGlobalDataWithGEP
		auto AllocTy = dyn_cast<ArrayType>(AI.getAllocatedType());
		assert(AllocTy);
		auto elmTy = AllocTy->getArrayElementType();
		assert(
				(elmTy->isIntegerTy() || elmTy->isDoubleTy())
						&& "Only scalar types used in hwtHls");
		auto elmWidth = elmTy->getScalarSizeInBits();
		auto V = ST->getValueOperand();
		auto VTy = V->getType();
		Constant *newInitializer = nullptr;
		Module &M = *AI.getParent()->getParent()->getParent();
		if (VTy->isIntegerTy()) {
			// initialization from integer, typically used for small arrays
			assert(VTy->getScalarSizeInBits() == allocSize * 8);
			auto VasC = dyn_cast<ConstantInt>(V);
			assert(VasC);

			APInt VasAPInt = VasC->getValue();
			std::vector<Constant*> initData;
			initData.reserve(AllocTy->getNumElements());
			auto &C = AI.getContext();
			for (size_t i = 0; i < AllocTy->getNumElements(); ++i) {
				auto item = VasAPInt.extractBits(elmWidth, i * elmWidth);
				initData.push_back(ConstantInt::get(C, item));
			}
			newInitializer = ConstantDataArray::get(AI.getContext(), initData);
		} else {
			assert(AllocTy == VTy);
			// initialization from array constant, typically instruction like:
			// store [16 x i16] undef, ptr %ram_memory, align 2
			if (auto VC = dyn_cast<Constant>(V)) {
				newInitializer = VC;
			} else {
				llvm_unreachable(
						"rewriteAllocaInitToGlobalValue: initialization of alloca memory from non constant data");
			}
		}

		SrcAsGlobalVal = new GlobalVariable(M, AllocTy, /*isConstant=*/
		isConstant, GlobalVariable::PrivateLinkage, newInitializer,
				AI.getName());
		SrcAsGlobalVal->setUnnamedAddr(GlobalValue::UnnamedAddr::Global);
		// Set the alignment to that of an array items. We will be only loading one
		// value out of it.
		dyn_cast<GlobalVariable>(SrcAsGlobalVal)->setAlignment(Align(1));

	} else if (auto *II = dyn_cast<IntrinsicInst>(def)) {
		switch (II->getIntrinsicID()) {
		case Intrinsic::memcpy: {
			// check for memcopy from existing global value
			auto src = II->getArgOperand(1);
			SrcAsGlobalVal = dyn_cast<GlobalValue>(src);
			if (SrcAsGlobalVal) {
				if (SrcAsGlobalVal->getNumUses() == 1) {
				} else {
					errs() << AI << "\n";
					llvm_unreachable(
							"NotImplemented duplicate global if this is not just rom");
				}
			} else {
				errs() << AI << "\n";
				llvm_unreachable("NotImplemented source of memcpy");
			}
			break;
		}
		default:
			errs() << AI << "\n";
			llvm_unreachable("NotImplemented intristic");
		}
	}

	if (!SrcAsGlobalVal->hasName()) {
		SrcAsGlobalVal->setName(AI.getName());
	}
	if (AI.getIterator() == Iit)
		++Iit;
	assert(AI.getAddressSpace() == SrcAsGlobalVal->getAddressSpace());
	AI.replaceAllUsesWith(SrcAsGlobalVal);
	AI.eraseFromParent();
	if (Iit == def->getIterator()) {
		++Iit;
	}
	def->eraseFromParent();
}

void rewriteAllocaToGlobalValue(const DataLayout &DL, BasicBlock::iterator &Iit,
		AllocaInst &AI) {
	SmallVector<Instruction*> completeDefs;
	SmallVector<Instruction*> partialDefs;
	std::set<Instruction*> seenCompleteRewrites;

	// :note:
	//    allocSize is number of bytes of data + alignment + padding
	//    allocTypeSize is number of bytes required by data allone
	TypeSize allocSize = DL.getTypeAllocSize(AI.getAllocatedType());
	bool anyStoreSeen = false;
	discoverStoresToAddr(AI, anyStoreSeen, allocSize, AI, completeDefs, partialDefs, seenCompleteRewrites);

	if (completeDefs.empty()) {
		if (!anyStoreSeen)
			throw std::runtime_error(
					"memory of alloca is missing any initialization"
							+ AI.getName().str());
	} else if (completeDefs.size() == 1) {
		Instruction *def = completeDefs[0];
		bool isConstant = partialDefs.empty();
		rewriteAllocaInitToGlobalValue(Iit, AI, allocSize, def, isConstant);
	} else {
		// there are multiple initializations
		BasicBlock &defBB = *AI.getParent();
		// check for case that the AllocaInst and its initialization is executed only once
		Instruction *defInDefBB = nullptr;
		SmallVector<Instruction*> dominatedDefs;
		for (auto def : completeDefs) {
			if (def->getParent() == &defBB) {
				if (defInDefBB) {
					if (defInDefBB->comesBefore(def)) {
						dominatedDefs.push_back(defInDefBB);
						defInDefBB = def; // get last instruction in this block which initializes alloca memory
					} else {
						dominatedDefs.push_back(def);
					}
				} else {
					defInDefBB = def;
				}
			}
		}
		if (defInDefBB) {
			// check that the data of alloca is not read until last initialization instruction
			for (auto I = AI.getIterator(); I != defInDefBB->getIterator();
					++I) {
				if (auto GEP = dyn_cast<GetElementPtrInst>(I)) {
					if (GEP->getPointerOperand() == &AI) {
						llvm_unreachable(
								"Address of AllocaInst taken before initialization");
					}
				} else if (auto St = dyn_cast<LoadInst>(I)) {
					if (St->getPointerOperand() == &AI) {
						llvm_unreachable(
								"Load from AllocaInst before initialization");
					}
				}
			}

			for (auto I : dominatedDefs) {
				if (Iit == I->getIterator()) {
					++Iit;
				}
				I->eraseFromParent();
			}
			bool isConstant = partialDefs.empty() && completeDefs.size() == dominatedDefs.size() + 1;
			rewriteAllocaInitToGlobalValue(Iit, AI, allocSize, defInDefBB,
					isConstant);
		} else {
			errs() << AI << "\n";
			llvm_unreachable(
					"NotImplemented multiple stores but none of them in entry block");

		}
	}
}

// [todo] this should be ModulePass because it produces GlobalValue
llvm::PreservedAnalyses PromoteAllocaToGlobalPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	const DataLayout &DL = F.getDataLayout();
	for (auto &BB : F) {
		for (auto Iit = BB.begin(); Iit != BB.end();) {
			Instruction &I = *Iit;
			if (auto AI = dyn_cast<AllocaInst>(&I)) {
				rewriteAllocaToGlobalValue(DL, Iit, *AI);
			} else {
				++Iit;
			}
		}

	}
	return PreservedAnalyses::none();
}

}
