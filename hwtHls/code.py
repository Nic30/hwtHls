"""
:see: https://llvm.org/docs/LangRef.html#instruction-reference
      https://llvm.org/docs/LangRef.html#intrinsic-functions
      llvm/ADT/bit.h
:note: :class:`hwt.hdl.operatorDefs.HwtOps` are compatible and its translation
    is handled directly in :class:`ToLlvmIrTranslator`
"""
from typing import Union, Optional

from hdlConvertorAst.hdlAst._expr import HdlOpType
from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.mainBases import HwIOBase
from hwt.mainBases import RtlSignalBase
from hwt.math import log2ceil, toPow2Ceil, AnyHValue
from hwtHls._llvmOpDefUtils import _getllvmIntBitcountIntrinsicConstructor, \
    _getllvmIntUnaryIntrinsicConstructor, _getllvmIntBinOpConstructor, \
    _getllvmIntFShIntrinsicConstructor, _getllvmIntBinaryIntrinsicConstructor, \
    _llvmIntCtpopIntrinsicConstructor
from hwtHls.frontend.hOperatorDefLlvm import HOperatorDefLlvm
from hwtHls.llvm.llvmIr import Intrinsic
from pyMathBitPrecise.bit_utils import mask, reverse_bits as reverse_bits_int, to_signed, \
    to_unsigned, bit_field, ValidityError, ctlz as ctlz_int, \
    ctpop as ctpop_int, cttz as cttz_int


@hwt_expr_producer
def ctlz(v: AnyHBitsValue, is_zero_poison:bool=False) -> AnyHBitsValue:
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

        return resTy.from_py(ctlz_int(v.val, w))

    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        return HOperatorNode.withRes(OP_CTLZ, (v, BIT.from_py(is_zero_poison)), resTy)


OP_CTLZ = HOperatorDefLlvm(ctlz, _getllvmIntBitcountIntrinsicConstructor(Intrinsic.ctlz), False, idStr="OP_CTLZ")


@hwt_expr_producer
def cttz(v: AnyHBitsValue, is_zero_poison:bool=False) -> AnyHBitsValue:
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

        return resTy.from_py(cttz_int(v.val, w))
    else:
        if isinstance(v, HwIOBase):
            v = v._sig

        return HOperatorNode.withRes(OP_CTTZ, (v, BIT.from_py(is_zero_poison)), resTy)


OP_CTTZ = HOperatorDefLlvm(cttz, _getllvmIntBitcountIntrinsicConstructor(Intrinsic.cttz), False, idStr="OP_CTTZ")


@hwt_expr_producer
def ctpop(v: AnyHBitsValue) -> AnyHBitsValue:
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
        res = ctpop_int(v.val, w)
        return resTy.from_py(res)
    else:
        if isinstance(v, HwIOBase):
            v = v._sig

        return HOperatorNode.withRes(OP_CTPOP, (v,), resTy)


OP_CTPOP = HOperatorDefLlvm(ctpop, _llvmIntCtpopIntrinsicConstructor,
                            False, idStr="OP_CTPOP")


@hwt_expr_producer
def bitreverse(v: AnyHBitsValue) -> AnyHBitsValue:
    """
    Reverses order of bits in bit vector

    :note: translates to llvm.bitreverse.*
    """
    width = v._dtype.bit_length()
    if isinstance(v, HConst):
        return v._dtype.from_py(reverse_bits_int(v.val, width), reverse_bits_int(v.vld_mask, width))
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        return HOperatorNode.withRes(OP_BITREVERSE, (v,), v._dtype)


OP_BITREVERSE = HOperatorDefLlvm(bitreverse, _getllvmIntUnaryIntrinsicConstructor(Intrinsic.bitreverse),
                                 False, idStr="OP_BITREVERSE")


