# modulo by const https://electronics.stackexchange.com/questions/608840/verilog-modulus-operator-for-non-power-of-two-synthetizable

from hwt.mainBases import RtlSignalBase
from hwtHls.frontend.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel, \
    PyBytecodeInline
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from hwtHls.frontend.pyBytecode import hlsBytecode
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.fp.normalizeDenormalize import fpUnpack, fpNormalize, \
    fpPack, fpRound, exponentBiassedToUnbiassed, exponentUnbiassedToBiassed
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from hwt.hdl.commonConstants import b1


# https://github.com/akilm/FPU-IEEE-754/blob/main/srcs/sources/FloatingDivision.v
# https://github.com/nishthaparashar/Floating-Point-ALU-in-Verilog/tree/master/Division
# https://github.com/taneroksuz/fpu-sp/blob/main/verilog/src/float/fp_fdiv.sv
def _IEEE754FpDiv_getInternDivTy(t: IEEE754Fp) -> HFixedPointQ:
    mantisaFixPTy = HFixedPointQ(1, t.MANTISSA_WIDTH + 3, signed=False,
                                    rounding=HFloatTmpRounding.ROUND_FLOOR,
                                    saturation=HFloatTmpSaturation.SATURATE_NONE)
    return mantisaFixPTy


@hlsBytecode
def IEEE754FpDiv(a: RtlSignalBase[IEEE754Fp],
                 b: RtlSignalBase[IEEE754Fp]):
    """
    based on https://github.com/dawsonjon/verilog-math/blob/master/ip_generator/float.py#L78
             https://github.com/dawsonjon/fpu/blob/master/divider/divider.v
    """
    t: IEEE754Fp = a._dtype
    toMantissaT = a.mantissa._dtype.from_py
    toExponentT = a.exponent._dtype.from_py
    res = t.from_py(None)
    if a.isNaN() | b.isNaN() | (a.isSpecial() & b.isSpecial()):
        PyBytecodeBlockLabel("IEEE754FpDiv.isNaN")
        # if a is NaN or b is NaN return NaN
        res.sign = a.sign ^ b.sign
        res.exponent = t.getSpecialExponentHw()
        res.mantissa = t.getNaNMantisaHw()

    elif a.isInf():
        PyBytecodeBlockLabel("IEEE754FpDiv.aIsInf")

        # if b is zero return NaN
        res.exponent = t.getSpecialExponentHw()
        if b.isZero():
            # if b is zero return NaN
            res.sign = b1
            res.mantissa = t.getNaNMantisaHw()
        else:
            # if a is inf return inf
            res.sign = a.sign ^ b.sign
            res.mantissa = toMantissaT(0)

    elif b.isInf():
        PyBytecodeBlockLabel("IEEE754FpDiv.bIsInf")
        res.exponent = t.getSpecialExponentHw()
        if a.isZero():
            # if a is zero return NaN
            res.sign = b1
            res.mantissa = t.getNaNMantisaHw()
        else:
            # if b is inf return 0
            res.sign = a.sign ^ b.sign
            res.exponent = toExponentT(0)
            res.mantissa = toMantissaT(0)

    elif b.isZero():
        # if a or b is zero return zero
        PyBytecodeBlockLabel("IEEE754FpDiv.bIs0")
        # return 0.0
        res.sign = a.sign ^ b.sign
        res.exponent = toExponentT(0)
        res.mantissa = toMantissaT(0)

    else:
        PyBytecodeBlockLabel("IEEE754FpDiv.compute")
        aMantissa, aExponent = fpUnpack(a, mantisaWidthIncrease=3, expWidthIncrease=2)
        bMantissa, bExponent = fpUnpack(b, mantisaWidthIncrease=3, expWidthIncrease=2)

        # Divide mantissas and adjust the exponent
        PyBytecodeBlockLabel("IEEE754FpDiv.divide_0")
        # substract in biassed form
        aExpUnbiased = exponentBiassedToUnbiassed(t, aExponent)
        bExpUnbiased = exponentBiassedToUnbiassed(t, bExponent)
        resExponent = aExpUnbiased - bExpUnbiased
        curLeftShift = resExponent._dtype.from_py(0)
        if resExponent > -t.EXPONENT_OFFSET:
            # it means that the result exponent
            # will be 0 because there is an underflow
            # and the number will become subnormal.
            # The mantissa has to be shifted to compensate for exp underflow.
            resExponent = 0
            curLeftShift = bExpUnbiased - aExpUnbiased

        mantisaT = aMantissa._dtype
        mantisaFixPTy = _IEEE754FpDiv_getInternDivTy(t)
        aMantisaAsFixp = aMantissa._reinterpret_cast(mantisaFixPTy)._explicit_cast(HFloatTmp)
        bMantisaAsFixp = bMantissa._reinterpret_cast(mantisaFixPTy)._explicit_cast(HFloatTmp)
        # :note: [1, 2) / [1, 2) -> (0.5, 2) # RHS is checked to  not be 0.0
        quotientFixp = aMantisaAsFixp / bMantisaAsFixp
        quotient = quotientFixp._explicit_cast(mantisaFixPTy)._reinterpret_cast(mantisaT)

        resExpBiased = exponentUnbiassedToBiassed(t, resExponent)
        mantissa0, exponetTmp, guard_bit, round_bit, sticky_bit = fpNormalize(
            quotient, t.MANTISSA_WIDTH, resExpBiased, curLeftShift=curLeftShift._vec())
        PyBytecodeNoSplitSlices(mantissa0)
        mantissa1 = mantissa0[:3]  # top MANTISSA_WIDTH bits except MSB (which is 1)

        PyBytecodeBlockLabel("IEEE754FpDiv.round")
        res.sign = a.sign ^ b.sign
        mantissaRounded, exponetTmp = fpRound(
            t,
            res.sign,
            exponetTmp,
            mantissa1,
            guard_bit, round_bit, sticky_bit)

        PyBytecodeInline(fpPack)(exponetTmp, mantissaRounded, res)

    return res


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators
    from tests.math.componentGenerators._genericHwModules import _FpAlu2HwModule
    from tests.math.fp.fptypes import IEEE754Fp16
    m = _FpAlu2HwModule()
    m.T = IEEE754Fp16
    m.FN = IEEE754FpDiv

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
