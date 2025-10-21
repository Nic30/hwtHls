#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <math.h>
#include <llvm/IR/PatternMatch.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <hwtHls/llvm/bitMath.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {


llvm::Instruction* HwtHlsInstCombiner::_tryReduceHwtHlsFpFAdd(
		llvm::CallInst &I) {
	auto lhs = I.getArgOperand(0);
	auto rhs = I.getArgOperand(1);

	if (isa<PoisonValue>(rhs)) {
		return replaceInstUsesWith(I, PoisonValue::get(I.getType()));
	} else if (isa<UndefValue>(rhs)) {
		return replaceInstUsesWith(I, UndefValue::get(I.getType()));
	} else if (auto rhsC = dyn_cast<ConstantInt>(rhs)) {
		auto cfg = HFloatTmpConfig::fromCallArgs(I, 2);
		if (cfg.isInQFormat) {
			if (rhsC->isZero()) {
				// fadd x, 0 -> x
				return replaceInstUsesWith(I, lhs);
			}
		}
	} else {
		auto lhsC = dyn_cast<ConstantInt>(lhs);
		if (lhsC) {
			auto cfg = HFloatTmpConfig::fromCallArgs(I, 2);
			if (cfg.isInQFormat) {
				if (lhsC->isZero()) {
					// fadd 0, x -> x
					return replaceInstUsesWith(I, rhs);
				}
			}

		}
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceHwtHlsFpSub_to_addNeg(
		llvm::CallInst &I) {
	auto cfg = HFloatTmpConfig::fromCallArgs(I, 2);
	if (!cfg.isInQFormat) {
		auto lhs = I.getArgOperand(0);
		auto rhs = I.getArgOperand(1);
		rhs = CreateHwtHlsFpFNeg(Builder, rhs, cfg);
		auto r = CreateHwtHlsFpFAdd(Builder, lhs, rhs, cfg);

		return replaceInstUsesWith(I, r);
	}
	return nullptr;
}

}
