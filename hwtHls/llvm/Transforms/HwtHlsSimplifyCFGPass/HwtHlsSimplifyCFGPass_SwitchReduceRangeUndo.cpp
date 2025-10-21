#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchReduceRangeUndo.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>

#include <llvm/IR/Intrinsics.h>
#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

// convert the range reduced switch inst produced by llvm SimplifyCFG ReduceSwitchRange
// to a format without @llvm.fshl
bool HwtHlsSimplifyCFGPass_SwitchReduceRangeUndo(llvm::SwitchInst &I) {
	// llvm SimplifyCFG ReduceSwitchRange called from llvm::SimplifyCFGOpt::simplifySwitch does following transformation:
	//
	// .. code-block:: llvm
	//
	//     %2 = load i5, ptr %rxDataOffset, align 1
	//     switch i5 %2, label %%bbUnreachable [
	//       i5 0, label %bb0
	//       i5 -8, label %bb24
	//       i5 -16, label %bb16
	//       i5 8, label %bb8
	//     ]
	//     ; to
	//     %2 = load i5, ptr %rxDataOffset, align 1
	//     %3 = sub i5 %2, -16 ; -16 == msb=1 and others=0
	//     %4 = call i5 @llvm.fshl.i5(i5 %3, i5 %3, i5 2) ; shift is BitWidth - min(cttz(v) for v in case values)
	//     switch i5 %4, label %%bbUnreachable [
	//       i5 2, label %bb0
	//       i5 1, label %bb24
	//       i5 0, label %bb16
	//       i5 3, label %bb8
	//     ]
	auto C = I.getCondition();
	Value *fshlLhs, *fshlRhs;
	uint64_t sh;
	if (match(C,
			m_Intrinsic<Intrinsic::fshl>(m_Value(fshlLhs), m_Value(fshlRhs),
					m_ConstantInt(sh)))) {
		if (fshlLhs != fshlRhs)
			return false;
		Value *origC;
		uint64_t Base;
		if (match(fshlLhs, m_Sub(m_Value(origC), m_ConstantInt(Base)))) {
			auto Ty = dyn_cast<IntegerType>(C->getType());
			uint64_t Shift = Ty->getBitWidth() - sh;

			I.setCondition(origC);
			for (auto Case : I.cases()) {
				auto *Orig = Case.getCaseValue();
				auto lshrUndo = Orig->getValue().shl(Shift);
				auto SubUndo = lshrUndo + APInt(Ty->getBitWidth(), Base);
				Case.setValue(cast<ConstantInt>(ConstantInt::get(Ty, SubUndo)));
			}
			if (!C->hasNUsesOrMore(1))
				dyn_cast<Instruction>(C)->eraseFromParent();
			if (!fshlLhs->hasNUsesOrMore(1))
				dyn_cast<Instruction>(fshlLhs)->eraseFromParent();
			return true;
		}
	}
	return false;
}

}
