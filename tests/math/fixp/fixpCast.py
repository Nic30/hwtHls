from typing import Union

from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType, default_auto_cast_fn, \
    default_reinterpret_cast_fn, default_reverse_reinterpret_cast_fn
from hwt.mainBases import RtlSignalBase, HwIOBase
from hwt.synthesizer.rtlLevel.exceptions import SignalDriverErr
from hwtHls.llvm.llvmIr import Value, IRBuilder, Twine, HFloatTmpConfig, APFloat, ValueToConstantInt, \
    HFloatTmpSaturation, HFloatTmpRounding, LlvmCompilationBundle
from hwtHls.ssa.translation.toLlvm import HOperatorDefLlvm
from pyMathBitPrecise.bit_utils import mask, get_bit, to_signed
from tests.math.fixp.fixpResize import fixp_resize
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp, HFloatTmpConfigHdlType, \
    _HFloatTmpConfigHdlTypeConst
from tests.math.hFloatTmp.hFloatTmpCast import OP_CAST_TO_HFLOATTMP, \
    OP_CAST_FROM_HFLOATTMP


def HFixedPointQ_explicit_cast(curType: HFixedPointQ, val: Union["HFixedPointQConst", "HFixedPointQRtlSignal"], toType: HdlType):
    if toType == HFloatTmp:
        cfg = HFloatTmpConfigHdlType.from_py(curType._cfg)
        if isinstance(val, HConst):
            return HFloatTmp.from_py(float(val) if val._is_full_valid() else None)

        elif isinstance(val, RtlSignalBase):
            try:
                d = val.singleDriver()
            except SignalDriverErr:
                d = None
            if d is not None and isinstance(d, HOperatorNode) and\
                d.operator == OP_CAST_FROM_HFLOATTMP and \
                d.operands[1:] == (cfg,):
                # try reduce useless cast from, to HFloatTmp
                return d.operands[0]

        return HOperatorNode.withRes(OP_CAST_TO_HFLOATTMP, (
            val, cfg,),
            HFloatTmp)
    elif isinstance(toType, (HFixedPointQ, HBits)):
        # [todo] maybe use OP_CAST_HFLOATTMP instead
        valRaw = val._reinterpret_cast(HBits(val._dtype.bit_length()))
        if isinstance(toType, HBits):
            _toType = HFixedPointQ(toType.bit_length(), 0, bool(toType.signed),
                                   HFloatTmpRounding.ROUND_FLOOR,
                                   HFloatTmpSaturation.SATURATE_NONE)
        else:
            _toType = toType
        resRaw = fixp_resize(valRaw, val._dtype, _toType)
        res = resRaw._reinterpret_cast(toType)
        return res

    return default_auto_cast_fn(curType, val, toType)


def HFixedPointQ_reverse_explicit_cast_HConst(toType: HFixedPointQ, val: Union["RtlSignal", "HConst"], fromType: HdlType):
    if isinstance(fromType, HBits):
        cfg: HFloatTmpConfig = toType._cfg
        srcWidth = fromType.bit_length()
        dstWidth = toType.int_bit_length

        if fromType.signed:
            v = to_signed(val.val, srcWidth)
        else:
            v = val.val
        v = int(cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(float(v))))
        sizeDiff = srcWidth - dstWidth
        # :note: auto_cast from HBits just setting the int part
        #    frac_bits are always defined and the msb bits may be extended if the src type is signed
        vldMask = val.vld_mask
        if fromType.bit_length() == toType.bit_length():
            pass
        elif fromType.signed:
            msbBitsNewlyDefined = get_bit(vldMask, srcWidth - 1)
        else:
            msbBitsNewlyDefined = True

        if msbBitsNewlyDefined and sizeDiff < 0:
            vldMask |= mask(-sizeDiff) << srcWidth

        if dstWidth < srcWidth:
            m = mask(dstWidth)
            vldMask &= m

        vldMask <<= toType.frac_bit_length
        vldMask |= mask(toType.frac_bit_length)

        return toType._from_py(v, vldMask)

    return default_reverse_reinterpret_cast_fn(toType, val, fromType)


def HFixedPointQ_reverse_explicit_cast_RtlSignal(toType: HFixedPointQ, val: Union["RtlSignal", "HConst"], fromType: HdlType):
    if isinstance(fromType, HBits):
        if isinstance(val, HwIOBase):
            val = val._sig
        cfg = HFloatTmpConfigHdlType.from_py(toType._cfg)
        return HOperatorNode.withRes(OP_EXPLICIT_CAST_HBITS_TO_HFIXEDPOINTQ, (val, BIT.from_py(bool(fromType.signed)), cfg),
            toType)

    return default_reverse_reinterpret_cast_fn(toType, val, fromType)


