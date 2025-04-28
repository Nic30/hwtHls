from typing import Callable

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragma import _PyBytecodeLoopPragma
from hwtHls.frontend.pyBytecode.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeBlockLabel, \
    PyBytecodeInline


@hlsBytecode
def _divCastToUnsigned(dividend: RtlSignal, divisor: RtlSignal, isSigned: RtlSignal):
    """
    An utility function which cast signed operands to unsigned before division
    before division algorithm is for unsigned only.
    It also computes invertQuotient and invertRemainder which
    should be used to correct result if inputs were signed.
    """
    PyBytecodeBlockLabel("_divCastToUnsigned")
    width = dividend._dtype.bit_length()

    invertQuotient = isSigned & (dividend[width - 1] != divisor[width - 1]) & (divisor != 0)
    invertRemainder = isSigned & dividend[width - 1]

    if isSigned & dividend[width - 1]:
        dividend = -dividend

    if isSigned & divisor[width - 1]:
        divisor = -divisor

    return dividend, divisor, invertQuotient, invertRemainder


@hlsBytecode
def divRestoring(dividend: RtlSignal, divisor: RtlSignal, isSigned: RtlSignal,
                    loopPragmaGetter: Callable[[], _PyBytecodeLoopPragma]=lambda: None,
                    dbgNoSplitSlices:bool=True):
    """
    Restoring integer division, quotient = dividend // divisor, remainder = dividend%divisor 

    :param dbgSplitSlices: debug option which controls SplitSlices pass
        (which does not improve anything but triggers many other optimizations)

    based on https://github.com/ultraembedded/riscv/blob/master/core/riscv/riscv_divider.v
    https://en.wikipedia.org/wiki/Division_algorithm
    """
    assert dividend._dtype == divisor._dtype
    t = dividend._dtype
    width = t.bit_length()

    dividend, divisor, invertQuotient, invertRemainder = PyBytecodeInline(_divCastToUnsigned)(dividend, divisor, isSigned)

    zeroPad = HBits(width - 1).from_py(0)
    quotient = t.from_py(0)
    divisorTmp = Concat(divisor, zeroPad)
    qMask = t.from_py(1 << (width - 1))
    if dbgNoSplitSlices:
        PyBytecodeNoSplitSlices(divisorTmp)

    while qMask != 0:
        PyBytecodeBlockLabel("divRestoring.divLoop")
        if divisorTmp <= Concat(zeroPad, dividend):
            dividend -= divisorTmp[width:]
            quotient |= qMask

        if dbgNoSplitSlices:
            PyBytecodeNoSplitSlices(qMask)
            PyBytecodeNoSplitSlices(divisorTmp)
            PyBytecodeNoSplitSlices(quotient)

        divisorTmp >>= 1
        qMask >>= 1
        loopPragmaGetter()

    PyBytecodeBlockLabel("divRestoring.signFinalize")
    if invertQuotient:
        quotient = -quotient

    remainder = dividend
    if invertRemainder:
        remainder = -remainder

    PyBytecodeBlockLabel("divRestoring.return")
    return (quotient, remainder)
