from typing import Dict, Optional, List, Tuple, Union

from hwt.code import And
from hwt.hdl.statements.statement import HdlStatement
from hwt.pyUtils.setList import SetList
from hwt.hwIO import HwIO
from hwt.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtLib.handshaked.streamNode import StreamNode, ValidReadyTuple
from hwtLib.logic.rtlSignalBuilder import RtlSignalBuilder
from hwt.mainBases import RtlSignalBase


class SkipWhenMemberList():

    def __init__(self, data:List[RtlSignal]):
        self.data = data

    def resolve(self) -> RtlSignal:
        assert self.data
        return And(*(d for d in self.data))


class ExtraCondMemberList():
    """
    Container of tuples skipWhen, extraCond flags for stream synchronization.
    """

    def __init__(self, data:List[Tuple[Optional[RtlSignal], RtlSignal]]):
        self.data = data

    def resolve(self) -> RtlSignal:
        assert self.data
        if len(self.data) == 1:
            return self.data[0][1]

        extraCond = None
        for skipWhen, curExtraCond in self.data:
            extraCond = RtlSignalBuilder.buildOrWithNegatedMaskedOptional(extraCond, curExtraCond, skipWhen)

        return extraCond


InterfaceOrReadWriteNodeOrValidReadyTuple = Union[HwIO, HlsNetNodeRead, HlsNetNodeWrite, ValidReadyTuple]


class IORecord:
    """
    :ivar validReadyTupleUsedInSyncGeneration: is used when synchronization is generated.
    :ivar validReadyTuplePhysicallyPresent: is used to store valid/ready signals for IO which do not use valid/ready signal
        for handshake synchronization but the has mentioned signals.
    :ivar validHasCustomDriver: if True the valid driver is not not generated
    :ivar readyHasCustomDriver: if True the ready driver is not not generated
    """

    def __init__(self, firstSeenIoNode: Union[HlsNetNodeRead, HlsNetNodeWrite],
                  ioInterface:Optional[Union[HwIO, HlsNetNodeWrite]],
                  validReadyTupleUsedInSyncGeneration: ValidReadyTuple,
                  ioUniqueKey: InterfaceOrReadWriteNodeOrValidReadyTuple,
                  validReadyTuplePhysicallyPresent: ValidReadyTuple,
                  validHasCustomDriver:bool,
                  readyHasCustomDriver:bool):
        self.node = firstSeenIoNode
        assert ioInterface is None or isinstance(ioInterface, (HwIO, RtlSignalBase, HlsNetNodeWrite)), ioInterface
        self.io = ioInterface
        self.validReady = validReadyTupleUsedInSyncGeneration
        self.ioUniqueKey = ioUniqueKey
        self.validReadyPresent = validReadyTuplePhysicallyPresent
        assert validReadyTuplePhysicallyPresent[0] is not None, (validReadyTuplePhysicallyPresent, "1 should be used instead of None")
        assert validReadyTuplePhysicallyPresent[1] is not None, (validReadyTuplePhysicallyPresent, "1 should be used instead of None")

        self.validHasCustomDriver = validHasCustomDriver
        self.readyHasCustomDriver = readyHasCustomDriver


