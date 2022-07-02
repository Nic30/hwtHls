from typing import Type, Dict, Optional, List, Tuple, Union, Sequence

from hwt.code import And
from hwt.hdl.statements.statement import HdlStatement
from hwt.interfaces.std import HandshakeSync, Handshaked, VldSynced, RdSynced, \
    Signal, BramPort_withoutClk
from hwt.interfaces.structIntf import StructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtLib.amba.axi_intf_common import Axi_hs
from hwtLib.handshaked.streamNode import StreamNode


def get_sync_type(intf: Interface) -> Type[Interface]:
    """
    resolve which primitive type of synchronization is the interface using
    """

    if isinstance(intf, HandshakeSync):
        return Handshaked
    elif isinstance(intf, (VldSynced, BramPort_withoutClk)):
        return VldSynced
    elif isinstance(intf, RdSynced):
        return RdSynced
    else:
        assert isinstance(intf, (Signal, RtlSignal, StructIntf)), intf
        return Signal


class SkipWhenMemberList(TimeIndependentRtlResourceItem):

    def __init__(self, data:List[TimeIndependentRtlResourceItem]):
        self.data = data

    def resolve(self) -> RtlSignal:
        assert self.data
        return And(*(d.data for d in self.data))

    def is_rlt_register(self) -> bool:
        raise NotImplementedError()


class ExtraCondMemberList(TimeIndependentRtlResourceItem):
    """
    Container of tuples skipWhen, extraCond flags for stream synchronization.
    """

    def __init__(self, data:List[Tuple[Optional[TimeIndependentRtlResourceItem], TimeIndependentRtlResourceItem]]):
        self.data = data

    def resolve(self) -> RtlSignal:
        assert self.data
        if len(self.data) == 1:
            return self.data[0][1].data

        extraCond = None
        for skipWhen, curExtraCond in self.data:
            if skipWhen is None:
                if extraCond is None:
                    extraCond = curExtraCond.data
                else:
                    extraCond = extraCond | curExtraCond.data
            else:
                if extraCond is None:
                    extraCond = ~skipWhen.data & curExtraCond.data
                else:
                    extraCond = extraCond | (~skipWhen.data & curExtraCond.data)

        return extraCond

    def is_rlt_register(self) -> bool:
        raise NotImplementedError()


class ConnectionsOfStage():
    """
    Container of connections of pipeline stage or FSM state
    """

    def __init__(self):
        self.inputs: UniqList[Interface] = UniqList()
        self.outputs: UniqList[Interface] = UniqList()
        self.signals: UniqList[TimeIndependentRtlResourceItem] = UniqList()
        self.io_skipWhen: Dict[Interface, SkipWhenMemberList] = {}
        self.io_extraCond: Dict[Interface, ExtraCondMemberList] = {}
        self.sync_node: Optional[StreamNode] = None
        self.stDependentDrives: List[HdlStatement] = []


class SignalsOfStages(List[UniqList[TimeIndependentRtlResourceItem]]):
    """
    Container of signals in :class:`~.ConnectionsOfStage` instances.
    """

    def __init__(self, normalizedClkPeriod: int, initVals=None):
        self.normalizedClkPeriod = normalizedClkPeriod
        list.__init__(self)
        if initVals:
            for v in initVals:
                assert isinstance(v, UniqList) or v is None, v
                self.append(v)

    def getForTime(self, t: int):
        i = int(t // self.normalizedClkPeriod)
        try:
            if i < 0:
                raise IndexError()
            res = self[i]
        except IndexError:
            raise IndexError("Asking for an object which is scheduled by a different region", t, i, len(self), self) from None
        if res is None:
            raise IndexError("Asking for an object in time which is not managed by this architectural element", t, i, [int(item is not None) for item in self])

        return res


def setNopValIfNotSet(intf: Interface, nopVal, exclude: List[Interface]):
    if intf in exclude:
        return
    elif intf._interfaces:
        for _intf in intf._interfaces:
            setNopValIfNotSet(_intf, nopVal, exclude)
    elif intf._sig._nop_val is NOT_SPECIFIED:
        intf._sig._nop_val = intf._dtype.from_py(nopVal)


def extract_control_sig_of_interface(
        intf: Union[HandshakeSync, RdSynced, VldSynced, RtlSignalBase, Signal,
                    Tuple[Union[int, RtlSignalBase, Signal],
                          Union[int, RtlSignalBase, Signal]]]
        ) -> Tuple[Union[int, RtlSignalBase, Signal],
                   Union[int, RtlSignalBase, Signal]]:
    if isinstance(intf, tuple):
        assert len(intf) == 2
        return intf
    elif isinstance(intf, (Handshaked, HandshakeSync, Axi_hs)):
        return intf
        # return (intf.vld, intf.rd)
    elif isinstance(intf, VldSynced):
        return (intf.vld, 1)
    elif isinstance(intf, BramPort_withoutClk):
        return (intf.en, 1)
    elif isinstance(intf, RdSynced):
        return (1, intf.rd)
    elif isinstance(intf, (RtlSignalBase, Signal, StructIntf)):
        return (1, 1)
    else:
        raise TypeError("Unknown synchronisation of ", intf)


def getIntfSyncSignals(intf: Interface) -> Tuple[Interface, ...]:
    if isinstance(intf, Axi_hs):
        return (intf.ready, intf.valid)
    elif isinstance(intf, (HandshakeSync, Handshaked)):
        return (intf.rd, intf.vld)
    elif isinstance(intf, (RtlSignal, Signal, StructIntf)):
        return ()
    elif isinstance(intf, VldSynced):
        return (intf.vld,)
    elif isinstance(intf, RdSynced):
        return (intf.rd,)
    else:
        raise NotImplementedError(intf)


def resolveStrongestSyncType(current_sync: Type[Interface], io_channels: Sequence[Interface]):
    for op in io_channels:
        sync_type = get_sync_type(op)
        if sync_type is Handshaked or current_sync is RdSynced and sync_type is VldSynced:
            current_sync = Handshaked
        elif sync_type is RdSynced:
            if current_sync is Handshaked:
                pass
            elif current_sync is VldSynced:
                current_sync = Handshaked
            else:
                current_sync = sync_type

        elif sync_type is VldSynced:
            if current_sync is Handshaked:
                pass
            elif current_sync is RdSynced:
                current_sync = Handshaked
            else:
                current_sync = sync_type

    return current_sync
