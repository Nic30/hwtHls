from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll


@hlsBytecode
def divNonRestoring(dividend: RtlSignal, divisor: RtlSignal, isSigned: RtlSignal, unrollFactor: int):
    """
    Non-restoring integer division, dividend/divisor = quotient + remainder

    based on https://github.com/ultraembedded/riscv/blob/master/core/riscv/riscv_divider.v
    """
    assert dividend._dtype == divisor._dtype
    t = dividend._dtype
    width = t.bit_length()
    assert unrollFactor > 0 and unrollFactor <= width

    invertQuotient = isSigned & (dividend[width - 1] != divisor[width - 1]) & (divisor != 0)
    invertRemainder = isSigned & dividend[width - 1]

    if isSigned & (dividend[width - 1]):
        dividend = -dividend
    
    if isSigned & (divisor[width - 1]):
        divisor = -divisor

    zeroPad = HBits(width - 1).from_py(0)
    quotient = t.from_py(0)
    divisorTmp = Concat(divisor, zeroPad)
    qMask = t.from_py(1 << (width - 1))

    while qMask != 0:
        if divisorTmp <= Concat(zeroPad, dividend):
            dividend -= divisorTmp[width:]
            quotient |= qMask
    
        divisorTmp >>= 1
        qMask >>= 1
        PyBytecodeLLVMLoopUnroll(unrollFactor > 1, unrollFactor)

    if invertQuotient:
        quotient = -quotient

    remainder = dividend
    if invertRemainder:
        remainder = -remainder

    return (quotient, remainder)
