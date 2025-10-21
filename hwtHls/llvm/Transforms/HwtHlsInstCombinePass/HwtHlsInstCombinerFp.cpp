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

llvm::Instruction* HwtHlsInstCombiner::_tryReduceFMulDivByPow2_to_HwtHlsFpSh(
		llvm::BinaryOperator &I, Value *x, Value *sh, bool isMul) {
	// x * (2.0 ** sh) or x / (2.0 ** sh)
	auto *shForPosSh = &CreateHwtHlsFpUnspecializedShl;
	auto *shForNegSh = &CreateHwtHlsFpUnspecializedShr;
	if (!isMul) {
		std::swap(shForPosSh, shForNegSh);
	}
	Value *shTrunc;
	size_t shWidth = sh->getType()->getIntegerBitWidth();
	if (match(sh, m_ZExt(m_Value(shTrunc)))) {
		// sh is knonw to be >= 0
		auto shTrimmed = Builder.CreateZExt(shTrunc,
				Builder.getIntNTy(shWidth - 1));
		Value *r = (*shForPosSh)(Builder, x, shTrimmed, "");
		return replaceInstUsesWith(I, r);
	} else {
		// sh may be negative
		auto shLt0 = Builder.CreateIsNeg(sh);
		auto newShTy = Builder.getIntNTy(shWidth - 1);
		// dividing by pow 2
		auto shNeg = Builder.CreateNeg(sh);
		auto shNegTrimmed = Builder.CreateTrunc(shNeg, newShTy);
		Value *xShr = (*shForNegSh)(Builder, x, shNegTrimmed, "");
		// multiplying by pow 2
		auto shTrimmed = Builder.CreateTrunc(sh, newShTy);
		Value *xShl = (*shForPosSh)(Builder, x, shTrimmed, "");
		auto r = Builder.CreateSelect(shLt0, xShr, xShl);
		return replaceInstUsesWith(I, r);
	}
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceFDivByPow2_to_HwtHlsFpSh(
		llvm::BinaryOperator &I) {
	Value *x = I.getOperand(0);
	Value *sh;
	const APFloat *base;
	if (match(I.getOperand(1),
			m_Intrinsic<Intrinsic::powi>(m_APFloat(base), m_Value(sh)))) {
		if (isa<Constant>(sh))
			return nullptr; // perform const propagation first
		auto baseD = base->convertToDouble();
		if (baseD == 1.0) {
			// 1.0 ** any = 1.0
			// x / (1.0 ** sh) == x
			return replaceInstUsesWith(I, x);
		} else if (baseD == 2.0) {
			// x / (2.0 ** sh)
			_tryReduceFMulDivByPow2_to_HwtHlsFpSh(I, x, sh, false);
		}
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceFMulByPow2_to_HwtHlsFpSh(
		llvm::BinaryOperator &I) {
	Value *x = I.getOperand(0);
	Value *sh;
	const APFloat *base;
	// [todo] implementation for base of any pow of 2 (including negative one like 0.5)
	if (match(I.getOperand(1),
			m_Intrinsic<Intrinsic::powi>(m_APFloat(base), m_Value(sh)))) {
		if (isa<Constant>(sh))
			return nullptr; // perform const propagation first
		auto baseD = base->convertToDouble();
		if (baseD == 0.0) {
			// :attention: sh must be > 0
			// x * (0.0 ** sh) == sh == 0 ? x : 0.0
			auto shEq0 = Builder.CreateICmpEQ(sh,
					ConstantInt::get(sh->getType(), 0));
			auto sel = Builder.CreateSelect(shEq0, x,
					ConstantFP::get(x->getType(), 0.0));
			return replaceInstUsesWith(I, sel);
		} else if (baseD == 1.0) {
			// 1.0 ** any = 1.0
			// x * (1.0 ** sh) == x
			return replaceInstUsesWith(I, x);
		} else if (baseD == 2.0) {
			// x * (2.0 ** sh)
			return _tryReduceFMulDivByPow2_to_HwtHlsFpSh(I, x, sh, true);
		}
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::_tryReduceFRemByPow2_to_HwtHlsFpCast(
		llvm::CallInst &I) {
	// e.g. x rem 2. = (origTy) (q1.n) x

	// https://github.com/gpuweb/gpuweb/issues/1696
	// FRem "The floating-point remainder whose sign matches the sign of Operand 1."

	auto _op1 = dyn_cast<ConstantInt>(I.getArgOperand(1));
	if (!_op1)
		return nullptr;
	const auto &op1 = _op1->getValue();
	auto cfg = HFloatTmpConfig::fromCallArgs(I, 2);
	if (cfg.isInQFormat && op1.isPowerOf2()) {
		// x % 2**i case, this preserves all bits on right side from bit position defined by i which is resolved from op1 value
		// the cleared bits must be filled with msb if type is signed or with 0 if the type is signed
		auto trailingZeros = op1.countTrailingZeros();
		// e.g 1.0 rem 1.0 = 0.0
		// e.g 0.5 rem 1.0 = 0.5

		if (cfg.hasIs0 || cfg.hasIs1 || cfg.hasIsInf || cfg.hasIsNaN)
			llvm_unreachable(
					"NotImplemented: _tryReduceFRemByPow2_to_HwtHlsFpCast handle flag");

		auto op0 = I.getArgOperand(0);
		auto remBits = CreateBitRangeGetConst(&Builder, op0, 0, trailingZeros);
		Value *msbBits;
		size_t clearedBits = cfg.getBitWidth() - trailingZeros;
		if (cfg.hasSign) {
			auto msb = CreateBitRangeGetConst(&Builder, op0,
					cfg.getBitWidth() - 1, 1);
			if (clearedBits == 1) {
				msbBits = msb;
			} else {
				msbBits = Builder.CreateSelect(msb,
						ConstantInt::getAllOnesValue(
								Builder.getIntNTy(clearedBits)),
						Builder.getIntN(clearedBits, 0));
			}
		} else {
			msbBits = Builder.getIntN(clearedBits, 0);
		}
		auto res = CreateBitConcat(&Builder, { remBits, msbBits });
		return replaceInstUsesWith(I, res);
	}

	return nullptr;
}


llvm::Instruction* HwtHlsInstCombiner::_tryReduceFModByPow2_to_HwtHlsFpCast(
			llvm::CallInst &I) {
	// e.g. x % 2. = (origTy) (q1.n) x

	// https://github.com/gpuweb/gpuweb/issues/1696
	// OpFMod "The floating-point remainder whose sign matches the sign of Operand 2."

	auto _op1 = dyn_cast<ConstantInt>(I.getArgOperand(1));
	if (!_op1)
		return nullptr;
	const auto &op1 = _op1->getValue();
	auto cfg = HFloatTmpConfig::fromCallArgs(I, 2);
	if (cfg.isInQFormat && op1.isPowerOf2()) {
		auto trailingZeros = op1.countTrailingZeros();
		// e.g 1.0 % 1.0 = 0.0
		// e.g 0.5 % 1.0 = 0.5

		if (cfg.hasIs0 || cfg.hasIs1 || cfg.hasIsInf || cfg.hasIsNaN)
			llvm_unreachable(
					"NotImplemented: _tryReduceFModByPow2_to_HwtHlsFpCast handle flag");

		auto op0 = I.getArgOperand(0);
		if (cfg.hasSign) {
			op0 = CreateHwtHlsFpFAbs(Builder, op0, cfg);
		}
		size_t clearedBits = cfg.getBitWidth() - trailingZeros;
		Value *msbBits = Builder.getIntN(clearedBits, 0);
		auto modBits = CreateBitRangeGetConst(&Builder, op0, 0, trailingZeros);
		auto res = CreateBitConcat(&Builder, { modBits, msbBits });
		return replaceInstUsesWith(I, res);
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::_tryReduceCastHFloatTmpToHFloatTmpRaw(
		llvm::CallInst &I) {
	auto src = I.getArgOperand(0);
	if (isa<PoisonValue>(src)) {
		return replaceInstUsesWith(I, PoisonValue::get(I.getType()));
	} else if (isa<UndefValue>(src)) {
		return replaceInstUsesWith(I, UndefValue::get(I.getType()));
	} else if (auto srcC = dyn_cast<ConstantInt>(src)) {
		auto srcCfg = HFloatTmpConfig::fromCallArgs(I, 1);
		auto dstCfg = HFloatTmpConfig::fromCallArgs(I,
				1 + HFloatTmpConfig::MEMBER_CNT);
		auto v = srcCfg.bitCastHFloatTmpAPIntToAPFloat(srcC->getValue());
		auto res = dstCfg.bitCastAPFloatToHFloatTmpAPInt(v);
		return replaceInstUsesWith(I, Builder.getInt(res));
	}
	return nullptr;
}

llvm::Instruction* HwtHlsInstCombiner::_tryReduceCastHFloatTmpRaw(llvm::CallInst &I) {
	auto srcCfg = HFloatTmpConfig::fromCallArgs(I, 1);
	auto dstCfg = HFloatTmpConfig::fromCallArgs(I, 1 + HFloatTmpConfig::MEMBER_CNT);
	srcCfg.rounding = dstCfg.rounding;
	srcCfg.saturation = dstCfg.saturation;
	if (srcCfg == dstCfg) {
		// only type notation differs but physically it is the same value
		replaceInstUsesWith(I, I.getArgOperand(0));
	}

	return nullptr;
}


}