class ConnectionsOfStage():
    """
    This object is a container of meta-information for synchronization generation for a single clock pipeline stage pipeline stage or FSM state.

    :ivar inputs: a :var:`~.IORecordTuple` for every input channels to this stage
    :ivar outputs: equivalent of inputs for outputs
    :ivar signals: all TimeIndependentRtlResourceItem instances generated in this pipeline stage/FSM state
    :ivar inputs_skipWhen: skipWhen condition for inputs which specifies when the synchronization should wait for this channel
    :ivar inputs_extraCond: extraCond condition for inputs which specifies when the data should be received from channel
    :ivar outputs_skipWhen: inputs_skipWhen equivalent for outputs
    :ivar outputs_extraCond: inputs_extraCond equivalent for outputs
    :ivar implicitSyncFromPrevStage: The read for a channel which holds information if the implicit input data for this stage are valid.
        Used to implement "valid" for pipelines. 
    :ivar syncNode: optional StreamNode instance which was used to generate synchronization
    :ivar syncNodeAck: optional signal which is 1 if this stage is working
    :ivar stageEnable: optional signal which is 1 if this stage is allowed to perform its function
    :ivar stDependentDrives: list of HdlStatement which should be wrapped under the condition that this state is enabled in FSM
    """

    def __init__(self, parent: "ArchElement", clkIndex: int):
        self.parent = parent
        self.clkIndex = clkIndex
        self.inputs: SetList[IORecord] = SetList()
        self.outputs: SetList[IORecord] = SetList()
        self.signals: SetList[TimeIndependentRtlResourceItem] = SetList()
        self.inputs_skipWhen: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, SkipWhenMemberList] = {}
        self.inputs_extraCond: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, ExtraCondMemberList] = {}
        self.outputs_skipWhen: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, SkipWhenMemberList] = {}
        self.outputs_extraCond: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, ExtraCondMemberList] = {}
        self.ioMuxes: Dict[HwIO, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]] = {}
        self.ioMuxesKeysOrdered: SetList[HwIO] = SetList()

        self.implicitSyncFromPrevStage: Optional["HlsNetNodeReadForwardedge"] = None
        self.syncNode: Optional[StreamNode] = None
        self.syncNodeAck: Optional[RtlSignal] = None
        self.stageEnable: Optional[RtlSyncSignal] = None
        self.stDependentDrives: List[HdlStatement] = []

    def isUnused(self):
        return (
            not self.inputs and
            not self.outputs and
            # not self.signals and # unused at the beginning still may have signals which are coming from outside
            not self.inputs_extraCond and
            not self.inputs_skipWhen and
            not self.outputs_extraCond and
            not self.outputs_skipWhen and
            not self.ioMuxes and
            not self.ioMuxesKeysOrdered and
            not self.implicitSyncFromPrevStage and
            not self.syncNode and
            not self.syncNodeAck and
            not self.stageEnable and
            not self.stDependentDrives)

    def merge(self, other: "ConnectionsOfStage"):
        "merge other to self"
        self.inputs.extend(other.inputs)
        self.outputs.extend(other.outputs)
        self.signals.extend(other.signals)
        self.inputs_skipWhen.update(other.inputs_skipWhen)
        self.inputs_extraCond.update(other.inputs_extraCond)
        self.outputs_skipWhen.update(other.outputs_skipWhen)
        self.outputs_extraCond.update(other.outputs_extraCond)
        assert self.implicitSyncFromPrevStage is None
        assert self.syncNode is None
        assert self.syncNodeAck is None
        assert other.syncNodeAck is None
        assert self.stageEnable is None
        assert other.stageEnable is None
        self.stDependentDrives.extend(other.stDependentDrives)
        assert not self.ioMuxes
        assert not other.ioMuxes
        assert not self.ioMuxesKeysOrdered
        assert not other.ioMuxesKeysOrdered

    def getRtlStageAckSignal(self):
        ack = self.syncNodeAck
        if ack is None:
            # forward declaration
            ack = self.parent._sig(f"{self.parent.name}st{self.clkIndex:d}_ack")
            self.syncNodeAck = ack
        return ack

    def getRtlStageEnableSignal(self):
        en = self.stageEnable
        if en is None:
            # forward declaration
            en = self.parent._sig(f"{self.parent.name}st{self.clkIndex:d}_en")
            self.stageEnable = en
        return en

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.parent} clk:{self.clkIndex}>"


class ConnectionsOfStageList(List[Optional[SetList[ConnectionsOfStage]]]):
    """
    Container of for :class:`~.ConnectionsOfStage` divided into clock cycles.
    """

    def __init__(self, normalizedClkPeriod: SchedTime, initVals=None):
        self.normalizedClkPeriod = normalizedClkPeriod
        list.__init__(self)
        if initVals:
            for v in initVals:
                assert isinstance(v, ConnectionsOfStage) or v is None, v
                self.append(v)

    def getForClkIndex(self, clkIndex: int, allowNone=False) -> Optional[SetList[TimeIndependentRtlResourceItem]]:
        try:
            if clkIndex < 0:
                raise IndexError("Asking for an object in invalid time", clkIndex)
            res = self[clkIndex]
        except IndexError:
            raise IndexError("Asking for an object which is scheduled to different architectural element",
                             clkIndex, len(self), self) from None

        if res is None and not allowNone:
            raise IndexError("Asking for an object in time which is not managed by this architectural element",
                             clkIndex, [int(item is not None) for item in self])

        return res

    def getForTime(self, t: int, allowNone=False) -> Optional[SetList[TimeIndependentRtlResourceItem]]:
        """
        Use time to index in this list.
        :note: entirely same as getForClkIndex just with better error messages
        """
        i = int(t // self.normalizedClkPeriod)
        try:
            if i < 0:
                raise IndexError("Asking for an object in invalid time", t)
            res = self[i]
        except IndexError:
            raise IndexError("Asking for an object which is scheduled to different architectural element",
                             t, i, len(self), self) from None

        if res is None and not allowNone:
            raise IndexError("Asking for an object in time which is not managed by this architectural element",
                             t, i, [int(item is not None) for item in self])

        return res


def setNopValIfNotSet(hwIO: Union[HwIO, RtlSignal], nopVal, exclude: List[HwIO]):
    if hwIO in exclude:
        return
    elif isinstance(hwIO, RtlSignal):
        hwIO._nop_val = hwIO._dtype.from_py(nopVal)

    elif hwIO._hwIOs:
        for cHwIO in hwIO._hwIOs:
            setNopValIfNotSet(cHwIO, nopVal, exclude)

    elif hwIO._sig._nop_val is NOT_SPECIFIED:
        hwIO._sig._nop_val = hwIO._dtype.from_py(nopVal)

