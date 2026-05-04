#pragma once

#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/IRBuilder.h>
#include <iostream>

namespace llvm {
class MachineInstr;
}

namespace hwtHls {

/*
 * Intrinsic function for conversion to HFloatTmp which is just double in LLVM but this instruction
 * CastToHFloatTmp/CastFromHFloatTmp holds the info about type specialization for later lowering.
 * (The HFloatTmp exists because LLVM does support just some floating type variants and this is to allow any floating type.
 *  :see: llvm::Type::TypeID)
 * :note: LLVM has some intrinsics for fixed point like llvm.smul.fix.*, but they are not used, because there is only few of them
 *
 * */

// https://thax.hardliners.org/rounding/
enum HFloatTmpRounding {
	ROUND_HALF_EVEN, // nearest with ties going to nearest even integer. (c fp default)
	// also known as Gaussian rounding or bankers’ rounding, 1.5 -> 2, 2.5 -> 2
	// ROUND_HALF_DOWN, // nearest with ties going towards 0.
	ROUND_HALF_UP,  //  nearest with ties going away from 0.
	ROUND_DOWN,  //  towards 0.
	ROUND_CEILING,  // towards inf.
	ROUND_FLOOR,  // towards -Inf.
	// ROUND_UP, // away from 0.
	// ROUND_05UP, // away from 0 if last digit after rounding towards zero would have been 0 or 5;
	// otherwise towards 0.
	ROUND_WIDTH = 8,
	ROUND_C_DEFAULT = ROUND_HALF_EVEN,
};

enum HFloatTmpSaturation {
	SATURATE_NONE = 0,  // no saturation, operations may overflow
	SATURATE_INF = 3,  // saturate +/- inf
	SATURATE_WIDTH = 8,
	SATURATE_C_DEFAULT = SATURATE_INF,
};

class HFloatTmpConversionError: public std::runtime_error {
public:
	using std::runtime_error::runtime_error;
};

// :note: in Q is in ARM notation, IntWidth includes sign
// FP: (MSB) is0? is1? isInf? isNaN? sign? exponent mantissa (lsb)
// Q:  (MSB) is0? is1? isInf? isNaN? sign? intPart fractPart (lsb)
struct HFloatTmpConfig {
	// if true number is in Q format else number is in FP format
	bool isInQFormat;
	// width of exponent if number is in FP format, or width of int part if number is in Q format
	std::uint8_t exponentOrIntWidth;
	// width of mantissa part if number is in FP format, or width of fractional part if number is in Q format
	std::uint8_t mantissaOrFracWidth;
	// if number is in FP format the type supports subnormal numbers
	bool supportSubnormal;
	// if true type has sign bit
	bool hasSign;
	// if true type has dedicated bit for is NaN
	bool hasIsNaN;
	// if true type has dedicated bit for is Inf
	bool hasIsInf;
	// if true type has dedicated bit for is 1
	bool hasIs1;
	// if true type has dedicated bit for is 0
	bool hasIs0;

	HFloatTmpRounding rounding;
	HFloatTmpSaturation saturation;

	static constexpr size_t C_DOUBLE_MANTISA_W = 52;
	static constexpr size_t C_DOUBLE_EXPONENT_W = 11;
	HFloatTmpConfig() :
			HFloatTmpConfig(false, 0, 0) {
	}
	HFloatTmpConfig(bool isInQFormat,           //
			std::uint8_t exponentOrIntWidth,    //
			std::uint8_t mantissaOrFracWidth,   //
			bool supportSubnormal = true,       //
			bool hasSign = true, bool hasIsNaN = false, bool hasIsInf = false, //
			bool hasIs1 = false, bool hasIs0 = false,                         //
			HFloatTmpRounding rounding = HFloatTmpRounding::ROUND_C_DEFAULT,  //
			HFloatTmpSaturation saturation =
					HFloatTmpSaturation::SATURATE_C_DEFAULT);

	// the total number of members in this class
	static constexpr size_t MEMBER_CNT = 11;

	bool operator==(const HFloatTmpConfig &other) const;

	size_t getBitWidth() const {
		return exponentOrIntWidth + mantissaOrFracWidth
				+ (isInQFormat ? 0 : hasSign) // for q format sign is part of int part
				+ hasIsNaN + hasIsInf + hasIs1 + hasIs0;
	}

	size_t __hash__() const;

