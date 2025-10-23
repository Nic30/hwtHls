from typing import Union

from hwt.code import Concat
from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.mainBases import RtlSignalBase, HwIOBase
from hwt.pyUtils.setList import SetList
from hwt.synthesizer.rtlLevel.exceptions import SignalDriverErr
from hwtHls.llvm.llvmIr import IRBuilder, Value, Twine, HFloatTmpConfig, LlvmCompilationBundle
from hwtHls.netlist.builder import _replaceOutPortWith
from hwtHls.ssa.translation.toLlvm import HOperatorDefLlvm
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp, HFloatTmpConfigHdlType, \
    _HFloatTmpConfigHdlTypeConst


def _extractHFloatTmpParamsFromFriendType(t: Union[IEEE754Fp, HFixedPointQ, HBits]):
    if isinstance(t, (IEEE754Fp, HFixedPointQ)):
        return t._cfg
    elif isinstance(t, HBits):
        isInQFormat = False
        supportSubnormal = False
        hasSign = bool(t.signed)
        exponentWidth = t.bit_length()
        mantissaWidth = 0
    else:
        raise TypeError(t)

    return HFloatTmpConfig(isInQFormat, exponentWidth, mantissaWidth, supportSubnormal, hasSign)


# see "denormal-fp-math"
def castToHFloatTmp(op: RtlSignalBase[Union[IEEE754Fp, HFixedPointQ, HBits]], *args):
    assert not args, "This is mean to be used as a separator in expressions and it is not meant to be evaluated."
    t = op._dtype
    cfg = _extractHFloatTmpParamsFromFriendType(t)
    cfg = HFloatTmpConfigHdlType.from_py(cfg)
    if isinstance(op, RtlSignalBase):
        if isinstance(op, HConst):
            if isinstance(t, HFixedPointQ):
                return HFloatTmp.from_py(float(op))
            elif isinstance(t, HBits):
                return HFloatTmp.from_py(float(int(op)))

        try:
            d = op.singleDriver()
        except SignalDriverErr:
            d = None
        if d is not None and isinstance(d, HOperatorNode) and\
            d.operator == OP_CAST_FROM_HFLOATTMP and \
            d.operands[1:] == (cfg,):
            # try reduce useless cast from, to HFloatTmp
            return d.operands[0]

    if isinstance(t, IEEE754Fp):
        if isinstance(op, HConst):
            return HFloatTmp.from_py(float(op))

        tmp = Concat(op.sign, op.exponent, op.mantissa)
    elif isinstance(op, HwIOBase):
        tmp = op._sig
    else:
        tmp = op

    assert isinstance(tmp, (RtlSignalBase, HConst)), tmp
    return HOperatorNode.withRes(OP_CAST_TO_HFLOATTMP,
                                 (tmp, cfg),
                                 HFloatTmp)


def _llvmCastToHFloatTmp(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, srcArg: Value, cfg:HFloatTmpConfig, name:Twine) -> Value:
    assert srcArg.getType().isIntegerTy(), (srcArg, srcArg.getType())
    return b.CreateCastToHFloatTmp(srcArg, cfg, name)


OP_CAST_TO_HFLOATTMP = HOperatorDefLlvm(castToHFloatTmp, _llvmCastToHFloatTmp, False, idStr="OP_CAST_TO_HFLOATTMP")


def castFromHFloatTmp(op: RtlSignalBase[Union[IEEE754Fp, HFixedPointQ, HBits]], t: Union[IEEE754Fp, HFixedPointQ, HBits]) \
        ->Union[RtlSignalBase[HFloatTmp], HConst[HFloatTmp]]:
    assert op._dtype == HFloatTmp, (op, op._dtype)
    cfg = _extractHFloatTmpParamsFromFriendType(t)
    cfg = HFloatTmpConfigHdlType.from_py(cfg)
    if isinstance(op, HConst):
        return t.from_py(float(op) if op._is_full_valid() else None)

    elif isinstance(t, HStruct):
        res = HOperatorNode.withRes(OP_CAST_FROM_HFLOATTMP, (
            op, cfg), HBits(t.bit_length()))
        return res._reinterpret_cast(t)

    else:
        return HOperatorNode.withRes(OP_CAST_FROM_HFLOATTMP, (
            op, cfg), t)


def _llvmCastFromHFloatTmp(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, srcArg: Value, cfg: _HFloatTmpConfigHdlTypeConst, name: Twine) -> Value:
    assert srcArg.getType().isDoubleTy(), srcArg
    return b.CreateCastFromHFloatTmp(srcArg, cfg, name)


OP_CAST_FROM_HFLOATTMP = HOperatorDefLlvm(castFromHFloatTmp, _llvmCastFromHFloatTmp, False, idStr="OP_CAST_FROM_HFLOATTMP")


def _llvmCastHFloatTmpToHFloatTmp(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, srcArg: Value, cfg: _HFloatTmpConfigHdlTypeConst, name: Twine) -> Value:
    assert srcArg.getType().isDoubleTy(), srcArg
    return b.CreateCastHFloatTmpToHFloatTmp(srcArg, cfg, name)


def castHFloatTmpToHFloatTmp(op: RtlSignalBase[Union[IEEE754Fp, HFixedPointQ, HBits]],
                              t: Union[IEEE754Fp, HFixedPointQ, HBits]) \
        ->Union[RtlSignalBase[HFloatTmp], HConst[HFloatTmp]]:
    assert op._dtype == HFloatTmp, (op, op._dtype)
    srcCfg = _extractHFloatTmpParamsFromFriendType(op._dtype)
    srcCfg = HFloatTmpConfigHdlType.from_py(srcCfg)

    dstCfg = _extractHFloatTmpParamsFromFriendType(t)
    dstCfg = HFloatTmpConfigHdlType.from_py(dstCfg)

    return HOperatorNode.withRes(OP_CAST_HFLOATTMP_TO_HFLOATTMP, (
        op, srcCfg, dstCfg), t)


# cast HFloatTmp to HFloatTmp with possibly different configuration of precision and bitwidth
def _OP_CAST_HFLOATTMP_TO_HFLOATTMP_runSimplifyRules(n: "HlsNetNodeOperator", worklist: SetList["HlsNetNode"]):
    cfgIn, cfgOut = n.operatorSpecialization
    if cfgIn == cfgOut:
        _replaceOutPortWith(n._outputs[0], n.dependsOn[0], worklist)
        return True
    return False


OP_CAST_HFLOATTMP_TO_HFLOATTMP = HOperatorDefLlvm(castHFloatTmpToHFloatTmp, _llvmCastHFloatTmpToHFloatTmp, False, idStr="OP_CAST_HFLOATTMP_TO_HFLOATTMP",
                                                  runSimplifyRules=_OP_CAST_HFLOATTMP_TO_HFLOATTMP_runSimplifyRules)
