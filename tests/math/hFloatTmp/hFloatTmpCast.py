from typing import Union, Tuple

from hwt.code import Concat
from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.bits import HBits
from hwt.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.exceptions import SignalDriverErr
from hwtHls.llvm.llvmIr import IRBuilder, Value, Twine, ValueToConstantInt
from hwtHls.ssa.translation.toLlvm import HOperatorDefLlvm
from hwtLib.types.ctypes import uint8_t
from tests.math.fixp.fixedpoint import HFixedPointQ
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


def _extractHFloatTmpParamsFromFriendType(t: Union[IEEE754Fp, HFixedPointQ, HBits]):

    if isinstance(t, IEEE754Fp):
        isInQFromat = b0
        supportSubnormal = b1
        hasSign = True
        exponentWidth = uint8_t.from_py(t.EXPONENT_WIDTH)
        mantissaWidth = uint8_t.from_py(t.MANTISSA_WIDTH)
    elif isinstance(t, HFixedPointQ):
        isInQFromat = b1
        supportSubnormal = b0
        hasSign = t.signed
        exponentWidth = t.int_bit_length
        mantissaWidth = t.frac_bit_length
    elif isinstance(t, HBits):
        isInQFromat = b1
        supportSubnormal = b0
        hasSign = t.signed
        exponentWidth = t.bit_length()
        mantissaWidth = 0
    else:
        raise TypeError(t)
    hasSign = b1 if hasSign else b0
    exponentWidth = uint8_t.from_py(exponentWidth)
    mantissaWidth = uint8_t.from_py(mantissaWidth)

    return hasSign, isInQFromat, supportSubnormal, exponentWidth, mantissaWidth

# see "denormal-fp-math"
def castToHFloatTmp(op: RtlSignalBase[Union[IEEE754Fp, HFixedPointQ, HBits]], *args):
    assert not args, "This is mean to be used as a separator in expressions and it is not meant to be evaluated."
    t = op._dtype
    hasIsNaN = b0
    hasIsInf = b0
    hasIs1 = b0
    hasIs0 = b0

    hasSign, isInQFromat, supportSubnormal, exponentWidth, mantissaWidth = _extractHFloatTmpParamsFromFriendType(t)
    if isinstance(op, RtlSignalBase):
        try:
            d = op.singleDriver()
        except SignalDriverErr:
            d = None
        if d is not None and isinstance(d, HOperatorNode) and\
            d.operator == OP_CAST_FROM_HFLOATTMP and \
            d.operands[1:] == (exponentWidth, mantissaWidth,
                               isInQFromat, supportSubnormal, hasSign,
                               hasIsNaN, hasIsInf, hasIs1, hasIs0):
            # try reduce useless cast from, to HFloatTmp
            return d.operands[0]

    if isinstance(t, IEEE754Fp):
        tmp = Concat(op.sign, op.exponent, op.mantissa)
    else:
        tmp = op

    return HOperatorNode.withRes(OP_CAST_TO_HFLOATTMP, (
        tmp, exponentWidth, mantissaWidth,
        isInQFromat, supportSubnormal, hasSign, hasIsNaN, hasIsInf, hasIs1, hasIs0),
        HFloatTmp)


def _llvmCastToHFloatTmp(b:IRBuilder, instr: HOperatorNode, srcArg: Value, *ops:Tuple[Union[Value, Twine], ...]) -> Value:
    assert srcArg.getType().isIntegerTy(), (srcArg, srcArg.getType())
    if isinstance(ops[-1], Twine):
        name: Twine = ops[-1]
        ops = ops[:-1]
    else:
        name = None
    ops = (int(ValueToConstantInt(o).getValue().getZExtValue()) for o in ops)
    if name:
        return b.CreateCastToHFloatTmp(srcArg, *ops, name)
    else:
        return b.CreateCastToHFloatTmp(srcArg, *ops)


OP_CAST_TO_HFLOATTMP = HOperatorDefLlvm(castToHFloatTmp, _llvmCastToHFloatTmp, False, idStr="OP_CAST_TO_HFLOATTMP")


def castFromHFloatTmp(op: RtlSignalBase[Union[IEEE754Fp, HFixedPointQ, HBits]], t: Union[IEEE754Fp, HFixedPointQ, HBits]) \
        ->Union[RtlSignalBase[HFloatTmp], HConst[HFloatTmp]]:
    assert op._dtype == HFloatTmp, (op, op._dtype)
    hasSign, isInQFromat, supportSubnormal, exponentWidth, mantissaWidth = _extractHFloatTmpParamsFromFriendType(t)

    hasIsNaN = b0
    hasIsInf = b0
    hasIs1 = b0
    hasIs0 = b0

    return HOperatorNode.withRes(OP_CAST_FROM_HFLOATTMP, (
        op, exponentWidth, mantissaWidth, isInQFromat, supportSubnormal, hasSign, hasIsNaN, hasIsInf, hasIs1, hasIs0), t)


def _llvmCastFromHFloatTmp(b:IRBuilder, instr: HOperatorNode, srcArg: Value, *ops:Tuple[Union[Value, Twine]]) -> Value:
    assert srcArg.getType().isDoubleTy(), srcArg
    if isinstance(ops[-1], Twine):
        name: Twine = ops[-1]
        ops = ops[:-1]
    else:
        name = None
    ops = (int(ValueToConstantInt(o).getValue().getZExtValue()) for o in ops)
    if name:
        return b.CreateCastFromHFloatTmp(srcArg, *ops, name)
    else:
        return b.CreateCastFromHFloatTmp(srcArg, *ops)


OP_CAST_FROM_HFLOATTMP = HOperatorDefLlvm(castFromHFloatTmp, _llvmCastFromHFloatTmp, False, idStr="OP_CAST_FROM_HFLOATTMP")

