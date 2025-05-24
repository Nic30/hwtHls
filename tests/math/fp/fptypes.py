

import struct
from typing import Optional, Self

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer, internal
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase, HStructRtlSignalBase
from hwt.hdl.types.typeCast import toHVal
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpRounding, HFloatTmpSaturation
from hwtLib.types.ctypes import uint16_t, uint32_t, uint64_t
from pyMathBitPrecise.bit_utils import mask, ValidityError, get_bit_range, \
    to_unsigned
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import fadd, fsub, fmul, fdiv


class IEEE754FpValue():
    """
    Common methods for IEEE754Fp and RtlSignal
    """

    @hwt_expr_producer
    def isSpecial(self):
        expAll1 = mask(self._dtype.EXPONENT_WIDTH)
        return self.exponent._eq(expAll1)

    @hwt_expr_producer
    def isNaN(self):
        return self.isSpecial() & self.hasNaNMantissa()

    @hwt_expr_producer
    def isInf(self):
        return self.isSpecial() & self.hasInfMantissa()

    @hwt_expr_producer
    def isZero(self):
        return self.exponent._eq(0) & self.mantissa._eq(0)

    @hwt_expr_producer
    def isSubnormal(self):
        return self.exponent._eq(0) & (self.mantissa != 0)

    @hwt_expr_producer
    def hasInfMantissa(self):
        return self.mantissa._eq(0)

    @hwt_expr_producer
    def hasNaNMantissa(self):
        return self.mantissa != 0

    def pack(self):
        return Concat(self.sign, self.exponent, self.mantissa)

    @override
    def __add__(self, other):
        other = toHVal(other, HFloatTmp)
        res = fadd(self._auto_cast(HFloatTmp), other._auto_cast(HFloatTmp))
        return res._auto_cast(self._dtype)

    @override
    def __sub__(self, other):
        other = toHVal(other, HFloatTmp)
        res = fsub(self._auto_cast(HFloatTmp), other._auto_cast(HFloatTmp))
        return res._auto_cast(self._dtype)

    @override
    def __mul__(self, other):
        other = toHVal(other, HFloatTmp)
        res = fmul(self._auto_cast(HFloatTmp), other._auto_cast(HFloatTmp))
        return res._auto_cast(self._dtype)

    @override
    def __truediv__(self, other):
        other = toHVal(other, HFloatTmp)
        res = fdiv(self._auto_cast(HFloatTmp), other._auto_cast(HFloatTmp))
        return res._auto_cast(self._dtype)


