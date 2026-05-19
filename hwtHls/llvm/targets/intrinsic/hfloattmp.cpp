#include <cmath>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <llvm/IR/Module.h>
#include <llvm/ADT/StringExtras.h>
#include <llvm/CodeGen/MachineInstr.h>

#include <hwtHls/llvm/targets/intrinsic/utils.h>
#include <hwtHls/llvm/bitMath.h>

#include <math.h>
#include <stdexcept>

using namespace llvm;

namespace hwtHls {

HFloatTmpConfig::HFloatTmpConfig(bool isInQFormat, //
		std::uint8_t exponentOrIntWidth,  //
		std::uint8_t mantissaOrFracWidth, //
		bool supportSubnormal,            //
		bool hasSign, bool hasIsNaN, bool hasIsInf, //
		bool hasIs1, bool hasIs0,                   //
		HFloatTmpRounding rounding, HFloatTmpSaturation saturation) : //
		isInQFormat(isInQFormat), //
		exponentOrIntWidth(exponentOrIntWidth), //
		mantissaOrFracWidth(mantissaOrFracWidth), //
		supportSubnormal(supportSubnormal), //
		hasSign(hasSign), hasIsNaN(hasIsNaN), hasIsInf(hasIsInf), //
		hasIs1(hasIs1), hasIs0(hasIs0), //
		rounding(rounding), saturation(saturation) {
	assert(isInQFormat == true || isInQFormat == false);
	if (isInQFormat)
		assert(
				!supportSubnormal
						&& "supportSubnormal is only relevant for floating point representation (not Q fixed point)");

}

bool HFloatTmpConfig::operator==(const HFloatTmpConfig &other) const {
	assert(MEMBER_CNT == 11);
	return //
	isInQFormat == other.isInQFormat && //
			exponentOrIntWidth == other.exponentOrIntWidth && //
			mantissaOrFracWidth == other.mantissaOrFracWidth && //
			supportSubnormal == other.supportSubnormal && //
			hasSign == other.hasSign && //
			hasIsNaN == other.hasIsNaN && //
			hasIsInf == other.hasIsInf && //
			hasIs1 == other.hasIs1 && //
			hasIs0 == other.hasIs0 && //
			rounding == other.rounding && //
			saturation == other.saturation;
}

size_t HFloatTmpConfig::__hash__() const {
	llvm::SmallVector<unsigned, 9> Bits;
	Bits.push_back(isInQFormat);
	Bits.push_back(exponentOrIntWidth);
	Bits.push_back(mantissaOrFracWidth);
	Bits.push_back(supportSubnormal);
	Bits.push_back(hasSign);
	Bits.push_back(hasIsNaN);
	Bits.push_back(hasIsInf);
	Bits.push_back(hasIs1);
	Bits.push_back(hasIs0);
	Bits.push_back(rounding);
	Bits.push_back(saturation);

	return llvm::hash_combine_range(Bits.begin(), Bits.end());
}

uint64_t HFloatTmpConfig::_mantissaToFixedPointQWithRounding(bool sign,
		uint64_t mantissa, int exponent, size_t numWidth,
		size_t CUR_MANTISA_WIDTH) const {
	assert(numWidth > 0);
	// shift mantissa on proper position
	mantissa |= 1ul << CUR_MANTISA_WIDTH; // set first 1 which was omitted in FP mantissa format

	int fracWidth = CUR_MANTISA_WIDTH;
	int requiredFracWidth = mantissaOrFracWidth;
	int rshiftAmountToAliginFrac = fracWidth - requiredFracWidth;
	int rshiftAmount = rshiftAmountToAliginFrac - exponent;
	bool addOneFlag = false;
	if (rshiftAmount == 0) {
	} else if (rshiftAmount < 0) {
		uint64_t lsb =  mantissa & 0b1;
		mantissa <<= -rshiftAmount;
		// copy lsb when there is more bits in fraction
		if (lsb) {
			mantissa |= mask<uint64_t>(-rshiftAmount);
		}
	} else if (rshiftAmount >= 64) {
		mantissa = 0; // set explicitly because shiftamount of >> operator has modulo applied
	} else {
		bool round_bit = (mantissa >> (rshiftAmount - 1)) & 1; // most significant removed bit
		if (rounding == HFloatTmpRounding::ROUND_HALF_EVEN) {
			// nearest with ties going to nearest even integer. (c default)
			// if round_bit && newLsb: x += 1; trunc(x)
			bool newLsb = (mantissa >> rshiftAmount) & 1;
			addOneFlag = round_bit & newLsb;
		} else if (rounding == HFloatTmpRounding::ROUND_HALF_UP) {
			//  nearest with ties going away from 0.
			// if round_bit && x > 0: x += 1; trunc(x)
			addOneFlag = round_bit & !sign;
		} else if (rounding == HFloatTmpRounding::ROUND_DOWN) {
			//  towards 0.
			// if round_bit && x < 0: x += 1; trunc(x)
			addOneFlag = round_bit & sign;
		} else if (rounding == HFloatTmpRounding::ROUND_CEILING) {
			// towards inf.
			// if round_bit: x += 1; trunc(x)
			addOneFlag = round_bit;
		} else if (rounding == HFloatTmpRounding::ROUND_FLOOR) {
			addOneFlag = false;
		} else {
			llvm_unreachable("Unsupported rounding type");
		}

		mantissa >>= rshiftAmount;
	}
	if (addOneFlag)
		mantissa += 1;
	if (mantissa > mask<uint64_t>(numWidth))
		throw HFloatTmpConversionError(
				"precision loss during conversions (msb bits are lost) ");
	return mantissa;
}


/**
 * Convert unsigned int to negative int which has same bits set (emulate sign overflow).
 *
 * :note: bits in value are not changed, just the C++ int object
 *        has signed flag set properly. And the number is in the expected range.
 */
template<typename T>
T to_signed(T val, int width) {
	if (val > 0) {
		T msb = static_cast<T>(1) << (width - 1); // most significant bit (MSB) mask
		if (val & msb) {  // check if MSB is set
			val -= mask<T>(width) + 1; // subtract mask value to emulate signed overflow
		}
	}
	return val;
}

// Convert signed integer to unsigned integer
template<typename T>
T to_unsigned(T val, int width) {
	if (val < 0) {
		return val & mask<T>(width); // apply mask to simulate unsigned behavior
	} else {
		return val;  // return as-is if the value is non-negative
	}
}

double HFloatTmpConfig::fixp_resize_double_representing_Q(double x, bool isSigned,
                   size_t inIntWidth, size_t inFracWidth,
                   size_t outIntWidth, size_t outFracWidth,
                   HFloatTmpRounding roundingMode,
                   HFloatTmpSaturation saturationMode)  {
	if (inIntWidth + inFracWidth > 64) {
		throw std::runtime_error(
			"NotImplemented: HFloatTmpConfig::fixp_resize_double_representing_Q in >64b "
			"value");
	}
	if (outIntWidth + outFracWidth > 64) {
		throw std::runtime_error(
			"NotImplemented: HFloatTmpConfig::fixp_resize_double_representing_Q out >64b "
			"value");
	}
   // :see: :func:`fixp_resize`
				   
    // Convert to internal scaled integer (assuming values fit in 64-bit)
    // We use std::ldexp to avoid multiplication overhead and ensure precision.
    // This represents the raw fixed-point bits.
    double scaled = std::ldexp(x, static_cast<int>(inFracWidth));
    
    // Adjust for change in fractional width
    int fracSizeDiff = static_cast<int>(outFracWidth) - static_cast<int>(inFracWidth);
    double target = std::ldexp(scaled, fracSizeDiff);

    // Rounding: Perform on the 'target' double before integer cast
    // This maintains the bit-precision relative to the Q-format definition.
    int64_t roundedValue;
    switch(roundingMode) {
        case HFloatTmpRounding::ROUND_HALF_EVEN:
            roundedValue = static_cast<int64_t>(std::nearbyint(target));
            break;
        case HFloatTmpRounding::ROUND_HALF_UP:
            roundedValue = static_cast<int64_t>(std::round(target));
            break;
        case HFloatTmpRounding::ROUND_FLOOR:
            roundedValue = static_cast<int64_t>(std::floor(target));
            break;
        case HFloatTmpRounding::ROUND_CEILING:
            roundedValue = static_cast<int64_t>(std::ceil(target));
            break;
        case HFloatTmpRounding::ROUND_DOWN:
            roundedValue = static_cast<int64_t>(std::trunc(target)); // Truncation
            break;
        default: throw std::runtime_error("Unsupported rounding");
    }

    // Saturation logic on the integer representation
    // Calculate bounds based on target bit widths
    int64_t minVal = isSigned ? -(1LL << (outIntWidth + outFracWidth - 1)) : 0;
    int64_t maxVal = (1LL << (outIntWidth + outFracWidth - (isSigned ? 1 : 0))) - 1;

    if (saturationMode == HFloatTmpSaturation::SATURATE_INF) {
		if (std::isinf(x)) {
			roundedValue = x < 0 ? minVal: maxVal;
		} else if (std::isnan(x)) {
			std::runtime_error("Can not represent NaN on ");
		}
        roundedValue = std::max(minVal, std::min(roundedValue, maxVal));
    } else if (saturationMode == HFloatTmpSaturation::SATURATE_NONE) {
        // Masking logic for bit-truncation (emulates hardware overflow)
		uint64_t vMask = (1ULL << (outIntWidth + outFracWidth)) - 1;
        uint64_t mask = (outIntWidth + outFracWidth >= 64) ? ~0ULL : vMask;
        uint64_t raw = static_cast<uint64_t>(roundedValue) & mask;
		uint64_t outMsb = 1ULL << (outIntWidth + outFracWidth - 1);
        if (isSigned && (raw & outMsb)) {
            // Sign extend if negative
            roundedValue = static_cast<int64_t>(raw | ~mask);
        } else {
            roundedValue = static_cast<int64_t>(raw);
        }
    }

    // Convert back to double scaling by output fractional width
    return std::ldexp(static_cast<double>(roundedValue), -static_cast<int>(outFracWidth));
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
	APInt vAsAPInt;
	if (isInQFormat) {
		auto vRounded = fixp_resize_double_representing_Q(vAsDouble, fpCfg.hasSign, C_DOUBLE_MANTISA_W,
				C_DOUBLE_EXPONENT_W, exponentOrIntWidth,
				mantissaOrFracWidth, rounding, saturation);
		vAsAPInt = APFloat(vRounded).bitcastToAPInt();
	} else  {
		// [todo] round float
		vAsAPInt = v.bitcastToAPInt();
	}
	// bool issubnormal_ = issubnormal(vAsDouble);
	size_t CUR_MANTISA_W = C_DOUBLE_MANTISA_W;
	size_t CUR_EXP_W = C_DOUBLE_EXPONENT_W;

	uint64_t mantissa = vAsAPInt.extractBits(CUR_MANTISA_W, 0).getZExtValue();
	uint64_t _exponent =
			vAsAPInt.extractBits(CUR_EXP_W, CUR_MANTISA_W).getZExtValue();
	int exponent = ((int) _exponent) + -mask<unsigned>(CUR_EXP_W - 1); // exponent in unbiassed format
	uint64_t sign =
			vAsAPInt.extractBits(1, CUR_EXP_W + CUR_MANTISA_W).getZExtValue();
	size_t offset = 0;
	bool isInf = isinf(vAsDouble);
	// resolve mantissa/exponent or int and frac part if it is in Q format
	if (fpCfg.isInQFormat) {
		// Q:  (MSB) is0? is1? isInf? isNaN? sign? intPart fractPart (lsb)
		const size_t numWidth = fpCfg.exponentOrIntWidth
				+ fpCfg.mantissaOrFracWidth;
		if (isnan(vAsDouble) || vAsDouble == 0.0
				|| (issubnormal(vAsDouble) && !fpCfg.supportSubnormal)) {
			// keep all bits 0
			offset += numWidth;
			if (isnan(vAsDouble) && !fpCfg.hasIsNaN)
				throw HFloatTmpConversionError(
						"double value is NaN but the target type does no support NaN");

		} else if (isinf(vAsDouble)) {
			if (!fpCfg.hasIsInf)
				throw HFloatTmpConversionError(
						"double value is Inf but the target type does no support Inf");
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
			mantissa = _mantissaToFixedPointQWithRounding(sign, mantissa,
					exponent, numWidth, CUR_MANTISA_W);
			res |= mantissa & mask<uint64_t>(numWidth);
			if (fpCfg.hasSign) {
				if (vAsDouble < 0.0) {
					auto res_n = -res.extractBits(numWidth, 0);
					if (res_n.getSExtValue()
							!= (int64_t) -(mantissa & mask<uint64_t>(numWidth)))
						throw HFloatTmpConversionError(
								"precision loss during conversions (overflow during application of sign)");
					res = (-res.extractBits(numWidth, 0)).zext(
							res.getBitWidth()); //  because there may be flags before msb
				} else {
					if (mantissa > mask<uint64_t>(numWidth - 1))
						throw HFloatTmpConversionError(
								"precision loss during conversions (unsigned value too large to fit into signed format)");
				}
			} else {
				if (vAsDouble < 0.0 && vAsDouble != -0.0) {
					throw HFloatTmpConversionError(
							"negative number constant for unsigned type");
				}
			}
			offset += numWidth;
		}
	} else {
		// FP: (MSB) is0? is1? isInf? isNaN? sign? exponent mantissa (LSB)
		size_t newMantisaW = fpCfg.mantissaOrFracWidth;
		int newExpOffset = -mask<unsigned>(fpCfg.exponentOrIntWidth - 1);
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
			exponent = 0;
		} else if (_exponent == mask<uint64_t>(CUR_EXP_W)) {
			// exponent == all 1
			if (mantissa == 0) {
				// inf case
			} else {
				// nan case
				// mantissa = mask<uint64_t>(newMantisaW);
				mantissa = 1ul << (newMantisaW - 1);
			}
			exponent = mask<unsigned>(fpCfg.exponentOrIntWidth);
		} else {
			size_t shiftedOutBits = 0;
			if (CUR_MANTISA_W > newMantisaW) {
				// need to shift mantissa and update exponent
				auto shAmount = CUR_MANTISA_W - newMantisaW;
				shiftedOutBits |= (mantissa & mask<uint64_t>(shAmount))
						<< (64 - shAmount);
				mantissa >>= shAmount;
			}
			int newExpMin = newExpOffset;
			int newExpMax = -newExpOffset + 1;
			if (exponent < newExpMin) {
				// may become 0 or subnormal
				size_t shAmount = -exponent - -newExpMin;
				shiftedOutBits >>= shAmount;
				shiftedOutBits |= (mantissa & mask<uint64_t>(shAmount))
						<< (64 - shAmount);
				if (shiftedOutBits != 0 && fpCfg.supportSubnormal) {
					llvm_unreachable(
							"NotImplemented: convert fp constant which become subnormal to a fp type of a different width");
				}
			} else if (exponent > newExpMax) {
				// become +-inf
				isInf = true;
				exponent = newExpMin - 1;
				mantissa = 0;
			}
			exponent = (exponent + -newExpOffset) & mask<uint64_t>(fpCfg.exponentOrIntWidth);
		}
		res.insertBits(mantissa, offset, fpCfg.mantissaOrFracWidth);
		offset += fpCfg.mantissaOrFracWidth;

		res.insertBits(exponent, offset, fpCfg.exponentOrIntWidth);
		offset += fpCfg.exponentOrIntWidth;
		// fill sign and other special flags
		if (fpCfg.hasSign) {
			if (sign) {
				res.setBit(offset);
			}
			offset += 1;
		} else {
			if (!sign)
				throw std::runtime_error(
						"Can not convert negative float constant to unsigned float type");
		}
	}

