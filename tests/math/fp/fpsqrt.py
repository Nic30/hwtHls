
from hwt.code import Concat
from hwt.hdl.commonConstants import b1, b0
from hwt.mainBases import RtlSignalBase
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.fp.normalizeDenormalize import fpRoundup, fpNormalize, \
    fpUnpack, fpPack, fpRound
from tests.math.hFloatTmp.hFloatTmpOps import sqrt
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.fixp.fixpSqrt import fixpSqrt
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwtHls.code import ashr
# NR https://github.com/akilm/FPU-IEEE-754

# @hlsBytecode
# def IEEE754FpSqrt(a: RtlSignalBase[IEEE754Fp]):
#    """
#    Based on https://github.com/dawsonjon/verilog-math/blob/master/ip_generator/float.py#L30
#
#    :note: for nth root there of positive number there is a formula
#        for any logarithm base b
#
#    .. code-block ::
#        n * log_b r = log_b x
#        r =~= b^((1/n) * log_b x)
#
#    """
#    # add a bit to e so that we can test for overflow
#    m_bits = a._dtype.MANTISSA_WIDTH
#    a_e = a.exponent
#    a_m = a.m
#    a_s = a.s
#    a_inf = a.isInf()
#    a_nan = a.isNaN()
#
#    a_m, a_e = fpNormalize(a_m, m_bits, a_e)
#    a_m = zext(a_m, m_bits * 2 + 3)
#
#    # if a_e is not even, re-scale e and m
#    odd = a_e[0]
#    if odd:
#        a_e -= 1
#        a_m <<= 1
#
#    # pre-multiply m so that we get the useful bits, add 1 bit for rounding
#    a_m = a_m << (m_bits + 1)
#    _z_m = PyBytecodeInline(sqrt)(a_m)
#    _z_m = _z_m[m_bits: 0]
#    z_s = a_s
#
#    # sqrt of 2^e == s^(e//2)
#    z_e = lshr(a_e, 1)  # exponent in biased format thats why lshr and not ashr
#
#    e_bits = a._dtype.EXPONENT_WIDTH
#    # handle underflow
#    shift_amount = Constant(z_e.bits, e_min) - z_e
#    if shift_amount[z_e.bits - 1]:
#        # do not shift if shift_amount < 0
#        shift_amount = 0
#    _z_m >>= shift_amount
#    z_e += shift_amount
#
#    # normalize
#    _z_m, z_e, g, _, _ = fpNormalize(_z_m, m_bits, z_e)
#    z_m = _z_m[m_bits: 1]
#    z_m, z_e = fpRoundup(z_m, z_e, g, 1, 0)
#
#    z_e = z_e[e_bits - 1: 0]
#    z_inf = a_inf
#    z_nan = a_nan | (a_s & (z_m != 0))
#
#    return Float(z_s, z_e, z_m, z_inf, z_nan, e_bits, m_bits)
# A Low-Cost High Radix Floating-Point Square-Root Circuit https://doi.org/10.3390/electronics10161988


def isExponentOdd(exponentBiassed: AnyHBitsValue) -> AnyHBitsValue:
    # :note: other implementations usually perform this check on unbiassed form,
    #        we perform it there on biassed
    exponenIsEven = exponentBiassed[0]
    return ~exponenIsEven


def exponentBiasedDiv2(t:IEEE754Fp, exp: AnyHBitsValue):
    biasU = t.EXPONENT_OFFSET_U
    expTy = exp._dtype.from_py
    W = t.EXPONENT_WIDTH
    tmp_0 = exp._zext(W + 1) + (expTy(biasU)._sext(W + 1) - (expTy(biasU)._sext(W + 1) << 1))
    tmp_1 = ashr(tmp_0, 1)
    o = tmp_1._trunc(W)
    return o


def _IEEE754FpSqrt_getInternSqrtTy(t: IEEE754Fp) -> HFixedPointQ:
    # 4 + (0 if t.MANTISSA_WIDTH % 2 == 0 else 1)
    # mantisaT.bit_length() - 2
    # int_bit_length=2 because that is the minimum for fixpSqrt
    # frac_bit_length +3 for guard, round, sticky and optinal +1 to have even number of frac bits for fixpSqrt
    mantisaFixPTy = HFixedPointQ(2, t.MANTISSA_WIDTH + 3 + (1 if t.MANTISSA_WIDTH % 2 == 0 else 0),
                                 signed=False,
                                 rounding=HFloatTmpRounding.ROUND_FLOOR,
                                 saturation=HFloatTmpSaturation.SATURATE_NONE)
    return mantisaFixPTy


