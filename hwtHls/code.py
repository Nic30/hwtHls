"""
:see: https://llvm.org/docs/LangRef.html#instruction-reference
      https://llvm.org/docs/LangRef.html#intrinsic-functions
      llvm/ADT/bit.h
"""
from typing import Union

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.bits import HBits
from hwt.hdl.const import HConst
from hwt.math import log2ceil, toPow2Ceil
from hwt.mainBases import RtlSignalBase
from pyMathBitPrecise.bit_utils import mask, reverse_bits, to_signed, \
    to_unsigned, bit_field, get_bit
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.mainBases import HwIOBase
from hwt.hdl.types.defs import BIT


def ctlz(v: Union[HConst, RtlSignalBase], is_zero_poison:bool=False):
    """
    Count leading zeros
    
    :param is_zero_poison: constant flag that indicates
         whether the intrinsic returns a valid result if the first
         argument is zero. If the first argument is zero and 
         the second argument is true, the result is poison.
         Historically some architectures did not provide a defined 
         result for zero values as efficiently, and many algorithms
         are now predicated on avoiding zero-value inputs.
    
    :note: translates to llvm.ctlz.*
    """
    w = v._dtype.bit_length()
    resTy = HBits(log2ceil(w + 1))
    if isinstance(v, HConst):
        v: HConst
        if not v._is_full_valid():
            return resTy.from_py(None)

        Val = v.val
        if Val == 0:
            return resTy.from_py(w)

        # Bisection method.
        ZeroBits = 0
        Shift = w >> 1
        while Shift:
            Tmp = Val >> Shift;
            if Tmp:
                Val = Tmp
            else:
                ZeroBits |= Shift
            Shift >>= 1

        return resTy.from_py(ZeroBits)
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        return HOperatorNode.withRes(OP_CTLZ, (v, BIT.from_py(is_zero_poison)), resTy)


OP_CTLZ = HOperatorDef(ctlz, False, idStr="OP_CTLZ")


def cttz(v: Union[HConst, RtlSignalBase], is_zero_poison:bool=False):
    """
    Count trailing zeros
    :param is_zero_poison: see doc for :func:`~.ctlz`
    :note: translates to llvm.cttz.*
    """
    w = v._dtype.bit_length()
    resTy = HBits(log2ceil(w + 1))
    if isinstance(v, HConst):
        v: HConst
        if not v._is_full_valid():
            return resTy.from_py(None)

        Val = v.val

        if Val == 0:
            return resTy.from_py(w)
        if Val & 0x1:
            return resTy.from_py(0)

        # Bisection method.
        ZeroBits = 0
        Shift = w >> 1
        Mask = mask(w) >> Shift
        while Shift:
            if (Val & Mask) == 0:
                Val >>= Shift
                ZeroBits |= Shift

            Shift >>= 1
            Mask >>= Shift

        return resTy.from_py(ZeroBits)
    else:
        if isinstance(v, HwIOBase):
            v = v._sig

        return HOperatorNode.withRes(OP_CTTZ, (v, BIT.from_py(is_zero_poison)), resTy)


OP_CTTZ = HOperatorDef(cttz, False, idStr="OP_CTTZ")


def _ctpop_u64(v: int):
    v = v - ((v >> 1) & 0x5555555555555555)
    v = (v & 0x3333333333333333) + ((v >> 2) & 0x3333333333333333)
    v = (v + (v >> 4)) & 0x0F0F0F0F0F0F0F0F
    return (v * 0x0101010101010101) >> 56


def ctpop(v: Union[HConst, RtlSignalBase]):
    """
    Count number of ones
    
    :note: translates to llvm.ctpop.*
    """
    w = v._dtype.bit_length()
    resTy = HBits(log2ceil(w + 1))
    if isinstance(v, HConst):
        v: HConst
        if not v._is_full_valid():
            return resTy.from_py(None)
        res = 0
        mask_u64 = mask(64)
        Val = v.val
        while True:
            res += _ctpop_u64(Val & mask_u64)
            w -= 64
            if w <= 0:
                break
            Val >>= 64

        return resTy.from_py(res)
    else:
        if isinstance(v, HwIOBase):
            v = v._sig

        return HOperatorNode.withRes(OP_CTPOP, (v,), resTy)


OP_CTPOP = HOperatorDef(ctpop, False, idStr="OP_CTPOP")