@hwt_expr_producer
def ashr(v: AnyHBitsValue, shiftAmount: AnyHBitsValue,
         zextShift=True) -> AnyHBitsValue:
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
        if zextShift:
            shWidth = shiftAmount._dtype.bit_length()
            if shWidth != w:
                assert shWidth < w, (shWidth, w)
                shiftAmount = zext(shiftAmount, w)

        return HOperatorNode.withRes(OP_ASHR, (v, shiftAmount), t)


OP_ASHR = HOperatorDefLlvm(ashr, _getllvmIntBinOpConstructor(lambda b: b.CreateAShr),
                           False, idStr="OP_ASHR", hdlConvertoAstOp=HdlOpType.SRA)


@hwt_expr_producer
def lshr(v: AnyHBitsValue, shiftAmount: AnyHBitsValue,
         zextShift=True) -> AnyHBitsValue:
    """
    Logical shift right (0 is shifted in) (shiftAmount must be >= 0)
    """
    t = v._dtype
    assert not shiftAmount._dtype.signed
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
        if t.signed and v.val < 0:
            val = to_signed(to_unsigned(v.val, w) >> shiftAmount, w)
        else:
            assert v.val >= 0
            val = v.val >> shiftAmount

        return t.from_py(
            val,
            (v.vld_mask >> shiftAmount) | (0 if shiftAmount > w else bit_field(w - shiftAmount, w)),
        )
    else:
        if isinstance(v, HwIOBase):
            v = v._sig
        if isinstance(shiftAmount, HwIOBase):
            shiftAmount = shiftAmount._sig
        if zextShift:
            shWidth = shiftAmount._dtype.bit_length()
            if shWidth != w:
                assert shWidth < w, (shWidth, w)
                shiftAmount = zext(shiftAmount, w)
        return HOperatorNode.withRes(OP_LSHR, (v, shiftAmount), t)


OP_LSHR = HOperatorDefLlvm(lshr, _getllvmIntBinOpConstructor(lambda b: b.CreateLShr),
                           False, idStr="OP_LSHR", hdlConvertoAstOp=HdlOpType.SRL)


@hwt_expr_producer
def shl(v: AnyHBitsValue, shiftAmount: AnyHBitsValue,
        zextShift: bool=True) -> AnyHBitsValue:
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
        if zextShift:
            shWidth = shiftAmount._dtype.bit_length()
            if shWidth != w:
                assert shWidth < w, (shWidth, w)
                shiftAmount = zext(shiftAmount, w)
        return HOperatorNode.withRes(OP_SHL, (v, shiftAmount), t)


OP_SHL = HOperatorDefLlvm(shl, _getllvmIntBinOpConstructor(lambda b: b.CreateShl), False, idStr="OP_SHL", hdlConvertoAstOp=HdlOpType.SLL)


@hwt_expr_producer
def fshl(a: AnyHBitsValue, b: AnyHBitsValue, c: Union[HConst, RtlSignalBase, int])\
        ->AnyHBitsValue:
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
    t = a._dtype
    if isinstance(c, HConst):
        try:
            c = int(c)
        except ValidityError:
            return a._dtype.from_py(None)

    if isinstance(c, int):
        w = t.bit_length()
        c %= w
        if c == 0:
            return a
        elif c == w:
            return b
        else:
            # b shifted into a from lsb
            return Concat(a[w - c:], b[:w - c])
    else:
        if isinstance(a, HwIOBase):
            a = a._sig
        if isinstance(b, HwIOBase):
            b = b._sig
        if isinstance(c, HwIOBase):
            c = c._sig
        assert b._dtype == t, (t, b._dtype, "all operands must be of same type")
        if not (c._dtype == t):
            c = zext(c, t.bit_length())
        return HOperatorNode.withRes(OP_FSHL, (a, b, c), t)


OP_FSHL = HOperatorDefLlvm(fshl, _getllvmIntFShIntrinsicConstructor(Intrinsic.fshl), False, idStr="OP_FSHL")