@hlsBytecode
def IEEE754FpSqrt(a: RtlSignalBase[IEEE754Fp], loopPragmaGetter=lambda: None):
    """
    IEEE754 Floating Point Square Root.
    Based on https://github.com/dawsonjon/verilog-math/blob/master/ip_generator/float.py#L30
             https://github.com/Desrep/simple_fpu/blob/main/fp_sqr.v 
    """
    t: IEEE754Fp = a._dtype
    res = t.from_py(None)

    # Handle NaN and Infinity cases
    if a.sign | a.isNaN() | a.isInf() | a.isZero():
        PyBytecodeBlockLabel("IEEE754FpSqrt.isNaNInfZero")
        # sqrt(0.0) = 0.0
        # sqrt(-0.0) = -0.0
        # sqrt(inf) = inf
        # sqrt(NaN) = NaN
        res.sign = b0
        res.exponent = a.exponent
        res.mantissa = a.mantissa
        if a.sign & ~a.isZero():
            # sqrt(-0.1) = NaN
            # sqrt(-inf) = NaN
            res.exponent = t.getSpecialExponentHw()
            res.mantissa = t.getNaNMantisaHw()
    else:
        # https://doi.org/10.1007/s10773-022-05222-7
        # Sr = Sa
        # if Ea.isOdd():
        #     IEr1 = Ea + 1
        #     IEr = IEr1/2
        #     Align Mantissa
        # else:
        #     IEr = Ea/2
        # Er = IEr + Bias
        # Mr = sqrt(Ma)

        # Normalize the operand
        PyBytecodeBlockLabel("IEEE754FpSqrt.denormalize")
        # :note: exponent is in the biased form
        mantisaFixPTy = _IEEE754FpSqrt_getInternSqrtTy(t)
        # :note: aMantissa is in Q1.x and will be Q2.x (mantissaIntExtended)
        aMantissa, aExponent = fpUnpack(a, mantisaWidthIncrease=mantisaFixPTy.frac_bit_length - t.MANTISSA_WIDTH, expWidthIncrease=0)

        mantissaIntExtended = Concat(b0, aMantissa)
        if isExponentOdd(aExponent):
            # multiply mantissa by 2
            aExponent -= 1  # no underflow
            mantissaIntExtended <<= 1

        PyBytecodeBlockLabel("IEEE754FpSqrt.sqrt")
        # Perform square root on mantissa on more than the twice the width

        # aMantissaAsFixp = aMantissa._reinterpret_cast(mantisaFixPTy)
        # sqrtAsFixp = sqrt(aMantissaAsFixp._explicit_cast(HFloatTmp))._explicit_cast(mantisaFixPTy)
        # sqrtAsInt = sqrtAsFixp._reinterpret_cast(mantisaT)

        sqrtAsInt = PyBytecodeInline(fixpSqrt)(mantissaIntExtended, loopPragmaGetter=loopPragmaGetter, t=mantisaFixPTy)

        # zMantissa1 = Concat(sqrtAsInt[t.MANTISSA_WIDTH + 1:], b0)

        # Calculate the exponent for the square root operation (half the exponent)
        # sqrt(n**e) == n**(0.5*e)
        zExponent = exponentBiasedDiv2(t, aExponent)

        # # Handle underflow (shift exponent and mantissa accordingly)
        # # [todo] this is probably useless as zExponent can not became more negative by dividing
        # if zExponent > t.e_min:
        #    # do not shift if shift_amount < 0
        #    shiftAmount = zExponent._dtype.from_py(t.e_min) - zExponent
        #    zMantissa1 >>= shiftAmount
        #    zExponent += shiftAmount
        #
        #    shiftAmount = shiftAmount._dtype.from_py(0)

        # PyBytecodeBlockLabel("IEEE754FpSqrt.finalNormalize")
        # hidden, mantissa (M), guard, round, sticky tail

        zMantissa2, zExponent, guard_bit, round_bit, sticky_bit = fpNormalize(sqrtAsInt, t.MANTISSA_WIDTH, zExponent, msbKnonwToBe1=True)
        W = zMantissa2._dtype.bit_length()
        # take top bits because [1,2) -> (1, sqrt(2)) approx [1, 1.414)
        # -1 because we added extra int bit to have even int bitwidth
        zMantissa3 = sqrtAsInt[W - 1: W - (t.MANTISSA_WIDTH + 1) - 1]

        # :note: already normalized
        # Perform rounding
        # guard_bit = zMantissa2[0]
        # round_bit = b1
        # sticky_bit = b0
        # zMantissa3 = zMantissa2[t.MANTISSA_WIDTH:1]
        PyBytecodeBlockLabel("IEEE754FpSqrt.finalRound")
        zMantissa4, zExponent = fpRound(t, a.sign, zExponent, zMantissa3, guard_bit, round_bit, sticky_bit)

        res.sign = b0
        res.exponent = zExponent
        res.mantissa = zMantissa4[t.MANTISSA_WIDTH:]  # cut off hidden MSB 1

        # PyBytecodeInline(fpPack)(zExponent[t.EXPONENT_WIDTH:], zMantissa4, res)

    return res


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators
    from tests.math.componentGenerators._genericHwModules import _FpAlu1HwModule
    from tests.math.fp.fptypes import IEEE754Fp16, IEEE754Fp64
    m = _FpAlu1HwModule()
    m.T = IEEE754Fp64
    m.FN = IEEE754FpSqrt

    m.CLK_FREQ = int(70e6)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                              # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          ]
                          )
    installMathLibComponentGenerators(platform)
    print(to_rtl_str(m, target_platform=platform))
    # debug()
