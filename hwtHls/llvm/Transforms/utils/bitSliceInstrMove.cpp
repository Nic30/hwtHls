#include <hwtHls/llvm/Transforms/utils/bitSliceInstrMove.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/setList.h>

using namespace llvm;

namespace hwtHls {


bool moveIntoSliceSuccessorsOf(llvm::Instruction &IToMoveAfterSrc, llvm::Instruction &src) {
	if (IToMoveAfterSrc.getIterator() != IToMoveAfterSrc.getParent()->begin()) {
		auto predI = IToMoveAfterSrc.getPrevNode();
		if (predI == &src) {
			return false;
		// check that predecessor some form of slice on same src
		} else if (isa<llvm::TruncInst>(predI)) {
			auto _src = predI->getOperand(0);
			if (_src == &src)
				return false;
		} else if (auto CI = llvm::dyn_cast<llvm::CallInst>(predI)) {
			if (IsBitRangeGet(CI)) {
				auto _src = CI->getArgOperand(0);
				if (_src == &src)
					return false;
			}
		}
	}
	if (llvm::isa<llvm::PHINode>(&src)) {
		auto firstNonPhi = src.getParent()->getFirstNonPHIIt();
		if (firstNonPhi != src.getParent()->end())
			IToMoveAfterSrc.moveBefore(firstNonPhi);
		else
			IToMoveAfterSrc.moveAfter(&src.getParent()->back());
	} else {
		IToMoveAfterSrc.moveAfter(&src);
	}
	return true;
}

bool BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(llvm::CallInst &I) {
	auto src = I.getArgOperand(0);
	if (auto srcI = llvm::dyn_cast<llvm::Instruction>(src))
		return moveIntoSliceSuccessorsOf(I, *srcI);
	return false;
}

bool TruncInstMoveIntoSliceSuccessorsOfSrcOperand(llvm::TruncInst &I) {
	auto src = I.getOperand(0);
	if (auto srcI = llvm::dyn_cast<llvm::Instruction>(src))
		return moveIntoSliceSuccessorsOf(I, *srcI);
	return false;
}


void moveSlicesDirectlyAfterSrcOpDef(Function &F) {
	// move bit slices directly after their src operand def so they are
	// dominating al uses of src
	ListSet<Instruction *> Worklist;
	for (BasicBlock &BB : F) {
		for (Instruction &I : make_early_inc_range(BB)) {
			if (isAnyFormOfBitRangeGet(&I) &&
				!isAnyFormOfBitRangeGet_forValue(I.getOperand(0)))
				Worklist.push_back(&I);
		}
	}
	while (!Worklist.empty()) {
		Instruction *I = Worklist.pop_front_val();
		if (auto T = dyn_cast<TruncInst>(I)) {
			TruncInstMoveIntoSliceSuccessorsOfSrcOperand(*T);
		} else if (auto C = dyn_cast<CallInst>(I)) {
			if (IsBitRangeGet(C)) {
				BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(*C);
			}
		} else {
			// not a BitRangeGet/trunc, the slice normalization does not affect
			// this instr
			continue;
		}
		// once we src slice is on correct place, we query users of it so they
		// move also to correct place if required
		for (auto U : I->users()) {
			if (auto UI = dyn_cast<Instruction>(U))
				Worklist.push_back(UI);
		}
	}
}

}