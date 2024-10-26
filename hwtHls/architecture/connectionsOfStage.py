from collections import OrderedDict
from typing import Optional, List, Tuple, Union

from hwt.code import Or, SwitchLogic
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIO import HwIO
from hwt.pyUtils.setList import SetList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeFsmStateEn, \
    HlsNetNodeStageAck
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtLib.handshaked.streamNode import ValidReadyTuple
from hwtLib.logic.rtlSignalBuilder import RtlSignalBuilder


class OrMemberList():
    """
    Container of ORed flags.
    """

    def __init__(self, data:List[RtlSignal]):
        self.data = data

    def resolve(self) -> RtlSignal:
        assert self.data
        if len(self.data) == 1:
            return self.data[0]

        return Or(*self.data)


InterfaceOrReadWriteNodeOrValidReadyTuple = Union[HwIO, HlsNetNodeRead, HlsNetNodeWrite, ValidReadyTuple]

# class IORecord:
#    """
#    :ivar validReadyTupleUsedInSyncGeneration: is used when synchronization is generated.
#    :ivar validReadyTuplePhysicallyPresent: is used to store valid/ready signals for IO which do not use valid/ready signal
#        for handshake synchronization but the has mentioned signals.
#    :ivar validHasCustomDriver: if True the valid driver is not not generated
#    :ivar readyHasCustomDriver: if True the ready driver is not not generated
#    """
#
#    def __init__(self, firstSeenIoNode: Union[HlsNetNodeRead, HlsNetNodeWrite],
#                  ioInterface:Optional[Union[HwIO, HlsNetNodeWrite]],
#                  validReadyTupleUsedInSyncGeneration: ValidReadyTuple,
#                  ioUniqueKey: InterfaceOrReadWriteNodeOrValidReadyTuple,
#                  validReadyTuplePhysicallyPresent: ValidReadyTuple,
#                  validHasCustomDriver:bool,
#                  readyHasCustomDriver:bool):
#        self.node = firstSeenIoNode
#        assert ioInterface is None or isinstance(ioInterface, (HwIO, RtlSignalBase, HlsNetNodeWrite)), ioInterface
#        self.io = ioInterface
#        self.validReady = validReadyTupleUsedInSyncGeneration
#        self.ioUniqueKey = ioUniqueKey
#        self.validReadyPresent = validReadyTuplePhysicallyPresent
#        assert validReadyTuplePhysicallyPresent[0] is not None, (validReadyTuplePhysicallyPresent, "1 should be used instead of None")
#        assert validReadyTuplePhysicallyPresent[1] is not None, (validReadyTuplePhysicallyPresent, "1 should be used instead of None")
#
#        self.validHasCustomDriver = validHasCustomDriver
#        self.readyHasCustomDriver = readyHasCustomDriver
#
#
# EnableReadyTuple = Tuple[Optional[AnyHValue], Optional[RtlSignalBase]]
# EnableValidTuple = Tuple[Optional[AnyHValue], Optional[RtlSignalBase]]


