#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/ConstantRange.h>
#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

llvm::Instruction* HwtHlsInstCombiner::tryReduceIntrinsicInst_fshlConstSh(
		IntrinsicInst &I) {
	const APInt *_sh;
	if (match(I.getArgOperand(2), m_APInt(_sh))) {
		// :see: hwtHls.code.fshl
		auto a = I.getArgOperand(0);
		auto b = I.getArgOperand(1);
		size_t w = a->getType()->getIntegerBitWidth();
		size_t sh = _sh->getZExtValue();
		sh %= w;
		Value *res;
		if (sh == 0)
			res = a;
		else if (sh == w)
			res = b;
		else {
			// b shifted into a from lsb
			// Concat(a[w - sh:], b[:w - sh])
			auto _a = CreateBitRangeGetConst(&Builder, a, 0, w - sh);
			auto _b = CreateBitRangeGetConst(&Builder, b, w - sh, sh);
			res = CreateBitConcat(&Builder, { _b, _a });
		}
		return replaceInstUsesWith(I, res);
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceIntrinsicInst_fshrConstSh(
		IntrinsicInst &I) {
	const APInt *_sh;
	if (match(I.getArgOperand(2), m_APInt(_sh))) {
		// :see: hwtHls.code.fshl
		auto a = I.getArgOperand(0);
		auto b = I.getArgOperand(1);
		size_t w = a->getType()->getIntegerBitWidth();
		size_t sh = _sh->getZExtValue();
		sh %= w;
		Value *res;
		if (sh == 0)
			res = a;
		else if (sh == w)
			res = b;
		else {
			// lower bits of 'b' shifter before 'a', lower bits of 'a' shifted out
			// Concat(b[sh:], a[:sh],)
			auto _a = CreateBitRangeGetConst(&Builder, a, sh, w - sh);
			auto _b = CreateBitRangeGetConst(&Builder, b, 0, sh);
			res = CreateBitConcat(&Builder, { _a, _b });
		}
		return replaceInstUsesWith(I, res);
	}
	return nullptr;
}
}
