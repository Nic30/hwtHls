

import struct

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtLib.types.ctypes import uint16_t, uint32_t, uint64_t
from pyMathBitPrecise.bit_utils import mask, ValidityError, get_bit_range


class IEEE754Fp(HStruct):
    """
    IEEE-754 s special meanings
    
    Meaning             Sign Field   Exponent Field    Mantissa Field
    Zero                Don't care   All 0s            All 0s
    Positive subnormal  0            All 0s            Non-zero
    Negative subnormal  1            All 0s            Non-zero
    Positive Infinity   0            All 1s            All 0s
    Negative Infinity   1            All 1s            All 0s
    Not a Number(NaN)   Don't care   All 1s            Non-zero
    
    :note: subnormal and denormal is synonym.

    Exponent is biased. For fp32 it has an offset of -127. All 1s represent the highest value, 0 the lowest.
    If the exponent is 0, then:
        * the leading bit becomes 0
        * the exponent is fixed to -126 (not -127 as if we didn't have this exception)
    """

    def __init__(self, exponentWidth, mantissaWidth, name=None, const=False):
        self.EXPONENT_WIDTH = exponentWidth
        self.MANTISSA_WIDTH = mantissaWidth
        self.EXPONENT_OFFSET = -mask(exponentWidth - 1)
        HStruct.__init__(self,
            # mantissa on lowest bits sign on MSB
            (Bits(mantissaWidth, signed=False), "mantissa"),
            (Bits(exponentWidth, signed=False), "exponent"),  # biased with EXPONENT_OFFSET
            (BIT, "sign"),
            name=name,
            const=const,
        )

    def fromPyInt(self, v: int):
        if self == IEEE754Fp16:
            vecT = uint16_t
        elif self == IEEE754Fp32:
            vecT = uint32_t
        elif self == IEEE754Fp64:
            vecT = uint64_t
        else:
            raise NotImplementedError()
        hVal = vecT.from_py(v)
        return hVal._reinterpret_cast(self)

    def from_py(self, v, vld_mask=None):
        if isinstance(v, float):
            if self != IEEE754Fp64:
                raise NotImplementedError(self, "not implemented rounding when converting from python float to a float of a different size")
            v = int.from_bytes(struct.pack("d", v), byteorder='little')
            v = {
                "mantissa": get_bit_range(v, 0, self.MANTISSA_WIDTH),
                "exponent": get_bit_range(v, self.MANTISSA_WIDTH, self.EXPONENT_WIDTH),
                "sign": get_bit_range(v, self.MANTISSA_WIDTH + self.EXPONENT_WIDTH, 1),
            }

        return HStruct.from_py(self, v, vld_mask)

    def to_py(self, v: HValue["IEEE754Fp"]) -> float:
        self = v._dtype
        if self == IEEE754Fp16:
            vecT = uint16_t
            unpackChar = 'e'
        elif self == IEEE754Fp32:
            vecT = uint32_t
            unpackChar = 'f'
        elif self == IEEE754Fp64:
            vecT = uint64_t
            unpackChar = 'd'
        else:
            raise NotImplementedError(self)
        try:
            pyVal = int(v._reinterpret_cast(vecT))
        except ValidityError:
            return None
        return struct.unpack(unpackChar, pyVal.to_bytes(vecT.bit_length() // 8, byteorder='little'))[0]

    @staticmethod
    @hlsBytecode
    def isSpecial(v: RtlSignalBase["IEEE754Fp"]):
        expAll1 = mask(v._dtype.EXPONENT_WIDTH)
        return v.exponent._eq(expAll1)

    @classmethod
    @hlsBytecode
    def isNaN(cls, v: RtlSignalBase["IEEE754Fp"]):
        return cls.isSpecial(v) & cls.hasNaNMantissa(v)

    @classmethod
    @hlsBytecode
    def isInf(cls, v: RtlSignalBase["IEEE754Fp"]):
        return cls.isSpecial(v) & cls.hasInfMantissa(v)

    @classmethod
    @hlsBytecode
    def isZero(cls, v: RtlSignalBase["IEEE754Fp"]):
        return v.exponent._eq(0) & v.mantissa._eq(0)

    @classmethod
    @hlsBytecode
    def isSubnormal(cls, v: RtlSignalBase["IEEE754Fp"]):
        return v.exponent._eq(0) & v.mantissa != 0

    @classmethod
    @hlsBytecode
    def hasInfMantissa(cls, v: RtlSignalBase["IEEE754Fp"]):
        return v.mantissa._eq(0)

    @classmethod
    @hlsBytecode
    def hasNaNMantissa(cls, v: RtlSignalBase["IEEE754Fp"]):
        return v.mantissa != 0

    @hlsBytecode
    def getSpecialExponent(self):
        return mask(self.EXPONENT_WIDTH)

    @hlsBytecode
    def getNaNMantisa(self):
        return 1 << (self.MANTISSA_WIDTH - 1)


# standard IEEE754 floating point number types
IEEE754Fp16 = IEEE754Fp(5, 10, name="float16")
IEEE754Fp32 = IEEE754Fp(8, 23, name="float32")
IEEE754Fp64 = IEEE754Fp(11, 52, name="float64")

# other commonly used floating point number types
TF32 = IEEE754Fp(8, 10, name="TF32") # NVidia's TensorFloat32 (19 bits)
BF16 = IEEE754Fp(8, 10, name="BF16") # BFLOAT16
fp24 = IEEE754Fp(7, 16, name="fp24") # AMD's fp24 format
PXR24 = IEEE754Fp(8, 15, name="PXR24") # Pixar's PXR24 format
sfp_3_3 = IEEE754Fp(3, 3, name="sfp_3_3") # Xilinx Small Floating Point<3,3>: https://xilinx.eetrend.com/files/2021-06/wen_zhang_/100113810-209893-wp530-small-floating-point.pdf
