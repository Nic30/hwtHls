from typing import Union

from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType, default_auto_cast_fn, \
    default_reinterpret_cast_fn
from hwt.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.exceptions import SignalDriverErr
from hwtHls.llvm.llvmIr import Value, IRBuilder, Twine
from hwtHls.ssa.translation.toLlvm import HOperatorDefLlvm
from hwtLib.types.ctypes import uint8_t
from tests.math.fixp.fixedpoint import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpCast import OP_CAST_TO_HFLOATTMP, \
    OP_CAST_FROM_HFLOATTMP


def castHFixedPointQ(curType: HFixedPointQ, val: Union["HFixedPointQConst", "HFixedPointQRtlSignal"], toType: HdlType):
    if toType == HFloatTmp:
        supportSubnormal = b0
        hasIsNaN = b0
        hasIsInf = b0
        hasIs1 = b0
        hasIs0 = b0
        isInQFromat = b1
        hasSign = b1 if curType.signed else b0
        exponentWidth = uint8_t.from_py(curType.int_bit_length)
        mantissaWidth = uint8_t.from_py(curType.frac_bit_length)
        if isinstance(val, RtlSignalBase):
            try:
                d = val.singleDriver()
            except SignalDriverErr:
                d = None
            if d is not None and isinstance(d, HOperatorNode) and\
                d.operator == OP_CAST_FROM_HFLOATTMP and \
                d.operands[1:] == (exponentWidth, mantissaWidth,
                                   isInQFromat, supportSubnormal, hasSign,
                                   hasIsNaN, hasIsInf, hasIs1, hasIs0):
                # try reduce useless cast from, to HFloatTmp
                return d.operands[0]

        return HOperatorNode.withRes(OP_CAST_TO_HFLOATTMP, (
            val, exponentWidth, mantissaWidth,
            isInQFromat, supportSubnormal, hasSign, hasIsNaN, hasIsInf, hasIs1, hasIs0),
            HFloatTmp)

    return default_auto_cast_fn(curType, val, toType)


def reinterpretCastHFixedPointQ(curType: HFixedPointQ, val: Union["HFixedPointQConst", "HFixedPointQRtlSignal"], toType: HdlType):
    if isinstance(toType, HBits) and toType.bit_length() == curType.bit_length():
        return HOperatorNode.withRes(OP_REINTEPRET_CAST_HFIXEDPOINTQ_TO_HBITS, (val,),
            toType)

    return default_reinterpret_cast_fn(curType, val, toType)


def _llvmCastHFixedPointQToHBits(b:IRBuilder, instr: HOperatorNode, srcArg: Value, name: Twine) -> Value:
    return srcArg


OP_REINTEPRET_CAST_HFIXEDPOINTQ_TO_HBITS = HOperatorDefLlvm(lambda x: x._reinterpret_cast(HBits(x._dtype.bit_length())),
                                                            _llvmCastHFixedPointQToHBits, False,
                                                            idStr="OP_REINTEPRET_CAST_HFIXEDPOINTQ_TO_HBITS")

