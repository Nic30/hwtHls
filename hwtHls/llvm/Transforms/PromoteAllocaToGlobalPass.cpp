#include <hwtHls/llvm/Transforms/PromoteAllocaToGlobalPass.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/IR/IntrinsicInst.h>
#include <set>

using namespace llvm;

namespace hwtHls {

bool discoverStoresToAddr(Instruction &AllocaI, bool &anyStoreSeen,
		TypeSize allocSize, Instruction &I, SmallVector<Instruction*> &defs,
		std::set<Instruction*> &seen) {
	for (auto *U : I.users()) {
		if (auto UI = dyn_cast<Instruction>(U)) {
			if (seen.contains(UI))
				continue;
			seen.insert(UI);
		}

		if (isa<LoadInst>(U)) {
		} else if (auto *ST = dyn_cast<StoreInst>(U)) {
			if (ST->getAccessType()->getScalarSizeInBits() == allocSize * 8) {
				defs.push_back(ST);
			}
			anyStoreSeen = true;
		} else if (auto *II = dyn_cast<IntrinsicInst>(U)) {
			switch (II->getIntrinsicID()) {
			case Intrinsic::memcpy:
				//case Intrinsic::memmove:
				//case Intrinsic::memset:
			{

				auto dst = II->getArgOperand(0);
				auto size = II->getArgOperand(2);
				if (dst == &AllocaI && dyn_cast<ConstantInt>(size)
						&& dyn_cast<ConstantInt>(size)->getZExtValue()
								== allocSize) {
					defs.push_back(II);
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
					defs, seen))
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
		TypeSize allocSize, Instruction *def) {
	GlobalValue *SrcAsGlobalVal = nullptr;
	if (auto *ST = dyn_cast<StoreInst>(def)) {
		// based on CreateGlobalDataWithGEP
		auto AllocTy = dyn_cast<ArrayType>(AI.getAllocatedType());
		assert(AllocTy);
		auto elmTy = AllocTy->getArrayElementType();
		assert(elmTy->isIntegerTy());
		auto elmWidth = elmTy->getScalarSizeInBits();
		auto V = ST->getValueOperand();
		assert(V->getType()->isIntegerTy());
		assert(V->getType()->getIntegerBitWidth() == allocSize * 8);
		auto VasC = dyn_cast<ConstantInt>(V);
		assert(VasC);

		APInt VasAPInt = VasC->getValue();
		Module &M = *AI.getParent()->getParent()->getParent();
		std::vector<Constant*> initData;
		initData.reserve(AllocTy->getNumElements());
		auto &C = AI.getContext();
		for (size_t i = 0; i < AllocTy->getNumElements(); ++i) {
			auto item = VasAPInt.extractBits(elmWidth, i*elmWidth);
			initData.push_back(ConstantInt::get(C, item));
		}

		auto *newCArray = ConstantArray::get(AllocTy, initData);
		SrcAsGlobalVal = new GlobalVariable(M, AllocTy, /*isConstant=*/
		true, GlobalVariable::PrivateLinkage, newCArray, AI.getName());
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
	++Iit;
	AI.replaceAllUsesWith(SrcAsGlobalVal);
	AI.eraseFromParent();
	if (Iit == def->getIterator()) {
		++Iit;
	}
	def->eraseFromParent();
}

void rewriteAllocaToGlobalValue(const DataLayout &DL, BasicBlock::iterator &Iit,
		AllocaInst &AI) {
	SmallVector<Instruction*> defs;
	std::set<Instruction*> seen;

	TypeSize allocSize = DL.getTypeAllocSize(AI.getAllocatedType());
	bool anyStoreSeen = false;
	discoverStoresToAddr(AI, anyStoreSeen, allocSize, AI, defs, seen);

	if (defs.empty()) {
		if (!anyStoreSeen)
			throw std::runtime_error(
					"memory of alloca is missing any initialization"
							+ AI.getName().str());
	} else if (defs.size() == 1) {
		Instruction *def = defs[0];
		rewriteAllocaInitToGlobalValue(Iit, AI, allocSize, def);
	} else {
		// there are multiple initializations
		BasicBlock &entryBB = AI.getParent()->getParent()->getEntryBlock();
		// check for case that the AllocaInst and its initialization is executed only once
		if (AI.getParent() == &entryBB) {
			Instruction *defInEntryBB = nullptr;
			for (auto def : defs) {
				if (def->getParent() == &entryBB) {
					assert(
							!defInEntryBB
									&& "There should be at most a single store like instruction for alloca in entry block");
					defInEntryBB = def;
				}
			}
			if (defInEntryBB) {
				rewriteAllocaInitToGlobalValue(Iit, AI, allocSize, defInEntryBB);
			} else {
				errs() << AI << "\n";
				llvm_unreachable(
						"NotImplemented multiple stores but none of them in entry block");

			}
		}
		errs() << AI << "\n";
		llvm_unreachable(
				"NotImplemented multiple stores - resolve which one is initialization");
	}
}

// [todo] this should be ModulePass because it produces GlobalValue
llvm::PreservedAnalyses PromoteAllocaToGlobalPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	const DataLayout &DL = F.getParent()->getDataLayout();
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
	return PreservedAnalyses();
}

}