def HBits_explicit_cast_to_HFixedPointQ_llvm(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, srcArg: Value, srcIsSigned:Value, dstCfg: HFloatTmpConfig, name: Twine) -> Value:
    srcTy = srcArg.getType()
    _srcIsSigned = ValueToConstantInt(srcIsSigned)
    assert _srcIsSigned is not None, (srcIsSigned, "must be ConstantInt")

    srcCfg = HFloatTmpConfig(True, srcTy.getIntegerBitWidth(), 0, False,
                             _srcIsSigned.getValue().getZExtValue(),
                             saturation=HFloatTmpSaturation.SATURATE_NONE,
                             rounding=HFloatTmpRounding.ROUND_FLOOR)
    return b.CreateCastHFloatTmpToHFloatTmpRaw(srcArg, srcCfg, dstCfg, name)


def _OP_EXPLICIT_CAST_HBITS_TO_HFIXEDPOINTQ_fn(x, dstCfg: _HFloatTmpConfigHdlTypeConst):
    raise NotImplementedError()


# int to fixed (value stays as llvm integer)
OP_EXPLICIT_CAST_HBITS_TO_HFIXEDPOINTQ = HOperatorDefLlvm(_OP_EXPLICIT_CAST_HBITS_TO_HFIXEDPOINTQ_fn,
                                                      HBits_explicit_cast_to_HFixedPointQ_llvm, False,
                                                      idStr="OP_EXPLICIT_CAST_HBITS_TO_HFIXEDPOINTQ")


def HFixedPointQ_reinterpret_cast_HConst(curType: HFixedPointQ, val: "HFixedPointQConst", toType: HdlType):
    if isinstance(toType, HBits) and toType.bit_length() == curType.bit_length():
        assert isinstance(val.val, int), "expected raw bits of value in HFixedPointQConst val attribute"
        v = val.val if not toType.signed else to_signed(val.val, toType.bit_length())
        return toType.from_py(v, val.vld_mask)

    return default_reinterpret_cast_fn(curType, val, toType)


def HFixedPointQ_reinterpret_cast_RtlSignal(curType: HFixedPointQ, val: "HFixedPointQRtlSignal", toType: HdlType):
    if isinstance(toType, HBits) and toType.bit_length() == curType.bit_length():
        if isinstance(val, HwIOBase):
            val = val._sig

        return HOperatorNode.withRes(OP_REINTEPRET_CAST_HFIXEDPOINTQ_TO_HBITS, (val,),
            toType)

    return default_reinterpret_cast_fn(curType, val, toType)


def HFixedPointQ_reinterpret_cast_llvm(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, srcArg: Value, name: Twine) -> Value:
    # does not change bitwidth just the meaning of type is different
    return srcArg


OP_REINTEPRET_CAST_HFIXEDPOINTQ_TO_HBITS = HOperatorDefLlvm(lambda x: x._reinterpret_cast(HBits(x._dtype.bit_length())),
                                                            HFixedPointQ_reinterpret_cast_llvm, False,
                                                            idStr="OP_REINTEPRET_CAST_HFIXEDPOINTQ_TO_HBITS")


def HFixedPointQ_reverse_reinterpret_cast_HConst(toType: HFixedPointQ, val: Union["RtlSignal", "HConst"], fromType: HdlType):
    if isinstance(fromType, HBits) and toType.bit_length() == fromType.bit_length():
        return toType._from_py(val.val, val.vld_mask)

    return default_reverse_reinterpret_cast_fn(toType, val, fromType)


def HFixedPointQ_reverse_reinterpret_cast_RtlSignal(toType: HFixedPointQ, val: Union["RtlSignal", "HConst"], fromType: HdlType):
    if isinstance(fromType, HBits) and toType.bit_length() == fromType.bit_length():
        if isinstance(val, HwIOBase):
            val = val._sig
        cfg = HFloatTmpConfigHdlType.from_py(toType._cfg)
        return HOperatorNode.withRes(OP_REINTEPRET_CAST_HBITS_TO_HFIXEDPOINTQ, (val, cfg),
            toType)

    return default_reverse_reinterpret_cast_fn(toType, val, fromType)


def HBits_reinterpret_cast_to_HFixedPointQ_llvm(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, srcArg: Value, dstCfg: HFloatTmpConfig, name: Twine) -> Value:
    return srcArg


def _OP_REINTEPRET_CAST_HBITS_TO_HFIXEDPOINTQ_fn(x, dstCfg: _HFloatTmpConfigHdlTypeConst):
    raise NotImplementedError()


# take raw bits of HBits and interpret it as HFixedPointQ value
OP_REINTEPRET_CAST_HBITS_TO_HFIXEDPOINTQ = HOperatorDefLlvm(_OP_REINTEPRET_CAST_HBITS_TO_HFIXEDPOINTQ_fn,
                                                            HBits_reinterpret_cast_to_HFixedPointQ_llvm, False,
                                                            idStr="OP_REINTEPRET_CAST_HBITS_TO_HFIXEDPOINTQ")
