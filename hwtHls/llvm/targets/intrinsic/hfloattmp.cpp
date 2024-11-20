#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <llvm/ADT/StringExtras.h>
#include <math.h>

using namespace llvm;

namespace hwtHls {

bool HFloatTmpConfig::operator==(const HFloatTmpConfig &other) const {
	return std::memcmp(this, &other, sizeof *this) == 0;
}
size_t HFloatTmpConfig::__hash__() const {
	llvm::SmallVector<unsigned, 9> Bits;
	Bits.push_back(exponentOrIntWidth);
	Bits.push_back(mantissaOrFracWidth);
	Bits.push_back(isInQFromat);
	Bits.push_back(supportSubnormal);
	Bits.push_back(hasSign);
	Bits.push_back(hasIsNaN);
	Bits.push_back(hasIsInf);
	Bits.push_back(hasIs1);
	Bits.push_back(hasIs0);

	return llvm::hash_combine_range(Bits.begin(), Bits.end());
}


template<typename INT_T>
INT_T mask(size_t numberOfBits) {
	static_assert(!std::is_signed<INT_T>::value);
	INT_T v = -1;
	v >>= (sizeof v) * 8 - numberOfBits;
	return v;
}

APInt HFloatTmpConfig::bitCastAPFloatToHFloatTmpAPInt(const APFloat &v) const {
	// IEEE-754 s special meanings
	//
	// Meaning             Sign Field   Exponent Field    Mantissa Field
	// Zero                Don't care   All 0s            All 0s
	// Positive subnormal  0            All 0s            Non-zero
	// Negative subnormal  1            All 0s            Non-zero
	// Positive Infinity   0            All 1s            All 0s
	// Negative Infinity   1            All 1s            All 0s
	// Not a Number(NaN)   Don't care   All 1s            Non-zero
	const HFloatTmpConfig &fpCfg = *this;
	auto res = APInt(fpCfg.getBitWidth(), 0);

	auto vAsDouble = v.convertToDouble();
	auto vAsAPInt = v.bitcastToAPInt();
	// bool issubnormal_ = issubnormal(vAsDouble);
	size_t CUR_MANTISA_W = 52;
	size_t CUR_EXP_W = 11;

	uint64_t mantissa = vAsAPInt.extractBits(CUR_MANTISA_W, 0).getZExtValue();
	uint64_t _exponent =
			vAsAPInt.extractBits(CUR_EXP_W, CUR_MANTISA_W).getZExtValue();
	int exponent = ((int) _exponent) + -mask<unsigned>(CUR_EXP_W - 1);
	uint64_t sign =
			vAsAPInt.extractBits(1, CUR_EXP_W + CUR_MANTISA_W).getZExtValue();
	size_t offset = 0;
	bool isInf = isinf(vAsDouble);
	// resolve mantissa/exponent or int and frac part if it is in Q format
	if (fpCfg.isInQFromat) {
		const size_t numWidth = fpCfg.exponentOrIntWidth
				+ fpCfg.mantissaOrFracWidth;
		if (isnan(vAsDouble) || vAsDouble == 0.0
				|| (issubnormal(vAsDouble) && !fpCfg.supportSubnormal)) {
			// keep all bits 0
			offset += numWidth;
		} else if (isinf(vAsDouble)) {
			if (vAsDouble < 0.0) {
				// set to min value
				offset += numWidth;
				if (fpCfg.hasSign) {
					res.setBit(offset - 1);
				}
			} else {
				// set to max value (all bits except first set, if number is signed)
				res.setBits(offset, offset + fpCfg.mantissaOrFracWidth);
				offset += fpCfg.mantissaOrFracWidth;
				res.setBits(offset, offset + fpCfg.exponentOrIntWidth);
				offset += fpCfg.exponentOrIntWidth;
				if (fpCfg.hasSign) {
					res.clearBit(offset - 1);
				}
			}
		} else {
			assert(
					fpCfg.exponentOrIntWidth + fpCfg.mantissaOrFracWidth < 64
							&& "Rounding may have happened");
			if (issubnormal(vAsDouble))
				llvm_unreachable(
						"NotImplemented: convert subnormal constant to Q format");
			// shift mantissa on proper position
			mantissa |= 1ul << CUR_MANTISA_W; // set first 1 which was omitted in FP mantissa format
			int fracWidth = CUR_MANTISA_W;
			int requiredFracWidth = fpCfg.mantissaOrFracWidth;
			int rshiftAmountToAliginFrac = fracWidth - requiredFracWidth;
			int rshiftAmount = rshiftAmountToAliginFrac - exponent;
			if (rshiftAmount < 0) {
				mantissa <<= -rshiftAmount;
			} else {
				mantissa >>= rshiftAmount;
			}
			res |= mantissa & mask<uint64_t>(numWidth);
			if (fpCfg.hasSign && vAsDouble < 0.0) {
				res = -res;
			}
			offset += numWidth;
		}
	} else {
		size_t newMantisaW = fpCfg.mantissaOrFracWidth;
		if (_exponent == 0) {
			// exponent == all 0
			if (mantissa == 0) {
				// zero case
			} else {
				// subnormal case
				if (fpCfg.supportSubnormal) {
					if (newMantisaW < CUR_MANTISA_W)
						mantissa >>= CUR_MANTISA_W - newMantisaW;
				} else {
					mantissa = 0;
				}
			}
		} else if (_exponent == mask<uint64_t>(CUR_EXP_W)) {
			// exponent == all 1
			if (mantissa == 0) {
				// inf case
			} else {
				// nan case
				mantissa = mask<uint64_t>(newMantisaW);
			}
		} else {
			size_t shiftedOutBits = 0;
			if (CUR_MANTISA_W > newMantisaW) {
				// need to shift mantissa and update exponent
				auto shAmount = CUR_MANTISA_W - newMantisaW;
				shiftedOutBits |= (mantissa & mask<uint64_t>(shAmount)) << (64 - shAmount);
				mantissa >>= shAmount;
			}
			int newExpOffset = -mask<unsigned>(fpCfg.exponentOrIntWidth - 1);
			int newExpMin = newExpOffset;
			int newExpMax = -newExpOffset + 1;
			if (exponent < newExpMin) {
				// may become 0 or subnormal
				size_t shAmount = -exponent - -newExpMin;
				shiftedOutBits >>= shAmount;
				shiftedOutBits |= (mantissa & mask<uint64_t>(shAmount)) << (64 - shAmount);
				if (shiftedOutBits != 0 && fpCfg.supportSubnormal) {
					llvm_unreachable("NotImplemented: convert fp constant which become subnormal to a fp type of a different width");
				}
			} else if (exponent > newExpMax) {
				// become +-inf
				isInf = true;
				exponent = newExpMin - 1;
				mantissa = 0;
			}
			res.insertBits(mantissa, offset, fpCfg.mantissaOrFracWidth);
			offset += fpCfg.mantissaOrFracWidth;
			size_t newExponent = (exponent + -newExpOffset) & mask<uint64_t>(fpCfg.exponentOrIntWidth);
			res.insertBits(newExponent, offset, fpCfg.exponentOrIntWidth);
			offset += fpCfg.exponentOrIntWidth;
		}
		// fill sign and other special flags
		if (fpCfg.hasSign) {
			if (sign) {
				res.setBit(offset);
			}
			offset += 1;
		} else {
			assert(
					!sign
							&& "Can not convert negative float constant to type without sign");
		}
	}

	if (fpCfg.hasIsNaN) {
		if (isnan(vAsDouble)) {
			res.setBit(offset);
		}
		offset += 1;
	}
	// else {
	// 	assert(
	// 			!(fpCfg.isInQFromat && isnan(vAsDouble))
	// 					&& "Can not convert NaN constant to q formated number without isNaN flag");
	// }
	if (fpCfg.hasIsInf) {
		if (isInf) {
			res.setBit(offset);
		}
		offset += 1;
	} else {
		assert(
				!(fpCfg.isInQFromat && isInf)
						&& "Can not convert Inf constant to q formated number without isInf flag");
	}
	if (fpCfg.hasIs1) {
		if (vAsDouble == 1.0) {
			res.setBit(offset);
		}
		offset += 1;
	}
	if (fpCfg.hasIs0) {
		if (vAsDouble == 0.0) {
			res.setBit(offset);
		}
		offset += 1;
	}
	return res;
}

static uint64_t extractConstIntFromArg(User::op_iterator &A,
		User::op_iterator AEnd) {
	assert(A != AEnd);
	auto c = dyn_cast<ConstantInt>(A->get());
	A++;
	assert(
			c
					&& "Arguments specifying HFloatTmpConfig members should be only constant integers");
	return c->getZExtValue();
}

HFloatTmpConfig HFloatTmpConfig::fromCallArgs(llvm::CallInst &CI,
		size_t argsToSkip) {
	HFloatTmpConfig res;
	auto A = CI.arg_begin();
	auto AEnd = CI.arg_end();
	for (size_t i = 0; i < argsToSkip; i++) {
		assert(A != AEnd);
		A++;
	}
	res.exponentOrIntWidth = extractConstIntFromArg(A, AEnd);
	res.mantissaOrFracWidth = extractConstIntFromArg(A, AEnd);
	res.isInQFromat = extractConstIntFromArg(A, AEnd);
	res.supportSubnormal = extractConstIntFromArg(A, AEnd);
	res.hasSign = extractConstIntFromArg(A, AEnd);
	res.hasIsNaN = extractConstIntFromArg(A, AEnd);
	res.hasIsInf = extractConstIntFromArg(A, AEnd);
	res.hasIs1 = extractConstIntFromArg(A, AEnd);
	res.hasIs0 = extractConstIntFromArg(A, AEnd);
	return res;
}

#define HFloatTmpConfig_PARAMS \
		std::uint8_t exponentOrIntWidth, std::uint8_t mantissaOrFracWidth, \
		bool isInQFromat, bool supportSubnormal, \
		bool hasSign, bool hasIsNaN, bool hasIsInf, \
		bool hasIs1, bool hasIs0
#define HFloatTmpConfig_ARGS \
	exponentOrIntWidth, mantissaOrFracWidth, \
	isInQFromat, supportSubnormal,           \
	hasSign, hasIsNaN,                       \
	hasIsInf, hasIs1, hasIs0
#define HFloatTmpConfig_FROM_LOCALS \
		(HFloatTmpConfig ) { HFloatTmpConfig_ARGS }

#define HFloatTmpConfig_ARGS_TO_LLVM(Builder) \
	Builder->getInt8(exponentOrIntWidth),     \
	Builder->getInt8(mantissaOrFracWidth),    \
	Builder->getInt1(isInQFromat),            \
	Builder->getInt1(supportSubnormal),       \
	Builder->getInt1(hasSign),                \
	Builder->getInt1(hasIsNaN),               \
	Builder->getInt1(hasIsInf),               \
	Builder->getInt1(hasIs1),                 \
	Builder->getInt1(hasIs0)

const std::string CastToHFloatTmpName = "hwtHls.castToHFloatTmp";

#define HFloatTmpConfig_UN_OP_ARG_TYPES(Ops)\
	Ops[0]->getType(), Ops[1]->getType(),\
	Ops[2]->getType(), Ops[3]->getType(),\
	Ops[4]->getType(), Ops[5]->getType(),\
	Ops[6]->getType(), Ops[7]->getType(),\
	Ops[8]->getType(), Ops[9]->getType()

#define HFloatTmpConfig_BIN_OP_ARG_TYPES(Ops) \
	HFloatTmpConfig_UN_OP_ARG_TYPES(Ops), Ops[10]->getType()

llvm::CallInst* CreateCastToHFloatTmp(llvm::IRBuilder<> *Builder,
		llvm::Value *srcArg, HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	assert(srcArg->getType()->isIntegerTy());
	if (isInQFromat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;
	assert(srcArg->getType()->getIntegerBitWidth() == tyCfg.getBitWidth());

	Value *Ops[] = { srcArg, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getDoubleTy();
	Type *TysForName[] = { Ops[0]->getType() };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(CastToHFloatTmpName, TysForName), ResT,
					HFloatTmpConfig_UN_OP_ARG_TYPES(Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;

}
bool IsCastToHFloatTmp(const llvm::CallInst *C) {
	return IsCastToHFloatTmp(C->getCalledFunction());
}
bool IsCastToHFloatTmp(const llvm::Function *F) {
	return F->getName().str().rfind(CastToHFloatTmpName + ".", 0) == 0;
}

const std::string CastFromHFloatTmpName = "hwtHls.castFromHFloatTmp";

llvm::CallInst* CreateCastFromHFloatTmp(llvm::IRBuilder<> *Builder,
		llvm::Value *srcArg, HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	if (isInQFromat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;

	assert(srcArg->getType()->isDoubleTy());

	Value *Ops[] = { srcArg, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getIntNTy(tyCfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(CastFromHFloatTmpName, TysForName), ResT,
					HFloatTmpConfig_UN_OP_ARG_TYPES(Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}
bool IsCastFromHFloatTmp(const llvm::CallInst *C) {
	return IsCastFromHFloatTmp(C->getCalledFunction());
}
bool IsCastFromHFloatTmp(const llvm::Function *F) {
	return F->getName().str().rfind(CastFromHFloatTmpName + ".", 0) == 0;
}

bool IsHwtHlsFp(const llvm::CallInst *C) {
	return IsHwtHlsFp(C->getCalledFunction());
}
bool IsHwtHlsFp(const llvm::Function *F) {
	return F->getName().str().rfind("hwtHls.fp.", 0) == 0;
}

llvm::CallInst* CreateHwtHlsFUnOp(llvm::IRBuilder<> *Builder,
		const std::string &intrinsicFnName, llvm::Value *op0,
		HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	if (isInQFromat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType()->getIntegerBitWidth() == tyCfg.getBitWidth());

	Value *Ops[] = { op0, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getIntNTy(tyCfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							Intrinsic_getName(intrinsicFnName, TysForName),
							ResT, HFloatTmpConfig_UN_OP_ARG_TYPES(Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

llvm::CallInst* CreateHwtHlsFBinOp(llvm::IRBuilder<> *Builder,
		const std::string &intrinsicFnName, llvm::Value *op0, llvm::Value *op1,
		HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	if (isInQFromat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType()->getIntegerBitWidth() == tyCfg.getBitWidth());
	assert(op0->getType() == op1->getType());

	Value *Ops[] = { op0, op1, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getIntNTy(tyCfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							Intrinsic_getName(intrinsicFnName, TysForName),
							ResT, HFloatTmpConfig_BIN_OP_ARG_TYPES(Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

// macros for definition of unary an binary operator functions and name variable

#define CONCAT_(prefix, suffix) prefix##suffix
/// Concatenate `prefix, suffix` into `prefixsuffix`
#define CONCAT(prefix, suffix) CONCAT_(prefix, suffix)

#define DEFINE_FP_BINOP(name, intrinsicName)                                             \
const std::string CONCAT(CONCAT(hwtHlsFp, name), Name) = "hwtHls.fp." #intrinsicName;    \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilder<> *Builder, llvm::Value *op0,       \
		llvm::Value *op1, HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {             \
	return CreateHwtHlsFBinOp(Builder, CONCAT(CONCAT(hwtHlsFp, name), Name), op0, op1,   \
			HFloatTmpConfig_ARGS, Name);                                                 \
}                                                                                        \
bool IsHwtHlsFp##name(const llvm::CallInst *C) {                                         \
	return IsHwtHlsFp##name(C->getCalledFunction());                                     \
}                                                                                        \
bool IsHwtHlsFp##name(const llvm::Function *F) {                                         \
	return F->getName().str().rfind(CONCAT(CONCAT(hwtHlsFp, name), Name) + ".", 0) == 0; \
}


#define DEFINE_FP_UNOP(name, intrinsicName)                                              \
const std::string CONCAT(CONCAT(hwtHlsFp, name), Name) = "hwtHls.fp." #intrinsicName;    \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilder<> *Builder, llvm::Value *op0,       \
		HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {                               \
	return CreateHwtHlsFUnOp(Builder, CONCAT(CONCAT(hwtHlsFp, name), Name), op0,         \
			HFloatTmpConfig_ARGS, Name);                                                 \
}                                                                                        \
bool IsHwtHlsFp##name(const llvm::CallInst *C) {                                         \
	return IsHwtHlsFp##name(C->getCalledFunction());                                     \
}                                                                                        \
bool IsHwtHlsFp##name(const llvm::Function *F) {                                         \
	return F->getName().str().rfind(CONCAT(CONCAT(hwtHlsFp, name), Name) + ".", 0) == 0; \
}


DEFINE_FP_BINOP(FAdd, fadd)
DEFINE_FP_BINOP(FSub, fsub)
DEFINE_FP_BINOP(FMul, fmul)
DEFINE_FP_BINOP(FDiv, fdiv)
DEFINE_FP_BINOP(FRem, frem)


const std::string hwtHlsFpFCmpName = "hwtHls.fp.fcmp";
llvm::CallInst* CreateHwtHlsFpFCmp(llvm::IRBuilder<> *Builder,
		llvm::CmpInst::Predicate predicate,
		llvm::Value *op0, llvm::Value *op1,
		HFloatTmpConfig_PARAMS, const llvm::Twine &Name) {
	if (isInQFromat)
			assert(
					!supportSubnormal
							&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");
	HFloatTmpConfig tyCfg = HFloatTmpConfig_FROM_LOCALS;
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType()->getIntegerBitWidth() == tyCfg.getBitWidth());
	assert(op0->getType() == op1->getType());

	Value *Ops[] = { Builder->getInt8(predicate), op0, op1, HFloatTmpConfig_ARGS_TO_LLVM(Builder) };
	Type *ResT = Builder->getIntNTy(1);
	Type *TysForName[] = { op0->getType() };
	Module *M = Builder->GetInsertBlock()->getParent()->getParent();
	std::string name = (Intrinsic_getName(hwtHlsFpFCmpName, TysForName) + "." + llvm::CmpInst::getPredicateName(predicate)).str();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							name,
							ResT,
							HFloatTmpConfig_BIN_OP_ARG_TYPES(Ops),
							Ops[11]->getType()).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder->CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

bool IsHwtHlsFpFCmp(const llvm::CallInst *C) {
	return IsHwtHlsFpFCmp(C->getCalledFunction());
}
bool IsHwtHlsFpFCmp(const llvm::Function *F) {
	return F->getName().str().rfind(hwtHlsFpFCmpName + ".", 0) == 0;
}

DEFINE_FP_UNOP(FNeg, fneg)

}