def bitreverse(v: Union[HConst, RtlSignalBase]):
    """
    Reverses order of bits in bit vector

    :note: translates to llvm.bitreverse.*
    """
    width = v._dtype.bit_length()
    if isinstance(v, HConst):
        return v._dtype.from_py(reverse_bits(v.val, width), reverse_bits(v.vld_mask, width))
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        return HOperatorNode.withRes(OP_BITREVERSE, (v,), v._dtype)


OP_BITREVERSE = HOperatorDef(bitreverse, False, idStr="OP_BITREVERSE")


def ashr(v: Union[HConst, RtlSignalBase], shiftAmount: Union[HConst, RtlSignalBase]):
    """
    Arithmetic shift right (MSB copy is shifted in) (shiftAmount must be >= 0)
    """
    t = v._dtype
    w = t.bit_length()
    shW = shiftAmount._dtype.bit_length()
    assert shW == log2ceil(w + 1), (shW, log2ceil(w + 1), w)
    if isinstance(v, HConst) and isinstance(shiftAmount, HConst):
        if not isinstance(t, HBits):
            raise NotImplementedError(t)

        if not shiftAmount._is_full_valid():
            return t.from_py(None)
        shiftAmount = int(shiftAmount)
        assert shiftAmount < toPow2Ceil(w + 1), (shiftAmount, w)
        assert shiftAmount >= 0, (shiftAmount, w)
        # :note: python >> is arithmetic shift, but the value is stored in unsigned format
        return t.from_py(
            to_unsigned(to_signed(v.val, w) >> shiftAmount, w),
            to_unsigned(to_signed(v.vld_mask, w) >> shiftAmount, w),
        )
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        if isinstance(shiftAmount, HwIOBase):
            shiftAmount = shiftAmount._sig
        shWidth = shiftAmount._dtype.bit_length()
        if shWidth != w:
            assert shWidth < w, (shWidth, w)
            shiftAmount = zext(shiftAmount, w)

        return HOperatorNode.withRes(OP_ASHR, (v, shiftAmount), t)


OP_ASHR = HOperatorDef(ashr, False, idStr="OP_ASHR")


def lshr(v: Union[HConst, RtlSignalBase], shiftAmount: Union[HConst, RtlSignalBase]):
    """
    Logical shift right (0 is shifted in) (shiftAmount must be >= 0)
    """
    t = v._dtype
    w = t.bit_length()
    shW = shiftAmount._dtype.bit_length()
    assert shW == log2ceil(w + 1), (shW, log2ceil(w + 1), w)
    if isinstance(v, HConst) and isinstance(shiftAmount, HConst):
        if not isinstance(t, HBits):
            raise NotImplementedError(t)
        if not shiftAmount._is_full_valid():
            return t.from_py(None)
        shiftAmount = int(shiftAmount)
        assert shiftAmount < toPow2Ceil(w + 1), (shiftAmount, w)
        assert shiftAmount >= 0, (shiftAmount, w)

        # :note: python >> is arithmetic shift, but the value is stored in unsigned format
        return t.from_py(
            v.val >> shiftAmount,
            (v.vld_mask >> shiftAmount) | (0 if shiftAmount > w else bit_field(w - shiftAmount, w)),
        )
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        if isinstance(shiftAmount, HwIOBase):
            shiftAmount = shiftAmount._sig

        shWidth = shiftAmount._dtype.bit_length()
        if shWidth != w:
            assert shWidth < w, (shWidth, w)
            shiftAmount = zext(shiftAmount, w)
        return HOperatorNode.withRes(OP_LSHR, (v, shiftAmount), t)


OP_LSHR = HOperatorDef(lshr, False, idStr="OP_LSHR")


def shl(v: Union[HConst, RtlSignalBase], shiftAmount: Union[HConst, RtlSignalBase]):
    """
    Shift left <<, 0 is shifted in (shiftAmount must be >= 0)
    """
    t = v._dtype
    w = t.bit_length()
    shW = shiftAmount._dtype.bit_length()
    assert shW == log2ceil(w + 1), (shW, log2ceil(w + 1), w)
    if isinstance(v, HConst) and isinstance(shiftAmount, HConst):
        if not isinstance(t, HBits):
            raise NotImplementedError(t)
        t: HBits
        m = t.all_mask()
        if not shiftAmount._is_full_valid():
            return t.from_py(None)
        shiftAmount = int(shiftAmount)
        assert shiftAmount < toPow2Ceil(w + 1), (shiftAmount, w)
        assert shiftAmount >= 0, (shiftAmount, w)

        # :note: python >> is arithmetic shift, but the value is stored in unsigned format
        return t.from_py(
            (v.val << shiftAmount) & m,
            (v.vld_mask << shiftAmount) & m | mask(shiftAmount),
        )
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        if isinstance(shiftAmount, HwIOBase):
            shiftAmount = shiftAmount._sig
        shWidth = shiftAmount._dtype.bit_length()
        if shWidth != w:
            assert shWidth < w, (shWidth, w)
            shiftAmount = zext(shiftAmount, w)
        return HOperatorNode.withRes(OP_LSHR, (v, shiftAmount), t)


