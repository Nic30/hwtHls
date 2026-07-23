from typing import Union

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.hdlType import HdlType, default_explicit_cast_fn
from hwt.hwIOs.hwIOStruct import HwIOStruct
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp, HFloatTmpConfigHdlType
from tests.math.hFloatTmp.hFloatTmpCast import OP_CAST_TO_HFLOATTMP


def IEEE754Fp_explicit_cast(curType: IEEE754Fp, val: Union["IEEE754FpConst", HwIOStruct, "IEEE754FpRtlSignal"], toType: HdlType):
    if toType == HFloatTmp:
        cfg = HFloatTmpConfigHdlType.from_py(curType._cfg)
        # if isinstance(val, RtlSignalBase):
        #    try:
        #        d = val.singleDriver()
        #    except SignalDriverErr:
        #        d = None
        #    if d is not None and isinstance(d, HOperatorNode) and\
        #        d.operator == OP_CAST_FROM_HFLOATTMP and \
        #        d.operands[1:] == (cfg,):
        #        # try reduce useless cast from, to HFloatTmp
        #        return d.operands[0]
        #
        val = val.pack()
        return HOperatorNode.withRes(OP_CAST_TO_HFLOATTMP, (
            val, cfg,),
            HFloatTmp)
    return  default_auto_cast_fn(curType, val, toType)
