from typing import Union

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.const import HConst
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIODataRdVld, HwIORdVldSync, HwIODataRd, HwIODataVld, \
    HwIOSignal
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.hwIOUnion import HwIOUnionSink, HwIOUnionSource
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi_common import Axi_hs


ANY_HLS_STREAM_INTF_TYPE = Union[HwIODataRdVld, Axi_hs, HwIODataVld,
                                 HwIOStructRdVld, RtlSignal, HwIOSignal,
                                 HwIOUnionSink, HwIOUnionSource]

ANY_SCALAR_INT_VALUE = Union[RtlSignal, HConst, HwIOSignal, SsaValue]


def _getNativeInterfaceWordType(i: HwIO) -> HdlType:
    if isinstance(i, (HwIODataRdVld, Axi_hs, HwIOStructRdVld, HwIORdVldSync)):
        return HBits(i._bit_length() - 2)
    elif isinstance(i, (HwIODataRd, HwIODataVld)):
        return HBits(i._bit_length() - 1)
    elif isinstance(i, (HwIOSignal, RtlSignal, HwIOStruct)):
        return i._dtype
    else:
        raise NotImplementedError(i)