class ConnectionsOfStage():
    """
    This object is a container of meta-information for synchronization generation for
    a single clock pipeline stage pipeline stage or FSM state.

    # :ivar inputs: a :var:`~.IORecordTuple` for every input channels to this stage
    # :ivar outputs: equivalent of inputs for outputs
    :ivar signals: all TimeIndependentRtlResourceItem instances generated in this pipeline stage/FSM state
    :ivar inputs_extraCond: extraCond condition for inputs which specifies when the data should be received from channel
    :ivar outputs_extraCond: inputs_extraCond equivalent for outputs

    :ivar pipelineSyncIn: The read for a channel which holds information if the implicit input data for this stage are valid.
        Used to implement "valid" for pipelines. 
    :ivar syncNode: optional StreamNode instance which was used to generate synchronization
    :ivar stageAck: optional signal which is 1 if this stage is working
    :ivar stageEnable: optional signal which is 1 if this stage is allowed to perform its function
    :ivar stateChangeDependentDrives: list of HdlStatement which should be wrapped under the condition that
        this state is enabled in FSM
    #:ivar finalInputs: collected enable, ready tuples from all io nodes
    #:ivar finalOutputs: collected enable, valid tuples from all io nodes
    """

    def __init__(self, parent: "ArchElement", clkIndex: int):
        self.parent = parent
        self.clkIndex = clkIndex
        # self.inputs: SetList[IORecord] = SetList()
        # self.outputs: SetList[IORecord] = SetList()
        self.signals: SetList[TimeIndependentRtlResourceItem] = SetList()
        # self.inputs_extraCond: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, OrMemberList] = {}
        # self.outputs_extraCond: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, OrMemberList] = {}
        # self.ioMuxes: OrderedDict[HwIO, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]] = OrderedDict()
        self.fsmIoMuxCases: OrderedDict[Union[HlsNetNodeRead, HlsNetNodeWrite, HwIO],
                                         List[Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite],  # node accessing IO
                                              Optional[RtlSignal],  # rtl node enable signal
                                              Optional[RtlSignal],  # rtl node ready for reads, valid for writes, should be asserted 1 if enable==1
                                              List[HdlStatement]],  # rtl statements produced by the node which are implementing the node
                                              ]] = {}
        # :note: ready/valid is not assigned from enable immediately because if there will be mux of variants we want it to be assigned
        # 1 in each case and not enable as if it there was just a single mux case
        self.pipelineSyncIn: Optional["HlsNetNodeReadForwardedge"] = None
        self.fsmStateAckNode: Optional[HlsNetNodeStageAck] = None
        self.fsmStateEnNode: Optional[HlsNetNodeFsmStateEn] = None
        self.fsmStateWriteNode: Optional[HlsNetNodeFsmStateWrite] = None
        self.stageAck: Optional[RtlSignal] = None
        self.stageEnable: Optional[RtlSignal] = None
        self.stateChangeDependentDrives: List[HdlStatement] = []
        self.stateDependentDrives: List[HdlStatement] = []

        # self.finalInputs: List[EnableReadyTuple] = []
        # self.finalOutputs: List[EnableValidTuple] = []

    def isUnused(self):
        return (
            # not self.inputs and
            # not self.outputs and
            # not self.signals and # unused at the beginning still may have signals which are coming from outside
            # not self.inputs_extraCond and
            # not self.outputs_extraCond and
            # not self.ioMuxes and
            not self.fsmIoMuxCases and
            not self.pipelineSyncIn and
            not self.fsmStateAckNode and
            not self.fsmStateEnNode and
            not self.stageAck and
            not self.stageEnable and
            not self.stateChangeDependentDrives and
            not self.stateDependentDrives  # and
            # not self.finalInputs and
            # not self.finalOutputs
        )

    def merge(self, other: "ConnectionsOfStage"):
        "merge other to self"
        # self.inputs.extend(other.inputs)
        # self.outputs.extend(other.outputs)
        self.signals.extend(other.signals)
        # for dstDict, srcDict in [
        #    (self.inputs_extraCond, other.inputs_extraCond),
        #    (self.outputs_extraCond, other.outputs_extraCond)]:
        #    for k, v in srcDict.items():
        #        cur = dstDict.get(k, None)
        #        if cur is None:
        #            dstDict[k] = v
        #        else:
        #            cur.extend(v)

        assert self.pipelineSyncIn is None
        assert self.stageAck is None
        assert other.stageAck is None
        assert self.stageEnable is None
        assert other.stageEnable is None
        self.stateChangeDependentDrives.extend(other.stateChangeDependentDrives)
        self.stateDependentDrives.extend(other.stateDependentDrives)
        # assert not self.ioMuxes
        assert not self.fsmIoMuxCases
        # assert not other.ioMuxes
        # assert not self.finalInputs
        # assert not other.finalInputs
        # assert not self.finalOutputs
        # assert not other.finalOutputs

    def getRtlStageAckSignal(self):
        ack = self.stageAck
        if ack is None:
            # forward declaration
            ack = self.parent._sig(f"{self.parent.namePrefix}_st{self.clkIndex:d}_ack")
            self.stageAck = ack
        return ack

    def getRtlStageEnableSignal(self):
        en = self.stageEnable
        if en is None:
            # forward declaration
            en = self.parent._sig(f"{self.parent.namePrefix}_st{self.clkIndex:d}_en")
            self.stageEnable = en
        return en

    # @staticmethod
    # def _rtlChannelSyncFinalizeFlag(parentHwModule: HwModule,
    #                                flagDict: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, OrMemberList],
    #                                flagsDictKey: InterfaceOrReadWriteNodeOrValidReadyTuple,
    #                                baseName:Optional[str],
    #                                flagName:Optional[str],
    #                                defaultVal: int,
    #                                dbgAddSignalNamesToSync: bool,
    #                                dbgExplicitlyNamedSyncSignals: Optional[Set[RtlSignal]]) -> Optional[RtlSignal]:
    #    flagBundle = flagDict.get(flagsDictKey, None)
    #    if flagBundle is None or not flagBundle:
    #        return None
    #
    #    flag = flagBundle.resolve()
    #
    #    if flag is None:
    #        return None
    #
    #    elif isinstance(flag, HBitsConst):
    #        assert int(flag) == defaultVal, (baseName, flagName, flag,
    #            "Enable condition is never satisfied, channel would be always disabled, (this should have been optimized out)")
    #        return None
    #
    #    else:
    #        assert isinstance(flag, (RtlSignal, HwIOSignal)), (baseName, flagName, flag)
    #        if dbgAddSignalNamesToSync and baseName is not None and baseName is not flagName:
    #            newName = f"{baseName:s}_{flagName:s}"
    #            flag = rename_signal(parentHwModule, flag, newName)
    #            dbgExplicitlyNamedSyncSignals.add(flag)
    #
    #        return flag

    # def rtlChannelSyncFinalize(self, parentHwModule: HwModule, dbgAddSignalNamesToSync:bool,
    #                            dbgExplicitlyNamedSyncSignals: Optional[Set[RtlSignal]]):
    #    """
    #    Before this function all concurrent IOs and their conditions are collected.
    #    In this function we resolve final enable conditions for all IOs and HwIO instances.
    #    """
    #    assert not self.finalInputs, (self, self.finalInputs)
    #    assert not self.finalOutputs, (self, self.finalOutputs)
    #
    #    if not self.inputs and not self.outputs:
    #        assert not self.inputs_extraCond, (self, self.inputs_extraCond)
    #        assert not self.outputs_extraCond, (self, self.outputs_extraCond)
    #        return
    #
    #    masters = self.finalInputs
    #    slaves = self.finalOutputs
    #
    #    seen: Set[InterfaceOrReadWriteNodeOrValidReadyTuple] = set()
    #    # :attention: It is important that outputs are iterated first, because if IO is
    #    # in inputs and outputs it needs to be slave and we are using first found and then
    #    # we are using seen set to filter already seen
    #    for masterOrSlaveList, ioList in ((slaves, self.outputs),
    #                                      (masters, self.inputs),):
    #        for ioRecord in ioList:
    #            ioRecord: IORecord
    #            node: Union[HlsNetNodeRead, HlsNetNodeWrite] = ioRecord.node
    #            hwIO: Optional[HwIO] = ioRecord.io
    #            flagsDictKey: InterfaceOrReadWriteNodeOrValidReadyTuple = ioRecord.ioUniqueKey
    #            assert not node._isBlocking, ("At this point all nodes should be converted to non-blocking and all other related"
    #                                          "should have a custom extraCond which takes this node in account", node)
    #            if flagsDictKey in seen:
    #                continue
    #            else:
    #                seen.add(flagsDictKey)
    #
    #            if hwIO is None or not isinstance(hwIO, (HwIOBase, RtlSignalBase)):
    #                baseName = node.name
    #            else:
    #                baseName = hwIO._name
    #
    #            # resolve conditions for IO as input and output (some IO may be both)
    #            inputExtraCond = self._rtlChannelSyncFinalizeFlag(
    #                parentHwModule, self.inputs_extraCond, flagsDictKey, baseName, "extraCond", 1,
    #                dbgAddSignalNamesToSync, dbgExplicitlyNamedSyncSignals)
    #            outputExtraCond = self._rtlChannelSyncFinalizeFlag(
    #                parentHwModule, self.outputs_extraCond, flagsDictKey, baseName, "extraCond", 1,
    #                dbgAddSignalNamesToSync, dbgExplicitlyNamedSyncSignals)
    #
    #            extraCond = RtlSignalBuilder.buildOrOptional(inputExtraCond, outputExtraCond)
    #            if extraCond is not None:
    #                if isinstance(extraCond, HBitsConst):
    #                    assert int(extraCond) == 1, (node, "Must be 1 otherwise IO is never activated")
    #                    extraCond = None
    #
    #            valid, ready = ioRecord.validReady
    #            _valid, _ready = ioRecord.validReadyPresent
    #            if isinstance(node, HlsNetNodeRead):
    #                assert valid == 1, ("ready should not be used in sync tuple and should be present"
    #                                    " only in ioRecord.validReadyPresent", node, valid)
    #                if not ioRecord.validHasCustomDriver and not (ready == 1):
    #                    masterOrSlaveList.append((extraCond, ready))
    #            else:
    #                assert ready == 1, ("ready should not be used in sync tuple and should be present"
    #                                " only in ioRecord.validReadyPresent", node, ready)
    #                if not ioRecord.readyHasCustomDriver and not (valid == 1):
    #                    masterOrSlaveList.append((extraCond, valid,))

    # def rtlAllocSync(self):
    #    """
    #    [todo] remove and use only logic generated by SyncLowering
    #    Driver ready/valid of IO from an enable flag computed for it.
    #    """
    #    res = []
    #    for en, ready in self.finalInputs:
    #        if en is None:
    #            en = 1
    #        res.append(ready(en))
    #    for en, valid in self.finalOutputs:
    #        if en is None:
    #            en = 1
    #        res.append(valid(en))
    #    return res

    # def rtlAllocIoMux(self):
    #    """
    #    [todo] remove and use only logic generated by IoPortPrivatization
    #    After all read/write nodes constructed all RTL create a HDL switch to select RTL which should be active.
    #    """
    #    for muxCases in self.ioMuxes.values():
    #        if len(muxCases) == 1:
    #            if isinstance(muxCases[0][0], HlsNetNodeWrite):
    #                caseList = muxCases[0][1]
    #                assert isinstance(caseList, list), (caseList.__class__, caseList)
    #                yield caseList
    #            else:
    #                assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
    #                # no MUX needed and we already merged the synchronization
    #        else:
    #            if isinstance(muxCases[0][0], HlsNetNodeWrite):
    #                # create a write MUX
    #                rtlMuxCases = []
    #                for w, stms in muxCases:
    #                    assert w.skipWhen is None, ("This port should be already lowered by RtlArchPassSyncLower", w)
    #                    assert w._forceEnPort is None, ("This port should be already lowered by RtlArchPassSyncLower", w)
    #                    # assert w._mayFlushPort is None, ("This port should be already lowered by RtlArchPassSyncLower", w)
    #
    #                    caseCond = None
    #                    extraCond = self.rtlAllocHlsNetNodeInDriverIfExists(w.extraCond)
    #                    if extraCond is not None:
    #                        caseCond = extraCond.data
    #
    #                    if isinstance(caseCond, HBitsConst):
    #                        assert int(caseCond) == 1, (w, "If ack=0 this means that channel is always stalling")
    #                        caseCond = None
    #
    #                    assert caseCond is not None, ("Because write object do not have any condition it is not possible to resolve which value should be MUXed to output interface", muxCases[0][0].dst)
    #                    rtlMuxCases.append((caseCond, stms))
    #
    #                stms = rtlMuxCases[0][1]
    #                # create default case to prevent lath in HDL
    #                if isinstance(stms, HdlAssignmentContainer):
    #                    defaultCase = [stms.dst(None), ]
    #                else:
    #                    defaultCase = [asig.dst(None) for asig in stms]
    #                yield SwitchLogic(rtlMuxCases, default=defaultCase)
    #            else:
    #                assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
    #                # no MUX needed and we already merged the synchronization

    def rtlAllocIoMux(self):
        """
        After all read/write nodes constructed all RTL create a HDL switch to select RTL which should be active.
        """
        for muxCases in self.fsmIoMuxCases.values():
            if len(muxCases) == 1:
                node, cond, enableOut, caseStatements = muxCases[0]
                assert isinstance(caseStatements, list), (caseStatements.__class__, caseStatements)
                if isinstance(node, HlsNetNodeWrite):
                    if enableOut is not None:
                        caseStatements = [enableOut(1 if cond is None else cond), ] + caseStatements
                    if caseStatements:
                        yield caseStatements
                else:
                    assert isinstance(node, HlsNetNodeRead), muxCases
                    if enableOut is None:
                        yield caseStatements
                    else:
                        yield [enableOut(1 if cond is None else cond), ] + caseStatements
                    # no MUX needed and we already merged the synchronization
            else:
                if isinstance(muxCases[0][0], HlsNetNodeWrite):
                    # create a write MUX
                    rtlMuxCases = []
                    for w, cond, enableOut, stms in muxCases:
                        assert w.skipWhen is None, ("This port should be already lowered by RtlArchPassSyncLower", w)
                        assert w._forceEnPort is None, ("This port should be already lowered by RtlArchPassSyncLower", w)
                        # assert w._mayFlushPort is None, ("This port should be already lowered by RtlArchPassSyncLower", w)

                        if cond is not None:
                            cond = cond.data

                        if isinstance(cond, HBitsConst):
                            assert int(cond) == 1, (w, "If ack=0 this means that channel is always stalling")
                            cond = None

                        assert cond is not None, ("Because write object do not have any condition it is not possible to resolve which value should be MUXed to output interface", muxCases[0][0].dst)
                        if enableOut is not None:
                            stms = [enableOut(1), ] + stms
                        rtlMuxCases.append((cond, [enableOut(1), ] + stms))

                    _, _, enableOut, stms = rtlMuxCases[0]
                    # create default case to prevent lath in HDL
                    defaultCase = []
                    if enableOut is not None:
                        defaultCase.append(enableOut(0))
                    if isinstance(stms, HdlAssignmentContainer):
                        defaultCase.append(stms.dst(None))
                    else:
                        defaultCase.extend(asig.dst(None) for asig in stms)
                    yield SwitchLogic(rtlMuxCases, default=defaultCase)
                else:
                    assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
                    en = None
                    enableOut = None
                    for r, cond, enableOut, caseStatements in muxCases:
                        assert not caseStatements, r
                        if enableOut is None:
                            break
                        if cond is None:
                            en = None
                            break
                        else:
                            en = RtlSignalBuilder.buildOrOptional(en, cond)
                    if enableOut is not None:
                        yield [enableOut(1 if en is None else en), ]

                    # no MUX needed and we already merged the synchronization

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