@hwt_expr_producer
def fshr(a: AnyHBitsValue, b: AnyHBitsValue, c: Union[HConst, RtlSignalBase, int])\
        ->AnyHBitsValue:
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
    t = a._dtype
    if isinstance(c, HConst):
        try:
            c = int(c)
        except ValidityError:
            return a._dtype.from_py(None)

    if isinstance(c, int):
        w = t.bit_length()
        c %= w
        if c == 0:
            return a
        elif c == w:
            return b
        else:
            # lower bits of 'b' shifter before 'a', lower bits of 'a' shifted out
            return Concat(b[c:], a[:c],)
    else:
        if isinstance(a, HwIOBase):
            a = a._sig
        if isinstance(b, HwIOBase):
            b = b._sig
        if isinstance(c, HwIOBase):
            c = c._sig
        assert b._dtype == t, (t, b._dtype, "all operands must be of same type")
        if not (c._dtype == t):
            c = zext(c, t.bit_length())
        return HOperatorNode.withRes(OP_FSHL, (a, b, c), t)


OP_FSHR = HOperatorDefLlvm(fshr, _getllvmIntFShIntrinsicConstructor(Intrinsic.fshr), False, idStr="OP_FSHR")


@hwt_expr_producer
def ror(sig:Union[RtlSignalBase, HConst], howMany: Union[HConst, RtlSignalBase, int])\
       ->AnyHBitsValue:
    "Rotate right"
    if sig._dtype.bit_length() == 1:
        return sig

    return fshr(sig, sig, howMany)


OP_ROR = HOperatorDef(ror, False, idStr="OP_ROR", hdlConvertoAstOp=HdlOpType.ROR)


@hwt_expr_producer
def rol(sig:Union[RtlSignalBase, HConst], howMany:Union[RtlSignalBase, int])\
        ->AnyHBitsValue:
    "Rotate left"
    if sig._dtype.bit_length() == 1:
        return sig

    return fshl(sig, sig, howMany)


OP_ROL = HOperatorDef(rol, False, idStr="OP_ROL", hdlConvertoAstOp=HdlOpType.ROL)


@hwt_expr_producer
def shlIn(a: AnyHBitsValue, b: AnyHBitsValue)\
         ->AnyHBitsValue:
    """
    Shift in b into value of a from lsb side
    """
    return Concat(a[a._dtype.bit_length() - b._dtype.bit_length():], b)


@hwt_expr_producer
def zext(v: Union[int, HConst, RtlSignalBase], newWidth: int) -> AnyHBitsValue:
    """
    Zero extension
    """
    if isinstance(v, int):
        return HBits(newWidth).from_py(v)

    return v._zext(newWidth)


@hwt_expr_producer
def zextToTy(v: Union[int, HConst, RtlSignalBase], newTy: HBits) -> AnyHBitsValue:
    return zext(v, newTy.bit_length())


@hwt_expr_producer
def sext(v: AnyHBitsValue, newWidth: int) -> AnyHBitsValue:
    """
    Signed extension
    """
    return v._sext(newWidth)


def _handleAutoCastOfMinMaxOperands(v0: AnyHValue,
                                    v1: AnyHValue,
                                    autoExtend:bool) -> tuple[AnyHValue, AnyHValue]:
    if isinstance(v0, HwIOBase):
        v0 = v0._sig

    if isinstance(v1, HwIOBase):
        v1 = v1._sig

    if v0 is v1:
        return (v0, v1)

    t0 = v0._dtype
    t0w = t0.bit_length()
    t1 = v1._dtype
    if autoExtend:
        if t0 == t1:
            pass
        else:
            t1w = t1.bit_length()
            if t0w < t1w:
                v0 = zext(v0, t1w)
                t0w = t1w
            elif t0w > t1w:
                v1 = zext(v1, t0w)
            else:
                raise TypeError(t0, t1)
    else:
        assert t0 == t1, ("Values must be of the same type", v0, v1, t0, t1)

    return (v0, v1)