	// convert mantissa to Q formated number and apply rounding
	uint64_t _mantissaToFixedPointQWithRounding(bool sign, uint64_t mantissa,
			int exponent, size_t numWidth, size_t CUR_MANTISA_WIDTH) const;

	// load config from arguments of call of hwtHls.fp.* intrinsic
	static HFloatTmpConfig fromCallArgs(llvm::CallInst &CI, size_t argsToSkip =
			1);
	// load config from operands od HWTFPGA_FP_* MachineInstr instance
	static HFloatTmpConfig fromMachineInstrOperands(llvm::MachineInstr &MI,
			size_t operandOffset);
	static double fixp_resize_double(double x, bool isSigned,
            size_t inIntWidth, size_t inFracWidth,
			size_t outIntWidth, size_t outFracWidth,
			HFloatTmpRounding roundingMode,
			HFloatTmpSaturation saturationMode);
	// convert APFloat constant to a format specified by HFloatTmpConfig
	llvm::APInt bitCastAPFloatToHFloatTmpAPInt(const llvm::APFloat &v) const;
	// reverse of bitCastAPFloatToHFloatTmpAPInt
	llvm::APFloat bitCastHFloatTmpAPIntToAPFloat(const llvm::APInt &v) const;

	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
};

// :note: order of operands is the same as in Instruction.def and IntrinsicEnums.inc
//     to have some consistent order (same as in hFloatTmpOps.py)

extern const std::string CastToHFloatTmpName;
llvm::CallInst* CreateCastToHFloatTmp(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &cfg,
		const llvm::Twine &Name = "");
bool IsCastToHFloatTmp(const llvm::CallInst *C);
bool IsCastToHFloatTmp(const llvm::Function *F);

extern const std::string CastFromHFloatTmpName;
llvm::CallInst* CreateCastFromHFloatTmp(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &cfg,
		const llvm::Twine &Name = "");
bool IsCastFromHFloatTmp(const llvm::CallInst *C);
bool IsCastFromHFloatTmp(const llvm::Function *F);

extern const std::string CastHFloatTmpToHFloatTmpName;
/*
 * cast HFloatTmp to HFloatTmp (double) with possibly different configuration (precision, bitwidth, rounding, ...)
 * :note: this implements float to int and int to float like conversions, but src and return value are bouth of double type
 * which represents HFloatTmp
 * */
llvm::CallInst* CreateCastHFloatTmpToHFloatTmp(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &cfg,
		const llvm::Twine &Name = "");
bool IsCastHFloatTmpToHFloatTmp(const llvm::CallInst *C);
bool IsCastHFloatTmpToHFloatTmp(const llvm::Function *F);

extern const std::string CastHFloatTmpToHFloatTmpRawName;
/*
 * cast HFloatTmp to HFloatTmp (bit vector) with possibly different configuration (precision, bitwidth, rounding, ...)
 * :note: this implements float to int and int to float like conversions
 * */
llvm::CallInst* CreateCastHFloatTmpToHFloatTmpRaw(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &srcCfg, const HFloatTmpConfig &dstCfg,
		const llvm::Twine &Name = "");
bool IsCastHFloatTmpToHFloatTmpRaw(const llvm::CallInst *C);
bool IsCastHFloatTmpToHFloatTmpRaw(const llvm::Function *F);


bool IsHwtHlsFp(const llvm::CallInst *C);
bool IsHwtHlsFp(const llvm::Function *F);

/**
 * Not yet specialized variant of HwtHlsFp intrinsics
 * */
#define __DefineHwtHlsFpUnspecializedBinOp(name)                           \
extern const std::string IntrinsicNameHwtHlsFp##name;                      \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilderBase& Builder,           \
		llvm::Value *op0, llvm::Value *op1, const llvm::Twine &Name = ""); \
bool IsHwtHlsFp##name(const llvm::CallInst *C);                            \
bool IsHwtHlsFp##name(const llvm::Function *F);

// :attention: shl/shr operand is interpreted as unsigned
// :attention: shl/shr for fp types are should be infered in last step of translation
//             and the code should be in format x * (2.0 ** -sh) or x / (2.0 ** sh)
//             before this point to keep compatibility with llvm optimizations as
//             this intrinsic is treated as any other function call in llvm optimizations
__DefineHwtHlsFpUnspecializedBinOp(UnspecializedShl)
__DefineHwtHlsFpUnspecializedBinOp(UnspecializedShr)

