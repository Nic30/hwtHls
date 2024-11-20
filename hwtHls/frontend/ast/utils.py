from typing import Union

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.hwIOUnion import HwIOUnionSink, HwIOUnionSource
from hwt.hwIOs.std import HwIODataRdVld, HwIORdVldSync, HwIODataRd, HwIODataVld, \
    HwIOSignal
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.llvm.llvmIr import Value
from hwtHls.netlist.hdlTypeVoid import HVoidExternData
from hwtLib.amba.axi_common import Axi_hs


ANY_HLS_STREAM_INTF_TYPE = Union[HwIODataRdVld, Axi_hs, HwIODataVld,
                                 HwIOStructRdVld, RtlSignal, HwIOSignal,
                                 HwIOUnionSink, HwIOUnionSource]

ANY_SCALAR_INT_VALUE = Union[RtlSignal, HConst, HwIOSignal, Value]


def _getNativeInterfaceWordType(i: HwIO) -> HdlType:
    if isinstance(i, (HwIODataRdVld, Axi_hs, HwIOStructRdVld, HwIORdVldSync)):
        w = i._bit_length() - 2
        if w == 0:
            return HVoidExternData
        return HBits(w)
    elif isinstance(i, (HwIODataRd, HwIODataVld)):
        w = i._bit_length() - 1
        if w == 0:
            return HVoidExternData
        return HBits(w)
    elif isinstance(i, (HwIOSignal, RtlSignal, HwIOStruct)):
        return i._dtype
    else:
        raise NotImplementedError(i)