@hwt_expr_producer
def hwUMax(v0: AnyHValue, v1: AnyHValue,
           autoExtend:bool=False) -> AnyHValue:
    """
    :returns: maximum of two unsigned values
    """
    v0, v1 = _handleAutoCastOfMinMaxOperands(v0, v1, autoExtend)

    if v0 is v1:
        return v0

    t = v0._dtype
    if isinstance(v0, HConst) and isinstance(v1, HConst):
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return t.from_py(None)
        else:
            if v0.val < v1.val:
                return v1
            else:
                return v0
    else:
        return HOperatorNode.withRes(OP_UMAX, (v0, v1), t)


OP_UMAX = HOperatorDefLlvm(hwUMax, _getllvmIntBinaryIntrinsicConstructor(Intrinsic.umax),
                           False, idStr="OP_UMAX")


@hwt_expr_producer
def hwSMax(v0: AnyHValue, v1: AnyHValue,
           autoExtend:bool=False) -> AnyHValue:
    """
    :returns: maximum of two signed values
    """
    v0, v1 = _handleAutoCastOfMinMaxOperands(v0, v1, autoExtend)

    if v0 is v1:
        return v0

    if isinstance(v0, HConst) and isinstance(v1, HConst):
        t = v0._dtype
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return t.from_py(None)
        else:
            w = t.bit_length()
            if to_signed(v0.val, w) < to_signed(v1.val, w):
                return v1
            else:
                return v0

    elif isinstance(v0, RtlSignalBase) and isinstance(v0, RtlSignalBase):
        return HOperatorNode.withRes(OP_SMAX, (v0, v1), t)
    else:
        return max(v0, v1)


OP_SMAX = HOperatorDefLlvm(hwSMax, _getllvmIntBinaryIntrinsicConstructor(Intrinsic.smax),
                           False, idStr="OP_SMAX")


@hwt_expr_producer
def hwFMaxinum(v0, v1):
    """
    "max" for fp types https://llvm.org/docs/LangRef.html#llvm-maximum-intrinsic
    """
    if v0 is v1:
        return v0

    if isinstance(v0, HConst) and isinstance(v1, HConst):
        t = v0._dtype
        if v0._is_full_valid() and v1._is_full_valid():
            if v0.val < v1.val:
                return v1
            else:
                return v0
        else:
            return t.from_py(None)

    elif isinstance(v0, RtlSignalBase) and isinstance(v0, RtlSignalBase):
        return HOperatorNode.withRes(OP_MAXIMUM, (v0, v1), t)
    else:
        return max(v0, v1)


@hwt_expr_producer
def hwMax(v0: AnyHValue, v1: AnyHValue, autoExtend=False) -> AnyHValue:
    if isinstance(v0._dtype, HBits):
        if v0._dtype.signed:
            return hwSMax(v0, v1, autoExtend=autoExtend)
        else:
            return hwUMax(v0, v1, autoExtend=autoExtend)
    else:
        return hwFMaxinum(v0, v1)


OP_MAXIMUM = HOperatorDefLlvm(hwFMaxinum, _getllvmIntBinaryIntrinsicConstructor(Intrinsic.maximum),
                              False, idStr="OP_MAXIMUM")


@hwt_expr_producer
def hwUMin(v0: AnyHValue, v1: AnyHValue, autoExtend=False) -> AnyHValue:
    """
    :returns: minimum of two unsigned values
    """

    v0, v1 = _handleAutoCastOfMinMaxOperands(v0, v1, autoExtend)

    if v0 is v1:
        return v0

    if isinstance(v0, HConst) and isinstance(v1, HConst):
        t = v0._dtype
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return t.from_py(None)
        else:
            if v1.val < v0.val:
                return v1
            else:
                return v0
    elif isinstance(v0, RtlSignalBase) and isinstance(v0, RtlSignalBase):
        t = v0._dtype
        return HOperatorNode.withRes(OP_UMIN, (v0, v1), t)
    else:
        assert v0 >= 0 and v1 >= 0, (v0, v1)
        return min(v0, v1)


