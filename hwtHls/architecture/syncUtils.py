from typing import Tuple, Union, Literal, Sequence

from hwt.interfaces.std import HandshakeSync, Handshaked, \
    Signal, BramPort_withoutClk, RdSync, VldSync
from hwt.interfaces.structIntf import StructIntf
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.io.portGroups import getFirstInterfaceInstance, MultiPortGroup, \
    BankedPortGroup
from hwtLib.amba.axi_intf_common import Axi_hs
from hwtLib.handshaked.streamNode import ValidReadyTuple

SyncOfInterface = Union[Handshaked, HandshakeSync, Axi_hs, ValidReadyTuple]


def getInterfaceSync(
            intf: Union[HandshakeSync, RdSync, VldSync, RtlSignalBase, Signal, SyncOfInterface]
            ) -> SyncOfInterface:
    if isinstance(intf, (Handshaked, HandshakeSync, Axi_hs)):
        return intf
    else:
        return getInterfaceSyncTuple(intf)


def getInterfaceSyncTuple(
            intf: Union[HandshakeSync, RdSync, VldSync, RtlSignalBase, Signal, ValidReadyTuple]
            ) -> ValidReadyTuple:
    if isinstance(intf, tuple):
        # expect ValidReadyTuple
        assert len(intf) == 2, intf
        assert isinstance(intf[0], (int, RtlSignalBase, Signal)), intf
        assert isinstance(intf[1], (int, RtlSignalBase, Signal)), intf
        return intf
    elif isinstance(intf, Axi_hs):
        return (intf.valid, intf.ready)
    elif isinstance(intf, (Handshaked, HandshakeSync)):
        return (intf.vld, intf.rd)
    elif isinstance(intf, VldSync):
        return (intf.vld, 1)
    elif isinstance(intf, BramPort_withoutClk):
        return (intf.en, 1)
    elif isinstance(intf, RdSync):
        return (1, intf.rd)
    elif isinstance(intf, (RtlSignalBase, Signal, StructIntf)):
        return (1, 1)
    else:
        raise TypeError("Unknown synchronization of ", intf)


def getInterfaceSyncSignals(intf: Union[Interface, RtlSignal, MultiPortGroup, BankedPortGroup]) -> Tuple[Interface, ...]:
    intf = getFirstInterfaceInstance(intf)
    if isinstance(intf, Axi_hs):
        return (intf.valid, intf.ready)
    elif isinstance(intf, HandshakeSync):
        return (intf.vld, intf.rd)
    elif isinstance(intf, (RtlSignal, Signal, StructIntf)):
        return ()
    elif isinstance(intf, VldSync):
        return (intf.vld,)
    elif isinstance(intf, RdSync):
        return (intf.rd,)
    elif isinstance(intf, BramPort_withoutClk):
        return (intf.en,)
    else:
        raise NotImplementedError(intf)