#undef __DefineHwtHlsFpUnspecializedBinOp
/**
 * Specialized intrinsic functions which are replacing llvm floatingpoint intrinsic and operators
 * after HFloatTmpLoweringPass
 * :note: Thins are not defined using macro to make search in code easier
 * **/
#define __CreateHwtHlsFpUnOpParams llvm::IRBuilderBase& Builder, llvm::Value *op0, \
	const HFloatTmpConfig & cfg, const llvm::Twine &Name = ""
#define __CreateHwtHlsFpBinOpParams llvm::IRBuilderBase& Builder, llvm::Value *op0, llvm::Value *op1,\
	const HFloatTmpConfig & cfg, const llvm::Twine &Name = ""

#define __DefineHwtHlsFpBinOp(name)                                \
extern const std::string IntrinsicNameHwtHlsFp##name;              \
llvm::CallInst* CreateHwtHlsFp##name(__CreateHwtHlsFpBinOpParams); \
bool IsHwtHlsFp##name(const llvm::CallInst *C);                    \
bool IsHwtHlsFp##name(const llvm::Function *F);

#define __DefineHwtHlsFpUnOp(name)                               \
extern const std::string IntrinsicNameHwtHlsFp##name;             \
llvm::CallInst* CreateHwtHlsFp##name(__CreateHwtHlsFpUnOpParams);  \
bool IsHwtHlsFp##name(const llvm::CallInst *C);                     \
bool IsHwtHlsFp##name(const llvm::Function *F);

__DefineHwtHlsFpUnOp(FNeg)
// common arithmetic binary operators
__DefineHwtHlsFpBinOp(FAdd)
__DefineHwtHlsFpBinOp(FSub)
__DefineHwtHlsFpBinOp(FMul)
__DefineHwtHlsFpBinOp(FDiv)
__DefineHwtHlsFpBinOp(FRem)
__DefineHwtHlsFpBinOp(FMod)
__DefineHwtHlsFpBinOp(Atan2)

// cmp operators
extern const std::string IntrinsicNameHwtHlsFpFCmp;
llvm::CallInst* CreateHwtHlsFpFCmp(llvm::IRBuilderBase &Builder,
		llvm::CmpInst::Predicate predicate, llvm::Value *op0, llvm::Value *op1,
		const HFloatTmpConfig &cfg, const llvm::Twine &Name = "");
bool IsHwtHlsFpFCmp(const llvm::CallInst *C);
bool IsHwtHlsFpFCmp(const llvm::Function *F);

__DefineHwtHlsFpUnOp(Ceil)
__DefineHwtHlsFpUnOp(Cos)
__DefineHwtHlsFpUnOp(Exp)
__DefineHwtHlsFpUnOp(Exp10)
__DefineHwtHlsFpUnOp(Exp2)
__DefineHwtHlsFpUnOp(FAbs)
__DefineHwtHlsFpUnOp(Floor)
__DefineHwtHlsFpUnOp(Log)
__DefineHwtHlsFpUnOp(Log10)
__DefineHwtHlsFpUnOp(Log2)
__DefineHwtHlsFpBinOp(FPow)
__DefineHwtHlsFpBinOp(FPowi)
__DefineHwtHlsFpUnOp(Round)
__DefineHwtHlsFpUnOp(Roundeven)
__DefineHwtHlsFpUnOp(Sin)
__DefineHwtHlsFpUnOp(Sqrt)

__DefineHwtHlsFpUnOp(Sinpi)
__DefineHwtHlsFpUnOp(Cospi)
__DefineHwtHlsFpUnOp(Asin)
__DefineHwtHlsFpUnOp(Sinh)
__DefineHwtHlsFpUnOp(Acos)
__DefineHwtHlsFpUnOp(Cosh)
__DefineHwtHlsFpUnOp(Tan)
__DefineHwtHlsFpUnOp(Tanpi)
__DefineHwtHlsFpUnOp(Atan)
__DefineHwtHlsFpUnOp(Tanh)

// hwtHls specific
__DefineHwtHlsFpBinOp(Shl)
__DefineHwtHlsFpBinOp(Shr)

#undef __CreateHwtHlsFpUnOpParams
#undef __CreateHwtHlsFpBinOpParams
#undef __DefineHwtHlsFpBinOp
#undef __DefineHwtHlsFpUnOp

}

namespace llvm {
inline llvm::raw_ostream &operator<<(llvm::raw_ostream &OS, const hwtHls::HFloatTmpConfig& cfg) {
	cfg.print(OS);
	return OS;
}
}