OP_SHL = HOperatorDef(shl, False, idStr="OP_SHL")


def fshl(a: Union[HConst, RtlSignalBase], b: Union[HConst, RtlSignalBase], c: Union[HConst, RtlSignalBase, int]):
    """
    The ‘llvm.fshl’ family of intrinsic functions performs a funnel shift left: the first two values are concatenated as { %a : %b }
    (%a is the most significant bits of the wide value), the combined value is shifted left, and the most significant bits are extracted
    to produce a result that is the same size as the original arguments. If the first 2 arguments are identical, this is equivalent
    to a rotate left operation. For vector types, the operation occurs for each element of the vector.
    The shift argument is treated as an unsigned amount modulo the element size of the arguments.

    .. code-block:: llvm
    
        %r = call i8 @llvm.fshl.i8(i8 %x, i8 %y, i8 %z)  ; %r = i8: msb_extract((concat(x, y) << (z % 8)), 8)
        %r = call i8 @llvm.fshl.i8(i8 255, i8 0, i8 15)  ; %r = i8: 128 (0b10000000)
        %r = call i8 @llvm.fshl.i8(i8 15, i8 15, i8 11)  ; %r = i8: 120 (0b01111000)
        %r = call i8 @llvm.fshl.i8(i8 0, i8 255, i8 8)   ; %r = i8: 0   (0b00000000)

    """
    raise NotImplementedError()


OP_FSHL = HOperatorDef(fshl, False, idStr="OP_FSHL")


def fshr(a: Union[HConst, RtlSignalBase], b: Union[HConst, RtlSignalBase], c: Union[HConst, RtlSignalBase, int]):
    """
    The ‘llvm.fshr’ family of intrinsic functions performs a funnel shift right: the first two values are concatenated as { %a : %b }
    (%a is the most significant bits of the wide value), the combined value is shifted right, and the least significant bits are extracted
    to produce a result that is the same size as the original arguments. If the first 2 arguments are identical, this is equivalent
    to a rotate right operation. For vector types, the operation occurs for each element of the vector. The shift argument is treated
    as an unsigned amount modulo the element size of the arguments.

    .. code-block:: llvm
        %r = call i8 @llvm.fshr.i8(i8 %x, i8 %y, i8 %z)  ; %r = i8: lsb_extract((concat(x, y) >> (z % 8)), 8)
        %r = call i8 @llvm.fshr.i8(i8 255, i8 0, i8 15)  ; %r = i8: 254 (0b11111110)
        %r = call i8 @llvm.fshr.i8(i8 15, i8 15, i8 11)  ; %r = i8: 225 (0b11100001)
        %r = call i8 @llvm.fshr.i8(i8 0, i8 255, i8 8)   ; %r = i8: 255 (0b11111111)   

    """
    raise NotImplementedError()


OP_FSHR = HOperatorDef(fshr, False, idStr="OP_FSHR")


def getMsb(v: Union[HConst, RtlSignalBase]):
    return v[v._dtype.bit_length() - 1]


def zext(v: Union[HConst, RtlSignalBase], newWidth: int):
    """
    Zero extension
    """
    t = v._dtype
    w = t.bit_length()
    if not isinstance(t, HBits):
        raise NotImplementedError(t)
    t: HBits
    assert newWidth > w, (newWidth, w)
    resTy = HBits(newWidth, signed=t.signed)
    if isinstance(v, HConst):
        return resTy.from_py(v.val, vld_mask=v.vld_mask | bit_field(w, newWidth))
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        return HOperatorNode.withRes(OP_ZEXT, (v,), resTy)


OP_ZEXT = HOperatorDef(zext, False, idStr="OP_ZEXT")


