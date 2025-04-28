#include <hwtHls/llvm/Transforms/SimpleConstEvalPass.h>

#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/IR/IRBuilder.h>
#include <algorithm>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

using namespace llvm;

namespace hwtHls {

void addAllUsersToWorklist(Instruction &I, SetVector<Instruction*>& Worklist) {
	for (User* U: I.users()) {
		if (auto UI = dyn_cast<Instruction>(U)) {
			Worklist.insert(UI);
		}
	}
}

bool tryReduceConstOpConcat(IRBuilder<>& Builder, DceWorklist& DCE, SetVector<Instruction*>& Worklist, CallInst & CI) {
	SmallVector<Value*> newOps;
	ConstantInt * lastInt = nullptr;
	UndefValue * lastUndef = nullptr;
	PoisonValue * lastPoison = nullptr;
	auto& Ctx = CI.getContext();
	for (Use &_A : CI.args()) {
		auto & A = *_A.get();
		if (auto* ACint = dyn_cast<ConstantInt>(&A)) {
			if (lastInt) {
				lastInt = ConstantInt::get(Ctx, ACint->getValue().concat(lastInt->getValue()));
				newOps.back() = lastInt;
			} else {
				lastInt = ACint;
				newOps.push_back(ACint);
			}
			lastUndef = nullptr;
			lastPoison = nullptr;
		} else if (auto* poison = dyn_cast<PoisonValue>(&A)) {
			if (lastPoison) {
				size_t newWidth  = lastPoison->getType()->getIntegerBitWidth() + poison->getType()->getIntegerBitWidth();
				newOps.back() = lastPoison = PoisonValue::get(IntegerType::get(Ctx, newWidth));
			} else {
				lastPoison = poison;
				newOps.push_back(poison);
			}
			lastInt = nullptr;
			lastUndef = nullptr;
		} else if (auto* undef = dyn_cast<UndefValue>(&A)) {
			if (lastUndef) {
				size_t newWidth  = lastUndef->getType()->getIntegerBitWidth() + undef->getType()->getIntegerBitWidth();
				newOps.back() = lastUndef =UndefValue::get(IntegerType::get(Ctx, newWidth));
			} else {
				lastUndef = undef;
				newOps.push_back(undef);
			}
			lastInt = nullptr;
			lastPoison = nullptr;
		} else {
			newOps.push_back(&A);
			lastInt = nullptr;
			lastUndef = nullptr;
			lastPoison = nullptr;
		}
	}
	if (newOps.size() < CI.arg_size()) {
		Builder.SetInsertPoint(&CI);
		auto replacement = CreateBitConcat(&Builder, newOps);
		assert(replacement != &CI);
		addAllUsersToWorklist(CI, Worklist);
		CI.replaceAllUsesWith(replacement);
		DCE.insert(CI);
		return true;
	}
	return false;

}
bool tryReduceConstOpBitRangeGet(IRBuilder<>& Builder, DceWorklist& DCE, SetVector<Instruction*>& Worklist, CallInst & CI) {
	auto srcOp = CI.getArgOperand(0);
	auto indexOp = dyn_cast<ConstantInt>(CI.getArgOperand(1));
	assert(indexOp && "BitRangeGet offset should always be constant");
	auto& Ctx = CI.getContext();
	Value * replacement = nullptr;
	if (auto srcC = dyn_cast<ConstantInt>(srcOp)) {
		Builder.SetInsertPoint(&CI);
		size_t resWidth = CI.getType()->getIntegerBitWidth();
		replacement = ConstantInt::get(Ctx, srcC->getValue().extractBits(resWidth, indexOp->getZExtValue()));
	} else if (isa<PoisonValue>(srcOp)) {
		replacement = PoisonValue::get(CI.getType());
	} else if (isa<UndefValue>(srcOp)) {
		replacement = UndefValue::get(CI.getType());
	}
	if (replacement) {
		assert(replacement != &CI);
		addAllUsersToWorklist(CI, Worklist);
		CI.replaceAllUsesWith(replacement);
		DCE.insert(CI);
		return true;
	}
	return false;
}


PreservedAnalyses SimpleConstEvalPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	DceWorklist DCE(TLI, nullptr);
	bool Changed = false;
	SetVector<Instruction*> Worklist;
	IRBuilder<> Builder(F.getContext());
	for (BasicBlock &BB : F) {
		for (auto Iit = BB.begin(); Iit != BB.end(); ++Iit) {
			if (auto CI = dyn_cast<CallInst>(&*Iit)) {
				if (IsBitConcat(CI)) {
					Changed |= tryReduceConstOpConcat(Builder, DCE, Worklist, *CI);
					Changed |= DCE.runToCompletition(Iit);
				} else if (IsBitRangeGet(CI)) {
					Changed |= tryReduceConstOpBitRangeGet(Builder, DCE, Worklist, *CI);
					Changed |= DCE.runToCompletition(Iit);
				}
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
}

}