	// set  (MSB) is0? is1? isInf? isNaN? ... (lsb)
	if (fpCfg.hasIsNaN) {
		if (isnan(vAsDouble)) {
			res.setBit(offset);
		}
		offset += 1;
	}
	// else {
	// 	assert(
	// 			!(fpCfg.isInQFormat && isnan(vAsDouble))
	// 					&& "Can not convert NaN constant to q formated number without isNaN flag");
	// }
	if (fpCfg.hasIsInf) {
		if (isInf) {
			res.setBit(offset);
		}
		offset += 1;
	} else {
		assert(
				!(fpCfg.isInQFormat && isInf)
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

llvm::APFloat HFloatTmpConfig::bitCastHFloatTmpAPIntToAPFloat(
		const llvm::APInt &v) const {
	const HFloatTmpConfig &fpCfg = *this;
	APFloat res = llvm::APFloat(0.0);

	size_t offset = 0;
	int64_t exponent = 0;
	uint64_t integerPart = 0, fractionalPart = 0, mantissa = 0;
	bool sign = false, isInf = false, isNaN = false, isZero = false, isOne =
			false;
	auto popFlag = [&offset, &v](bool condition, bool &flagValue) {
		// pop a single bit from "v" if condition is met
		if (condition) {
			if (v.extractBits(1, offset).getZExtValue()) {
				flagValue = true;
			}
			offset += 1;
		}
	};
	if (fpCfg.isInQFormat) {
		// Handle special cases for Q format
		if (v.isZero()) {
			// Check for zero case (all bits are zero)
			isZero = true;
		} else {
			auto numPart = v.extractBits(
					fpCfg.mantissaOrFracWidth + fpCfg.exponentOrIntWidth,
					offset);
			offset += fpCfg.mantissaOrFracWidth + fpCfg.exponentOrIntWidth;
			if (fpCfg.hasSign) {
				sign = numPart.isNegative();
				if (sign) {
					numPart = -numPart;
				}
			}
			fractionalPart =
					numPart.extractBits(fpCfg.mantissaOrFracWidth, 0).getZExtValue();
			integerPart = numPart.extractBits(fpCfg.exponentOrIntWidth,
					fpCfg.mantissaOrFracWidth).getZExtValue();

			// Handling special cases based on Q format values
			// Zero and Inf case for Q format (non-exponent based)
			if (integerPart == 0 && fractionalPart == 0) {
				isZero = true;
			} else if (integerPart == 1 && fractionalPart == 0) {
				isOne = true;
			}
		}
	} else {
		// Handle FP format
		mantissa =
				v.extractBits(fpCfg.mantissaOrFracWidth, offset).getZExtValue();
		offset += fpCfg.mantissaOrFracWidth;

		exponent =
				v.extractBits(fpCfg.exponentOrIntWidth, offset).getZExtValue();
		offset += fpCfg.exponentOrIntWidth;

		popFlag(fpCfg.hasSign, sign);

		if (exponent == 0) {
			if (mantissa == 0) {
				isZero = true;
			} else {
				exponent = 1;  // Subnormal handling
				mantissa |= (1 << fpCfg.mantissaOrFracWidth);
			}
		} else if ((uint64_t) exponent
				== mask<uint64_t>(fpCfg.exponentOrIntWidth)) {
			// special values
			if (mantissa == 0) {
				isInf = true;
			} else {
				isNaN = true;
			}
		} else {
			mantissa |= (1ul << fpCfg.mantissaOrFracWidth);
		}
		exponent -= mask<uint64_t>(fpCfg.exponentOrIntWidth - 1)
				+ fpCfg.mantissaOrFracWidth; // apply offset for exponent
	}
	// set  (MSB) is0? is1? isInf? isNaN? ... (lsb)

	popFlag(fpCfg.hasIsNaN, isNaN);
	popFlag(fpCfg.hasIsInf, isInf);
	popFlag(fpCfg.hasIs1, isOne);
	popFlag(fpCfg.hasIs0, isZero);

	// Construct the result based on special cases or regular values
	if (isZero) {
		res = APFloat(0.0);
	} else if (isOne) {
		res = APFloat(1.0);
	} else if (isInf) {
		res = APFloat(std::numeric_limits<double>::infinity());
	} else if (isNaN) {
		res = APFloat(std::numeric_limits<double>::quiet_NaN());
	} else {
		double value;
		if (fpCfg.isInQFormat) {
			value = static_cast<double>(integerPart)
					+ static_cast<double>(fractionalPart)
							/ (1ull << fpCfg.mantissaOrFracWidth);

		} else {
			value = static_cast<double>(mantissa) * std::pow(2.0, exponent);
		}
		res = APFloat(value);
	}
	if (sign)
		res = -res;

	return res;
}

static uint64_t extractConstIntFromArg(User::op_iterator &A,
									   User::op_iterator AEnd) {
	if (A == AEnd) {
		throw std::runtime_error(
			"HFloatTmpConfig: not enough operands to extract HFloatTmpConfig");
	}
	auto c = dyn_cast<ConstantInt>(A->get());
	A++;
	if (!c)
		throw std::runtime_error(
			"HFloatTmpConfig: Arguments specifying HFloatTmpConfig members "
			"should be only constant integers");
	return c->getZExtValue();
}

HFloatTmpConfig HFloatTmpConfig::fromCallArgs(llvm::CallInst &CI,
		size_t argsToSkip) {
	auto A = CI.arg_begin();
	auto AEnd = CI.arg_end();
	for (size_t i = 0; i < argsToSkip; i++) {
		assert(A != AEnd);
		A++;
	}

	assert(HFloatTmpConfig::MEMBER_CNT == 11);
	auto isInQFormat = extractConstIntFromArg(A, AEnd);
	auto exponentOrIntWidth = extractConstIntFromArg(A, AEnd);
	auto mantissaOrFracWidth = extractConstIntFromArg(A, AEnd);
	auto supportSubnormal = extractConstIntFromArg(A, AEnd);
	auto hasSign = extractConstIntFromArg(A, AEnd);
	auto hasIsNaN = extractConstIntFromArg(A, AEnd);
	auto hasIsInf = extractConstIntFromArg(A, AEnd);
	auto hasIs1 = extractConstIntFromArg(A, AEnd);
	auto hasIs0 = extractConstIntFromArg(A, AEnd);
	auto rounding = HFloatTmpRounding(extractConstIntFromArg(A, AEnd));
	auto saturation = HFloatTmpSaturation(extractConstIntFromArg(A, AEnd));

	HFloatTmpConfig res(isInQFormat, exponentOrIntWidth, mantissaOrFracWidth,
			supportSubnormal, hasSign, hasIsNaN, hasIsInf, hasIs1, hasIs0,
			rounding, saturation);
	return res;
}

HFloatTmpConfig HFloatTmpConfig::fromMachineInstrOperands(
		llvm::MachineInstr &MI, size_t operandOffset) {
	assert(HFloatTmpConfig::MEMBER_CNT == 11);
	assert(
			MI.getNumExplicitOperands()
					>= operandOffset + HFloatTmpConfig::MEMBER_CNT + 1); // + for enCondition
	auto isInQFormat = MI.getOperand(operandOffset++).getImm();
	auto exponentOrIntWidth = MI.getOperand(operandOffset++).getImm();
	auto mantissaOrFracWidth = MI.getOperand(operandOffset++).getImm();
	auto supportSubnormal = MI.getOperand(operandOffset++).getImm();
	auto hasSign = MI.getOperand(operandOffset++).getImm();
	auto hasIsNaN = MI.getOperand(operandOffset++).getImm();
	auto hasIsInf = MI.getOperand(operandOffset++).getImm();
	auto hasIs1 = MI.getOperand(operandOffset++).getImm();
	auto hasIs0 = MI.getOperand(operandOffset++).getImm();
	auto rounding = HFloatTmpRounding(MI.getOperand(operandOffset++).getImm());
	auto saturation = HFloatTmpSaturation(
			MI.getOperand(operandOffset++).getImm());

	HFloatTmpConfig res(isInQFormat, exponentOrIntWidth, mantissaOrFracWidth,
			supportSubnormal, hasSign, hasIsNaN, hasIsInf, hasIs1, hasIs0,
			rounding, saturation);
	return res;
}

void HFloatTmpConfig::print(llvm::raw_ostream &ss, bool IsForDebug) const {
	ss << "<HFloatTmpConfig";
	if (isInQFormat) {
		ss << " format=Q" << (unsigned) exponentOrIntWidth << "."
				<< (unsigned) mantissaOrFracWidth;
	} else {
		ss << " format=FP" << (unsigned) exponentOrIntWidth << "_"
				<< (unsigned) mantissaOrFracWidth;
	}
	if (supportSubnormal)
		ss << ", supportSubnormal";
	if (hasSign)
		ss << ", hasSign";
	if (hasIsNaN)
		ss << ", hasIsNaN";
	if (hasIsInf)
		ss << ", hasIsInf";
	if (hasIs1)
		ss << ", hasIs1";
	if (hasIs0)
		ss << ", hasIs0";
	ss << ">";
}

#define HFloatTmpConfig_ARGS_TO_LLVM(Builder, cfg) \
	Builder.getInt1(cfg.isInQFormat),            \
	Builder.getInt8(cfg.exponentOrIntWidth),     \
	Builder.getInt8(cfg.mantissaOrFracWidth),    \
	Builder.getInt1(cfg.supportSubnormal),       \
	Builder.getInt1(cfg.hasSign),                \
	Builder.getInt1(cfg.hasIsNaN),               \
	Builder.getInt1(cfg.hasIsInf),               \
	Builder.getInt1(cfg.hasIs1),                 \
	Builder.getInt1(cfg.hasIs0),                 \
    Builder.getInt8(cfg.rounding),               \
    Builder.getInt8(cfg.saturation)              \

const std::string CastToHFloatTmpName = "hwtHls.fp.castToHFloatTmp";

#define HFloatTmpConfig_OP_ARG_TYPES(off, Ops)\
	Ops[(off)+0]->getType()/*isInQFormat*/, \
	Ops[(off)+1]->getType()/*exponentOrIntWidth*/, \
	Ops[(off)+2]->getType()/*mantissaOrFracWidth*/, \
	Ops[(off)+3]->getType()/*supportSubnormal*/,\
	Ops[(off)+4]->getType()/*hasSign*/, Ops[(off)+5]->getType()/*hasIsNaN*/,\
	Ops[(off)+6]->getType()/*hasIsInf*/, Ops[(off)+7]->getType()/*hasIs1*/,\
	Ops[(off)+8]->getType()/*hasIs0*/, Ops[(off)+9]->getType()/*rounding*/, \
	Ops[(off)+10]->getType()/*saturation*/

llvm::CallInst* CreateCastToHFloatTmp(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &cfg,
		const llvm::Twine &Name) {
	assert(srcArg->getType()->isIntegerTy());
	assert(srcArg->getType()->getIntegerBitWidth() == cfg.getBitWidth());

	Value *Ops[] = { srcArg, HFloatTmpConfig_ARGS_TO_LLVM(Builder, cfg) };
	Type *ResT = Builder.getDoubleTy();
	Type *TysForName[] = { Ops[0]->getType() };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							Intrinsic_getName(CastToHFloatTmpName, TysForName),
							ResT, Ops[0]->getType(),
							HFloatTmpConfig_OP_ARG_TYPES(1, Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;

}
bool IsCastToHFloatTmp(const llvm::CallInst *C) {
	return IsCastToHFloatTmp(C->getCalledFunction());
}
bool IsCastToHFloatTmp(const llvm::Function *F) {
	assert(F);
	return F->getName().str().rfind(CastToHFloatTmpName + ".", 0) == 0;
}

llvm::CallInst* _CreateCastHFloatTmp(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &cfg, Type *ResT,
		const llvm::Twine &Name, const std::string FnName) {
	assert(srcArg->getType()->isDoubleTy());
	Value *Ops[] = { srcArg, HFloatTmpConfig_ARGS_TO_LLVM(Builder, cfg) };
	Type *TysForName[] = { ResT };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							Intrinsic_getName(FnName, TysForName), ResT,
							Ops[0]->getType(),
							HFloatTmpConfig_OP_ARG_TYPES(1, Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}
const std::string CastFromHFloatTmpName = "hwtHls.fp.castFromHFloatTmp";

llvm::CallInst* CreateCastFromHFloatTmp(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &cfg,
		const llvm::Twine &Name) {
	Type *ResT = Builder.getIntNTy(cfg.getBitWidth());
	return _CreateCastHFloatTmp(Builder, srcArg, cfg, ResT, Name,
			CastFromHFloatTmpName);
}
bool IsCastFromHFloatTmp(const llvm::CallInst *C) {
	return IsCastFromHFloatTmp(C->getCalledFunction());
}
bool IsCastFromHFloatTmp(const llvm::Function *F) {
	assert(F);
	return F->getName().str().rfind(CastFromHFloatTmpName + ".", 0) == 0;
}

const std::string CastHFloatTmpToHFloatTmpName =
		"hwtHls.fp.castHFloatTmpToHFloatTmp";

llvm::CallInst* CreateCastHFloatTmpToHFloatTmp(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &cfg,
		const llvm::Twine &Name) {
	return _CreateCastHFloatTmp(Builder, srcArg, cfg, Builder.getDoubleTy(),
			Name, CastHFloatTmpToHFloatTmpName);
}
bool IsCastHFloatTmpToHFloatTmp(const llvm::CallInst *C) {
	return IsCastHFloatTmpToHFloatTmp(C->getCalledFunction());
}
bool IsCastHFloatTmpToHFloatTmp(const llvm::Function *F) {
	assert(F);
	return F->getName().str().rfind(CastHFloatTmpToHFloatTmpName + ".", 0) == 0;
}

const std::string CastHFloatTmpToHFloatTmpRawName =
		"hwtHls.fp.castHFloatTmpToHFloatTmpRaw";
llvm::CallInst* CreateCastHFloatTmpToHFloatTmpRaw(llvm::IRBuilderBase &Builder,
		llvm::Value *srcArg, const HFloatTmpConfig &srcCfg,
		const HFloatTmpConfig &dstCfg, const llvm::Twine &Name) {
	assert(srcArg->getType()->isIntegerTy());
	Value *Ops[] = { srcArg,                               //
			HFloatTmpConfig_ARGS_TO_LLVM(Builder, srcCfg), //
			HFloatTmpConfig_ARGS_TO_LLVM(Builder, dstCfg)  //
			};

	Type *ResT = Builder.getIntNTy(dstCfg.getBitWidth());
	Type *TysForName[] = { srcArg->getType(), ResT };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(CastHFloatTmpToHFloatTmpRawName,
							TysForName), ResT, Ops[0]->getType(),
					HFloatTmpConfig_OP_ARG_TYPES(1, Ops),
					HFloatTmpConfig_OP_ARG_TYPES(
							1 + HFloatTmpConfig::MEMBER_CNT, Ops) //
					).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}
bool IsCastHFloatTmpToHFloatTmpRaw(const llvm::CallInst *C) {
	return IsCastHFloatTmpToHFloatTmpRaw(C->getCalledFunction());
}
bool IsCastHFloatTmpToHFloatTmpRaw(const llvm::Function *F) {
	return F->getName().str().rfind(CastHFloatTmpToHFloatTmpRawName + ".", 0)
			== 0;
}

bool IsHwtHlsFp(const llvm::CallInst *C) {
	return IsHwtHlsFp(C->getCalledFunction());
}
bool IsHwtHlsFp(const llvm::Function *F) {
	assert(F);
	return F->getName().str().rfind("hwtHls.fp.", 0) == 0;
}

llvm::CallInst* CreateHwtHlsFpUnspecializedBinOp(llvm::IRBuilderBase &Builder,
		const std::string &intrinsicFnName, llvm::Value *op0, llvm::Value *op1,
		const llvm::Twine &Name) {
	assert(op0->getType()->isFloatingPointTy());
	assert(op1->getType()->isIntegerTy());

	Value *Ops[] = { op0, op1 };
	Type *ResT = op0->getType();
	Type *TysForName[] = { ResT };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(intrinsicFnName, TysForName), ResT,
					Ops[0]->getType(), Ops[1]->getType()).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

llvm::CallInst* CreateHwtHlsFUnOp(llvm::IRBuilderBase &Builder,
		const std::string &intrinsicFnName, llvm::Value *op0,
		const HFloatTmpConfig &cfg, const llvm::Twine &Name) {
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType()->getIntegerBitWidth() == cfg.getBitWidth());

	Value *Ops[] = { op0, HFloatTmpConfig_ARGS_TO_LLVM(Builder, cfg) };
	Type *ResT = Builder.getIntNTy(cfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	Function *TheFn =
			cast<Function>(
					M->getOrInsertFunction(
							Intrinsic_getName(intrinsicFnName, TysForName),
							ResT, Ops[0]->getType(),
							HFloatTmpConfig_OP_ARG_TYPES(1, Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

llvm::CallInst* CreateHwtHlsFBinOp(llvm::IRBuilderBase &Builder,
		const std::string &intrinsicFnName, llvm::Value *op0, llvm::Value *op1,
		const HFloatTmpConfig &cfg, const llvm::Twine &Name,
		bool opsMustHaveSameType = true) {
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType()->getIntegerBitWidth() == cfg.getBitWidth());
	assert(!opsMustHaveSameType || op0->getType() == op1->getType());

	Value *Ops[] = { op0, op1, HFloatTmpConfig_ARGS_TO_LLVM(Builder, cfg) };
	Type *ResT = Builder.getIntNTy(cfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(intrinsicFnName, TysForName), ResT,
					Ops[0]->getType(), Ops[1]->getType(),
					HFloatTmpConfig_OP_ARG_TYPES(2, Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

llvm::CallInst* CreateHwtHlsFBinOpDifferentTypeOps(llvm::IRBuilderBase &Builder,
		const std::string &intrinsicFnName, llvm::Value *op0, llvm::Value *op1,
		const HFloatTmpConfig &cfg, const llvm::Twine &Name) {
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType()->getIntegerBitWidth() == cfg.getBitWidth());

	Value *Ops[] = { op0, op1, HFloatTmpConfig_ARGS_TO_LLVM(Builder, cfg) };
	Type *ResT = Builder.getIntNTy(cfg.getBitWidth());
	Type *TysForName[] = { ResT };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	Function *TheFn = cast<Function>(
			M->getOrInsertFunction(
					Intrinsic_getName(intrinsicFnName, TysForName), ResT,
					Ops[0]->getType(), Ops[1]->getType(),
					HFloatTmpConfig_OP_ARG_TYPES(2, Ops)).getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

// macros for definition of unary an binary operator functions and name variable

//#define CONCAT_(prefix, suffix) prefix##suffix
/// Concatenate `prefix, suffix` into `prefixsuffix`
//#define CONCAT(prefix, suffix) CONCAT_(prefix, suffix)

#define DEFINE_FP_IS_FN(name, intrinsicName) \
const std::string IntrinsicNameHwtHlsFp##name = "hwtHls.fp." #intrinsicName;    \
bool IsHwtHlsFp##name(const llvm::CallInst *C) {                                         \
	return IsHwtHlsFp##name(C->getCalledFunction());                                     \
}                                                                                        \
bool IsHwtHlsFp##name(const llvm::Function *F) {                                         \
	assert(F);                                                                           \
	return F->getName().str().rfind(IntrinsicNameHwtHlsFp##name + ".", 0) == 0;          \
}

#define DEFINE_FP_UNSPECIALIZED_BINOP(name, intrinsicName)                               \
DEFINE_FP_IS_FN(name, intrinsicName)                                                     \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilderBase& Builder, llvm::Value *op0,     \
		llvm::Value *op1, const llvm::Twine &Name) {                                     \
	return CreateHwtHlsFpUnspecializedBinOp(Builder, IntrinsicNameHwtHlsFp##name,        \
			op0, op1, Name);                                                             \
}

#define DEFINE_FP_BINOP(name, intrinsicName)                                             \
DEFINE_FP_IS_FN(name, intrinsicName)                                                     \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilderBase& Builder, llvm::Value *op0,     \
		llvm::Value *op1, const HFloatTmpConfig & cfg, const llvm::Twine &Name) {        \
	return CreateHwtHlsFBinOp(Builder, IntrinsicNameHwtHlsFp##name, op0, op1,   \
			cfg, Name);                                                                  \
}

#define DEFINE_FP_UNOP(name, intrinsicName)                                              \
DEFINE_FP_IS_FN(name, intrinsicName)                                                     \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilderBase& Builder, llvm::Value *op0,     \
		const HFloatTmpConfig & cfg, const llvm::Twine &Name) {                          \
	return CreateHwtHlsFUnOp(Builder, IntrinsicNameHwtHlsFp##name, op0,                  \
			cfg, Name);                                                                  \
}

#define DEFINE_FP_BINOP_RHS_INT(name, intrinsicName)                                     \
DEFINE_FP_IS_FN(name, intrinsicName)                                                     \
llvm::CallInst* CreateHwtHlsFp##name(llvm::IRBuilderBase& Builder, llvm::Value *op0,     \
		llvm::Value *op1, const HFloatTmpConfig & cfg, const llvm::Twine &Name) {        \
	return CreateHwtHlsFBinOp(Builder, IntrinsicNameHwtHlsFp##name, op0, op1,            \
			cfg, Name, false);                                                           \
}

DEFINE_FP_UNSPECIALIZED_BINOP(UnspecializedShl, unspecialized.shl)
DEFINE_FP_UNSPECIALIZED_BINOP(UnspecializedShr, unspecialized.shr)

DEFINE_FP_UNOP(FNeg, fneg)
DEFINE_FP_BINOP(FAdd, fadd)
DEFINE_FP_BINOP(FSub, fsub) // :note: for floating point types a-b should lowered to a+(-b)
DEFINE_FP_BINOP(FMul, fmul)
DEFINE_FP_BINOP(FDiv, fdiv)
DEFINE_FP_BINOP(FRem, frem)
DEFINE_FP_BINOP(FMod, fmod)
DEFINE_FP_BINOP(Atan2, atan2)

const std::string IntrinsicNameHwtHlsFpFCmp = "hwtHls.fp.fcmp";
llvm::CallInst* CreateHwtHlsFpFCmp(llvm::IRBuilderBase &Builder,
		llvm::CmpInst::Predicate predicate, llvm::Value *op0, llvm::Value *op1,
		const HFloatTmpConfig &cfg, const llvm::Twine &Name) {
	assert(op0->getType()->isIntegerTy());
	assert(op0->getType()->getIntegerBitWidth() == cfg.getBitWidth());
	assert(op0->getType() == op1->getType());

	Value *Ops[] = { Builder.getInt8(predicate), op0, op1,
			HFloatTmpConfig_ARGS_TO_LLVM(Builder, cfg) };
	Type *ResT = Builder.getIntNTy(1);
	Type *TysForName[] = { op0->getType() };
	Module *M = Builder.GetInsertBlock()->getParent()->getParent();
	std::string name = (Intrinsic_getName(IntrinsicNameHwtHlsFpFCmp, TysForName)
			+ "." + llvm::CmpInst::getPredicateName(predicate));
	auto F = M->getOrInsertFunction(name, ResT,    //
			Ops[0]->getType(), Ops[1]->getType(), Ops[2]->getType(), //
			HFloatTmpConfig_OP_ARG_TYPES(3, Ops)  //
			);
	Function *TheFn = cast<Function>(F.getCallee());
	AddDefaultFunctionAttributes(*TheFn);
	CallInst *CI = Builder.CreateCall(TheFn, Ops);
	CI->setDoesNotAccessMemory();
	CI->setName(Name);
	return CI;
}

bool IsHwtHlsFpFCmp(const llvm::CallInst *C) {
	return IsHwtHlsFpFCmp(C->getCalledFunction());
}
bool IsHwtHlsFpFCmp(const llvm::Function *F) {
	return F->getName().str().rfind(IntrinsicNameHwtHlsFpFCmp + ".", 0) == 0;
}
DEFINE_FP_UNOP(Ceil, ceil)
DEFINE_FP_UNOP(Cos, cos)
DEFINE_FP_UNOP(Exp, exp)
DEFINE_FP_UNOP(Exp10, exp10)
DEFINE_FP_UNOP(Exp2, exp2)
DEFINE_FP_UNOP(FAbs, fabs)
DEFINE_FP_UNOP(Floor, floor)
DEFINE_FP_UNOP(Log, log)
DEFINE_FP_UNOP(Log10, log10)
DEFINE_FP_UNOP(Log2, log2)
DEFINE_FP_BINOP(FPow, fpow)
DEFINE_FP_BINOP_RHS_INT(FPowi, fpowi)
DEFINE_FP_UNOP(Round, round)
DEFINE_FP_UNOP(Roundeven, roundeven)
DEFINE_FP_UNOP(Sin, sin)
DEFINE_FP_UNOP(Sqrt, sqrt)

DEFINE_FP_UNOP(Sinpi, sinpi)
DEFINE_FP_UNOP(Cospi, cospi)
DEFINE_FP_UNOP(Asin, asin)
DEFINE_FP_UNOP(Sinh, sinh)
DEFINE_FP_UNOP(Acos, acos)
DEFINE_FP_UNOP(Cosh, cosh)
DEFINE_FP_UNOP(Tan, tan)
DEFINE_FP_UNOP(Tanpi, tanpi)
DEFINE_FP_UNOP(Atan, atan)
DEFINE_FP_UNOP(Tanh, tanh)

// hwtHlsSpecific
DEFINE_FP_BINOP_RHS_INT(Shl, shl)
DEFINE_FP_BINOP_RHS_INT(Shr, shr)

}