class IEEE754FpHConst(HStructConstBase, IEEE754FpValue):

    def to_py(self) -> float:
        t = self._dtype
        if t == IEEE754Fp16:
            vecT = uint16_t
            unpackChar = 'e'
        elif t == IEEE754Fp32:
            vecT = uint32_t
            unpackChar = 'f'
        elif t == IEEE754Fp64:
            vecT = uint64_t
            unpackChar = 'd'
        else:
            raise NotImplementedError(t)
        try:
            pyVal = int(self._reinterpret_cast(vecT))
        except ValidityError:
            return None
        return struct.unpack(unpackChar, pyVal.to_bytes(vecT.bit_length() // 8, byteorder='little'))[0]


class IEEE754FpHStructRtlSignalBase(HStructRtlSignalBase, IEEE754FpValue):
    pass


# https://www.h-schmidt.net/FloatConverter/IEEE754.html
class IEEE754Fp(HStruct):
    """
    IEEE-754 s special meanings
    
    =================== ============ ================= ================
    Meaning             Sign Field   Exponent Field    Mantissa Field
    =================== ============ ================= ================
    Zero                Don't care   All 0s            All 0s
    Positive subnormal  0            All 0s            Non-zero
    Negative subnormal  1            All 0s            Non-zero
    Positive Infinity   0            All 1s            All 0s
    Negative Infinity   1            All 1s            All 0s
    Not a Number(NaN)   Don't care   All 1s            Non-zero
    =================== ============ ================= ================
    
    :note: subnormal and denormal is synonym.
    :note: significand, refers to the part of the mantissa that is actually stored in a floating-point number
        (= mantissa without leading 1)

    Exponent is biased. For fp32 it has an offset of -127.
    (msb=1, others=0) (EXPONENT_OFFSET_U) value represents offset of 0.
    All 1s represent the highest value, 0 the lowest.
    If the exponent is 0, then:
        * the leading bit becomes 0
        * the exponent is fixed to -126 (not -127 as if we didn't have this exception)
    
    Single operations are commutative, but sequence is not associative. (a + b) equals (b + a)
    But (a + b) + c may not equal a + (b + c)
    """
    _HStructConstBase = IEEE754FpHConst
    _HStructRtlSignalBase = IEEE754FpHStructRtlSignalBase

    def __init__(self, exponentWidth, mantissaWidth,
                 signed=True,
                 rounding=HFloatTmpRounding.ROUND_C_DEFAULT,
                 saturation=HFloatTmpSaturation.SATURATE_C_DEFAULT,
                 name=None, const=False):
        self.EXPONENT_WIDTH = exponentWidth
        self.MANTISSA_WIDTH = mantissaWidth
        self.EXPONENT_OFFSET = -mask(exponentWidth - 1)
        self.EXPONENT_OFFSET_U = to_unsigned(self.EXPONENT_OFFSET, self.EXPONENT_WIDTH)
        self.signed = signed
        HStruct.__init__(self,
            # mantissa on lowest bits sign on MSB
            (HBits(mantissaWidth, signed=False), "mantissa"),
            (HBits(exponentWidth, signed=False), "exponent"),  # biased with EXPONENT_OFFSET
            * (((BIT, "sign"),) if signed else ()),
            name=name,
            const=const,
        )

        isInQFormat = False
        supportSubnormal = False
        hasSign = bool(self.signed)
        hasIsNaN = False
        hasIsInf = False
        hasIs1 = False
        hasIs0 = False

        self._cfg = HFloatTmpConfig(
            isInQFormat,
            exponentWidth,
            mantissaWidth,
            supportSubnormal,
            hasSign,
            hasIsNaN,
            hasIsInf,
            hasIs1,
            hasIs0,
            rounding,
            saturation
        )

    @classmethod
    def fromHFloatTmpConfig(cls, cfg: HFloatTmpConfig) -> Self:
        assert not cfg.isInQFormat, cfg
        res = cls(cfg.exponentOrIntWidth, cfg.mantissaOrFracWidth, cfg.hasSign, cfg.rounding, cfg.saturation)
        res._cfg = cfg
        return res

    def fromPyInt(self, v: int, vld_mask:Optional[int]=None):
        """
        Construct constant from raw bits (in the form of python integer)
        """
        if self == IEEE754Fp16:
            vecT = uint16_t
        elif self == IEEE754Fp32:
            vecT = uint32_t
        elif self == IEEE754Fp64:
            vecT = uint64_t
        else:
            raise NotImplementedError()
        hVal = vecT.from_py(v, vld_mask=vld_mask)
        return hVal._reinterpret_cast(self)

    def from_py(self, v, vld_mask=None):
        if isinstance(v, (float, int)):
            if self != IEEE754Fp64:
                raise NotImplementedError(self, "not implemented rounding when converting from python float to a float of a different size")
            if isinstance(v, int):
                v = float(v)

            if vld_mask is not None:
                raise NotImplementedError()

            v = int.from_bytes(struct.pack("d", v), byteorder='little')
            v = {
                "mantissa": get_bit_range(v, 0, self.MANTISSA_WIDTH),
                "exponent": get_bit_range(v, self.MANTISSA_WIDTH, self.EXPONENT_WIDTH),
                "sign": get_bit_range(v, self.MANTISSA_WIDTH + self.EXPONENT_WIDTH, 1),
            }

        return HStruct.from_py(self, v, vld_mask)

    @internal
    @classmethod
    def get_auto_cast_HConst_fn(cls):
        from tests.math.fp.fptypesCast import auto_cast_IEEE754Fp
        return auto_cast_IEEE754Fp

    @internal
    @classmethod
    def get_auto_cast_RtlSignal_fn(cls):
        from tests.math.fp.fptypesCast import auto_cast_IEEE754Fp
        return auto_cast_IEEE754Fp

    @hlsBytecode
    def getSpecialExponent(self):
        return mask(self.EXPONENT_WIDTH)

    @hlsBytecode
    def getNaNMantisa(self):
        return 1 << (self.MANTISSA_WIDTH - 1)


# standard IEEE754 floating point number types
IEEE754Fp16 = IEEE754Fp(5, 10, name="float16")
IEEE754Fp32 = IEEE754Fp(8, 23, name="float32")  # c float
IEEE754Fp64 = IEEE754Fp(11, 52, name="float64")  # c double

# other commonly used floating point number types
TF32 = IEEE754Fp(8, 10, name="TF32")  # NVidia's TensorFloat32 (19 bits)
BF16 = IEEE754Fp(7, 8, name="BF16")  # BFLOAT16
fp24 = IEEE754Fp(7, 16, name="fp24")  # AMD's fp24 format
PXR24 = IEEE754Fp(8, 15, name="PXR24")  # Pixar's PXR24 format
sfp_3_3 = IEEE754Fp(3, 3, name="sfp_3_3")  # Xilinx Small Floating Point<3,3>: https://xilinx.eetrend.com/files/2021-06/wen_zhang_/100113810-209893-wp530-small-floating-point.pdf
