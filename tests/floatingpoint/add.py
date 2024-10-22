from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase
from hwt.math import log2ceil
from hwt.synthesizer.vectorUtils import fitTo
from hwtHls.code import getMsb, lshr, ctlz, hwUMin, shl
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodePreprocHwCopy, \
    PyBytecodeInline, PyBytecodeBlockLabel
from tests.floatingpoint.fptypes import IEEE754Fp
from tests.math.fp.normalizeDenormalize import _denormalize, fpRoundup, \
    fpPack


@PyBytecodeInline
def _swap(aSign, aExponent, aMantissa, bSign, bExponent, bMantissa):
    copy = PyBytecodePreprocHwCopy
    _aSign = copy(aSign)
    _aExponent = copy(aExponent)
    _aMantissa = copy(aMantissa)
    aSign = bSign
    aExponent = bExponent
    aMantissa = bMantissa
    bSign = _aSign
    bExponent = _aExponent
    bMantissa = _aMantissa
    return aSign, aExponent, aMantissa, bSign, bExponent, bMantissa


@hlsBytecode
def IEEE754FpAdd(a: RtlSignalBase[IEEE754Fp], b: RtlSignalBase[IEEE754Fp], isSim=False):
    """
    based on https://github.com/dawsonjon/fpu/blob/master/adder/adder.v
    https://github.com/ucb-bar/berkeley-softfloat-3
    https://users.encs.concordia.ca/~asim/COEN_6501/Lecture_Notes/L4_Slides.pdf
    https://doi.org/10.1049/iet-cdt.2016.0200
    https://github.com/OpenXiangShan/fudian/blob/main/src/main/scala/fudian/FADD.scala
    https://github.com/stskeeps/HyCC/blob/master/examples/float32/float32.h#L115
    """
    t: IEEE754Fp = a._dtype
    res = t.from_py(None)
    if t.isNaN(a) | t.isNaN(b):
        PyBytecodeBlockLabel("IEEE754FpAdd.isNaN")
        # if a is NaN or b is NaN return NaN
        res.sign = a.sign & b.sign
        res.exponent = t.getSpecialExponent()
        res.mantissa = t.getNaNMantisa()

    elif t.isInf(a):
        # if a is inf return inf
        PyBytecodeBlockLabel("IEEE754FpAdd.aIsInf")
        res.sign = a.sign
        res.exponent = t.getSpecialExponent()
        res.mantissa = 0
        if t.isInf(b) & (a.sign != b.sign):
            res.mantissa = t.getNaNMantisa()

    elif t.isInf(b):
        PyBytecodeBlockLabel("IEEE754FpAdd.bIsInf")
        # if b is inf return inf
        res.sign = b.sign
        res.exponent = t.getSpecialExponent()
        res.mantissa = 0

    elif t.isZero(a) & t.isZero(b):
        PyBytecodeBlockLabel("IEEE754FpAdd.Is0")
        res.sign = a.sign & b.sign
        res.exponent = 0
        res.mantissa = 0

    elif t.isZero(a):
        PyBytecodeBlockLabel("IEEE754FpAdd.aIs0")
        res = b

    elif t.isZero(b):
        PyBytecodeBlockLabel("IEEE754FpAdd.bIs0")
        res = a

    else:
        PyBytecodeBlockLabel("IEEE754FpAdd.compute")

        # :note: mantissa +4 bits, still in biased form
        aMantissa, aExponent = _denormalize(a)
        aSign = a.sign
        bMantissa, bExponent = _denormalize(b)
        bSign = b.sign

        if aExponent < bExponent:
            PyBytecodeBlockLabel("IEEE754FpAdd.expSwap")
            # swap to have number with larger exponent in a to avoid dual shifting logic
            if isSim:

                def copy(x):
                    return x

            else:
                copy = PyBytecodePreprocHwCopy

            aSign, aExponent, aMantissa, \
            bSign, bExponent, bMantissa = \
                copy(bSign), copy(bExponent), copy(bMantissa), \
                copy(aSign), copy(aExponent), copy(aMantissa)

        requiredShift = aExponent - bExponent
        del bExponent  # no longer  required
        if requiredShift < t.MANTISSA_WIDTH:
            PyBytecodeBlockLabel("IEEE754FpAdd.scale")
            # perform shit of b to scale it to the same exponent as a
            # accumulate all shifted out bits t bit0
            # (original align)
            bMantissaTmp = Concat(bMantissa, HBits(t.MANTISSA_WIDTH - 1).from_py(0))
            bMantissaTmp = lshr(bMantissaTmp, requiredShift[log2ceil(bMantissaTmp._dtype.bit_length() + 1):])
            PyBytecodeNoSplitSlices(bMantissaTmp)
            bMantissa = Concat(bMantissaTmp[:t.MANTISSA_WIDTH], bMantissaTmp[t.MANTISSA_WIDTH:] != 0)
            del requiredShift
            del bMantissaTmp

            # perform mantissa add
            # (add_0)
            sumTmp = HBits(aMantissa._dtype.bit_length() + 1).from_py(None)
            res.sign = aSign

            aMantissaTmp = Concat(BIT.from_py(0), aMantissa)
            bMantissaTmp = Concat(BIT.from_py(0), bMantissa)

            if aSign._eq(bSign):
                sumTmp = aMantissaTmp + bMantissaTmp
            elif aMantissa < bMantissa:
                sumTmp = bMantissaTmp - aMantissaTmp
                res.sign = bSign
            else:
                sumTmp = aMantissaTmp - bMantissaTmp

            PyBytecodeBlockLabel("IEEE754FpAdd.add_1")
            del aMantissa
            del bMantissa

            # (original add_1)
            mantissaTmp = HBits(t.MANTISSA_WIDTH + 1).from_py(None)
            exponetTmp = aExponent
            if getMsb(sumTmp):
                mantissaTmp = sumTmp[:4]
                guard_bit = sumTmp[3]
                round_bit = sumTmp[2]
                sticky_bit = sumTmp[1] | sumTmp[0]
                exponetTmp += 1
            else:
                # ! must be in sumTmp[msb-1]
                sumWidth = sumTmp._dtype.bit_length()
                mantissaTmp = sumTmp[sumWidth - 1:3]
                guard_bit = sumTmp[2]
                round_bit = sumTmp[1]
                sticky_bit = sumTmp[0]

            PyBytecodeBlockLabel("IEEE754FpAdd.normalize_1")
            # normalize
            # (original normalise_1)
            # shift mantissaTmp that there is 1 in MSB, if exponent allows it
            leadingZeroCnt = ctlz(mantissaTmp)
            PyBytecodeNoSplitSlices(leadingZeroCnt)
            shAmount = hwUMin(fitTo(leadingZeroCnt._unsigned(), exponetTmp), exponetTmp)
            _shAmount = shAmount[log2ceil(mantissaTmp._dtype.bit_length() + 1):]
            mantissaTmp = shl(Concat(mantissaTmp[:1], guard_bit), _shAmount)
            PyBytecodeNoSplitSlices(mantissaTmp)
            exponetTmp -= shAmount
            round_bit &= shAmount._eq(0)
            # while ~getMsb(mantissaTmp) & (exponetTmp > 1):
            #    exponetTmp -= 1
            #    mantissaTmp = Concat(mantissaTmp[:1], guard_bit)
            #    round_bit = round_bit._dtype.from_py(0)

            PyBytecodeBlockLabel("IEEE754FpAdd.normalize_2")
            # (original normalise_2)
            if exponetTmp._eq(0):
                # zero and subnormals
                exponetTmp += 1
                exponetTmp = exponetTmp._dtype.from_py(1)
                mantissaTmp >>= 1
                guard_bit = mantissaTmp[0]
                sticky_bit |= round_bit

            PyBytecodeBlockLabel("IEEE754FpAdd.round")
            # round (original round)
            mantissaTmp, exponetTmp = fpRoundup(t, exponetTmp, mantissaTmp, guard_bit, round_bit, sticky_bit)

            PyBytecodeBlockLabel("IEEE754FpAdd.pack")
            # handle overflows
            # (original pack)
            PyBytecodeInline(fpPack)(exponetTmp, mantissaTmp, res)
        else:
            PyBytecodeBlockLabel("IEEE754FpAdd.tooSmall")
            # other number is too small to affect result value
            res.sign = aSign
            res.exponent = aExponent[t.EXPONENT_WIDTH:]
            res.mantissa = aMantissa[t.MANTISSA_WIDTH + 3:3]

    return res