OP_UMIN = HOperatorDefLlvm(hwUMin, _getllvmIntBinaryIntrinsicConstructor(Intrinsic.umin), False, idStr="OP_UMIN")


@hwt_expr_producer
def hwSMin(v0: AnyHValue, v1: AnyHValue, autoExtend:bool=False) -> AnyHValue:
    """
    :returns: minimum of two signed values
    """
    v0, v1 = _handleAutoCastOfMinMaxOperands(v0, v1, autoExtend)

    if v0 is v1:
        return v0

    t = v0._dtype
    if isinstance(v0, HConst) and isinstance(v1, HConst):
        m = mask(t.bit_length())
        if v0.vld_mask != m or v1.vld_mask != m:
            return t.from_py(None)
        else:
            w = t.bit_length()
            if to_signed(v1.val, w) < to_signed(v0.val, w):
                return v1
            else:
                return v0
    else:
        return HOperatorNode.withRes(OP_SMIN, (v0, v1), t)


OP_SMIN = HOperatorDefLlvm(hwSMin, _getllvmIntBinaryIntrinsicConstructor(Intrinsic.smin), False, idStr="OP_SMIN")


@hwt_expr_producer
def hwFMininum(v0, v1) -> AnyHValue:
    """
    "min" for fp types https://llvm.org/docs/LangRef.html#llvm-minimumnum-intrinsic
    """
    if v0 is v1:
        return v0

    t = v0._dtype
    if isinstance(v0, HConst) and isinstance(v1, HConst):
        if v0._is_full_valid() and v1._is_full_valid():
            if v1.val < v0.val:
                return v1
            else:
                return v0
        else:
            return t.from_py(None)
    else:
        return HOperatorNode.withRes(OP_SMIN, (v0, v1), t)


@hwt_expr_producer
def hwMin(v0: AnyHValue, v1: AnyHValue, autoExtend:bool=False) -> AnyHValue:
    if isinstance(v0._dtype, HBits):
        if v0._dtype.signed:
            return hwSMin(v0, v1, autoExtend=autoExtend)
        else:
            return hwUMin(v0, v1, autoExtend=autoExtend)
    else:
        return hwFMininum(v0, v1)


OP_MINIMUM = HOperatorDefLlvm(hwFMininum, _getllvmIntBinaryIntrinsicConstructor(Intrinsic.minimum), False, idStr="OP_MINIMUM")


@hwt_expr_producer
def hwAbs(v0: AnyHValue) -> AnyHValue:
    if v0._dtype.signed:
        if isinstance(v0, HConst):
            assert isinstance(v0, HBitsConst), v0
            if v0._is_full_valid():
                if v0.val < 0:
                    return v0._dtype.from_py(-v0.val)
                else:
                    return v0
        else:
            return HOperatorNode.withRes(OP_ABS, (v0,), v0._dtype)
    else:
        return v0


OP_ABS = HOperatorDefLlvm(hwSMin, _getllvmIntBinaryIntrinsicConstructor(Intrinsic.abs), False, idStr="OP_ABS")


@hwt_expr_producer
def incrSat(x: AnyHBitsValue, en:Optional[AnyHBitsValue]=None) -> AnyHBitsValue:
    """
    Saturating add 1 operator
    """
    w = x._dtype.bit_length()
    if x._dtype.signed:
        if w == 1:
            # can not increment because it would change sign
            return x
        maxVal = mask(w - 1)
    else:
        maxVal = mask(w)

    isNotMaxVal = x != maxVal
    if en is not None:
        isNotMaxVal = en & isNotMaxVal

    return isNotMaxVal._ternary(x + 1, x)