def sext(v: Union[HConst, RtlSignalBase], newWidth: int):
    """
    Signed extension
    """
    t = v._dtype
    w = t.bit_length()
    if not isinstance(t, HBits):
        raise NotImplementedError(t)
    t: HBits
    assert newWidth > w, (newWidth, w)
    resTy = HBits(newWidth, signed=t.signed)
    if isinstance(v, HConst):
        val = v.val
        newBitsMask = bit_field(w, newWidth)
        if get_bit(val, w - 1):
            val |= newBitsMask
        vldMask = v.vld_mask
        if get_bit(vldMask, w - 1):
            vldMask |= newBitsMask
        return resTy.from_py(val, vld_mask=vldMask)
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        return HOperatorNode.withRes(OP_SEXT, (v,), resTy)


OP_SEXT = HOperatorDef(sext, False, idStr="OP_SEXT")


def hwUMax(v0: Union[HConst, RtlSignalBase], v1: Union[HConst, RtlSignalBase]):
    """
    :returns: maximum of two unsigned values
    """
    if isinstance(v0, HwIOBase):
        v0 = v0._sig

    if isinstance(v1, HwIOBase):
        v1 = v1._sig

    if v0 is v1:
        return v0

    t = v0._dtype
    assert t == v1._dtype, ("Values must be of the same type", v0, v1)
    if isinstance(v0, HConst) and isinstance(v1, HConst):
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return BIT.from_py(None)
        else:
            if v0.val < v1.val:
                return v1
            else:
                return v0
    else:
        return HOperatorNode.withRes(OP_UMAX, (v0, v1), t)


OP_UMAX = HOperatorDef(hwUMax, False, idStr="OP_UMAX")


def hwSMax(v0: Union[HConst, RtlSignalBase], v1: Union[HConst, RtlSignalBase]):
    """
    :returns: maximum of two signed values
    """
    if isinstance(v0, HwIOBase):
        v0 = v0._sig

    if isinstance(v1, HwIOBase):
        v1 = v1._sig

    if v0 is v1:
        return v0

    t = v0._dtype
    assert t == v1._dtype, ("Values must be of the same type", v0, v1)
    if isinstance(v0, HConst) and isinstance(v1, HConst):
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return BIT.from_py(None)
        else:
            w = t.bit_length()
            if to_signed(v0.val, w) < to_signed(v1.val, w):
                return v1
            else:
                return v0
    else:
        return HOperatorNode.withRes(OP_SMAX, (v0, v1), t)


OP_SMAX = HOperatorDef(hwSMax, False, idStr="OP_SMAX")


def hwMax(v0: Union[HConst, RtlSignalBase], v1: Union[HConst, RtlSignalBase]):
    if v0._dtype.signed:
        return hwSMax(v0, v1)
    else:
        return hwUMax(v0, v1)


def hwUMin(v0: Union[HConst, RtlSignalBase], v1: Union[HConst, RtlSignalBase]):
    """
    :returns: minimum of two unsigned values
    """
    if isinstance(v0, HwIOBase):
        v0 = v0._sig

    if isinstance(v1, HwIOBase):
        v1 = v1._sig

    if v0 is v1:
        return v0

    t = v0._dtype
    assert t == v1._dtype, ("Values must be of the same type", v0, v1, t, v1._dtype)
    if isinstance(v0, HConst) and isinstance(v1, HConst):
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return BIT.from_py(None)
        else:
            if v1.val < v0.val:
                return v1
            else:
                return v0
    else:
        return HOperatorNode.withRes(OP_UMIN, (v0, v1), t)


OP_UMIN = HOperatorDef(hwUMin, False, idStr="OP_UMIN")


def hwSMin(v0: Union[HConst, RtlSignalBase], v1: Union[HConst, RtlSignalBase]):
    """
    :returns: minimum of two signed values
    """
    if isinstance(v0, HwIOBase):
        v0 = v0._sig

    if isinstance(v1, HwIOBase):
        v1 = v1._sig

    if v0 is v1:
        return v0

    t = v0._dtype
    assert t == v1._dtype, ("Values must be of the same type", v0, v1)
    if isinstance(v0, HConst) and isinstance(v1, HConst):
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return BIT.from_py(None)
        else:
            w = t.bit_length()
            if to_signed(v1.val, w) < to_signed(v0.val, w):
                return v1
            else:
                return v0
    else:
        return HOperatorNode.withRes(OP_SMIN, (v0, v1), t)


OP_SMIN = HOperatorDef(hwSMin, False, idStr="OP_SMIN")


def hwMin(v0: Union[HConst, RtlSignalBase], v1: Union[HConst, RtlSignalBase]):
    if v0._dtype.signed:
        return hwSMin(v0, v1)
    else:
        return hwUMin(v0, v1)

