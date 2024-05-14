from typing import Union

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import Handshaked, HandshakeSync, RdSynced, VldSynced, \
    Signal
from hwt.interfaces.structIntf import StructIntf
from hwt.interfaces.unionIntf import UnionSink, UnionSource
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi_intf_common import Axi_hs


ANY_HLS_STREAM_INTF_TYPE = Union[Handshaked, Axi_hs, VldSynced,
                                 HsStructIntf, RtlSignal, Signal,
                                 UnionSink, UnionSource]

ANY_SCALAR_INT_VALUE = Union[RtlSignal, HValue, Signal, SsaValue]


def _getNativeInterfaceWordType(i: Interface) -> HdlType:
    if isinstance(i, (Handshaked, Axi_hs, HsStructIntf, HandshakeSync)):
        return Bits(i._bit_length() - 2)
    elif isinstance(i, (RdSynced, VldSynced)):
        return Bits(i._bit_length() - 1)
    elif isinstance(i, (Signal, RtlSignal, StructIntf)):
        return i._dtype
    else:
        raise NotImplementedError(i)
