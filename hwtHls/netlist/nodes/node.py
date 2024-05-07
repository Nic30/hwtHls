from copy import copy
from enum import Enum
from itertools import chain, islice
from typing import List, Optional, Union, Tuple, Generator

from hwt.hdl.types.hdlType import HdlType
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedulableNode, SchedTime
from hwtHls.netlist.observableList import ObservableList
from hwtHls.netlist.scheduler.clk_math import offsetInClockCycle
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


def _tupleWithoutItemOnIndex(arr: tuple, index: int):
    return tuple(item for i, item in enumerate(arr) if i != index)


def _tupleAppend(arr: tuple, v:int):
    return tuple(chain(arr, (v,)))


def _tupleSetItem(arr: tuple, index: int, replacement):
    return tuple(replacement if i == index else item for i, item in enumerate(arr))


class NODE_ITERATION_TYPE(Enum):
    PREORDER, POSTORDER, OMMIT_PARENT = range(3)


class _HlsNetNodeDeepcopyNil():
    pass


class HlsNetNode(SchedulableNode):
    """
    Abstract class for nodes in circuit which are subject to HLS scheduling

    :ivar name: optional suggested name for this object (for debugging purposes)
    :ivar netlist: reference on parent netlist
    :ivar usedBy: for each output list of operation and its input index which are using this output
    :ivar dependsOn: for each input operation and index of its output with data required
        to perform this operation
    :ivar scheduledIn: final scheduled time of start of operation for each input
    :ivar scheduledOut: final scheduled time of end of operation for each output

    :attention: inputs must be sorted 1st must have lowest latency

    :ivar inputWireDelay: combinational latency before first register
        in component for this operation (for each input)
    :ivar outputWireDelay: combinational latency after last register
        in component for this operation (for each output, 0 corresponds to a same time as input[0])
    :ivar OutputClkTickOffset: number of clk cycles for data to get from input
        to output (for each output, 0 corresponds to a same clock cycle as input[0])

    :ivar _inputs: list of inputs of this node
    :ivar _outputs: list of inputs of this node
    """

    def __init__(self, netlist: "HlsNetlistCtx", name: str=None):
        self.name = name
        self._id = netlist.getUniqId()
        SchedulableNode.__init__(self, netlist)
        self._isRtlAllocated = False

    def clone(self, memo: dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNode", bool]:
        """
        :returns: new object and flag which is True if object was newly constructed 
        """
        d = id(self)
        y = memo.get(d, _HlsNetNodeDeepcopyNil)
        if y is not _HlsNetNodeDeepcopyNil:
            return y, False

        y: HlsNetNode = copy(self)
        y._id = self.netlist.getUniqId()
        memo[d] = y
        # now we must also copy all mutable properties specific to this node
        y._inputs = [HlsNetNodeIn(y, i.in_i, i.name) for i in self._inputs]
        y._outputs = ObservableList(HlsNetNodeOut(y, o.out_i, o._dtype, o.name) for o in self._outputs)
        # self._outputs: ObservableList[HlsNetNodeOut] = ObservableList()
        y.usedBy = [[u.obj.clone(memo, True)[0]._inputs[u.in_i] if keepTopPortsConnected else [] for u in users]
                    for users in self.usedBy]
        y.dependsOn = ObservableList(None if dep is None or not keepTopPortsConnected
                                          else dep.obj.clone(memo, True)[0]._outputs[dep.out_i]
                                     for dep in self.dependsOn)
        return y, True

    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        self.usedBy = None
        self.dependsOn = None
        self._inputs = None
        self._outputs = None
        self.scheduledZero = None
        self.scheduledIn = None
        self.scheduledOut = None

    def getInputDtype(self, index: int) -> HdlType:
        return self.dependsOn[index]._dtype

    def _removeInput(self, index: int):
        """
        :attention: does not disconnect the input
        """
        self.dependsOn.pop(index)
        self._inputs.pop(index)
        for inp in islice(self._inputs, index, None):
            inp.in_i -= 1

        if self.realization is not None:
            self.inputClkTickOffset = _tupleWithoutItemOnIndex(self.inputClkTickOffset, index)
            self.inputWireDelay = _tupleWithoutItemOnIndex(self.inputWireDelay, index)
            if self.scheduledIn is not None:
                self.scheduledIn = _tupleWithoutItemOnIndex(self.scheduledIn, index)

    def _removeOutput(self, index: int):
        """
        :attention: does not disconnect the output
        """
        self.usedBy.pop(index)
        self._outputs.pop(index)
        for out in islice(self._outputs, index, None):
            out.out_i -= 1

        if self.realization is not None:
            self.outputClkTickOffset = _tupleWithoutItemOnIndex(self.outputClkTickOffset, index)
            self.outputWireDelay = _tupleWithoutItemOnIndex(self.outputWireDelay, index)
            if self.scheduledOut is not None:
                self.scheduledOut = _tupleWithoutItemOnIndex(self.scheduledOut, index)

    def _addInput(self, name: Optional[str], addDefaultScheduling=False,
                  inputClkTickOffset:int=0, inputWireDelay:int=0) -> HlsNetNodeIn:
        if addDefaultScheduling:
            if self.realization is not None:
                self.inputClkTickOffset = _tupleAppend(self.inputClkTickOffset, inputClkTickOffset)
                self.inputWireDelay = _tupleAppend(self.inputWireDelay, inputWireDelay)
                if self.scheduledIn is not None:
                    netlist = self.netlist
                    clkPeriod = netlist.normalizedClkPeriod
                    schedZero = self.scheduledZero
                    if inputClkTickOffset == 0:
                        assert offsetInClockCycle(schedZero, clkPeriod) >= inputWireDelay, (
                            offsetInClockCycle(schedZero, clkPeriod), inputWireDelay,
                            schedZero, clkPeriod)
                        time = schedZero
                    else:
                        if self.realization.mayBeInFFStoreTime:
                            epsilon = 0
                            ffdelay = 0
                        else:
                            ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
                            epsilon = netlist.scheduler.epsilon
                        time = self._scheduleAlapCompactionMultiClockInTime(self.scheduledZero, netlist.normalizedClkPeriod,
                                                                             inputClkTickOffset, epsilon, ffdelay)
                    time -= inputWireDelay
                    self.scheduledIn = _tupleAppend(self.scheduledIn, time)
        else:
            assert self.realization is None, self

        i = HlsNetNodeIn(self, len(self._inputs), name)
        self._inputs.append(i)
        self.dependsOn.append(None)
        return i

    def _addOutput(self, t: HdlType, name: Optional[str], addDefaultScheduling=False,
                   outputClkTickOffset:int=0, outputWireDelay:int=0) -> HlsNetNodeOut:
        if addDefaultScheduling:
            if self.realization is not None:
                self.outputClkTickOffset = _tupleAppend(self.outputClkTickOffset, outputClkTickOffset)
                self.outputWireDelay = _tupleAppend(self.outputWireDelay, outputWireDelay)
                if self.scheduledOut is not None:
                    time = self._scheduleAlapCompactionMultiClockOutTime(self.scheduledZero,
                                                                         self.netlist.normalizedClkPeriod,
                                                                         outputClkTickOffset)
                    time += outputWireDelay
                    self.scheduledOut = _tupleAppend(self.scheduledOut, time)
        else:
            assert self.realization is None, self

        o = HlsNetNodeOut(self, len(self._outputs), t, name)
        self._outputs.append(o)
        self.usedBy.append([])
        return o

    def deleteRealization(self):
        self.realization = None
        self.inputClkTickOffset = None
        self.inputWireDelay = None
        self.outputWireDelay = None
        self.outputClkTickOffset = None
        self.isMulticlock = None

    def assignRealization(self, r: OpRealizationMeta):
        # [todo] move inputWireDelay, outputWireDelay checks for clkPeriod there
        schedulerResolution: float = self.netlist.scheduler.resolution
        self.realization = r
        self.inputClkTickOffset = HlsNetNode_numberForEachInput(self, r.inputClkTickOffset)
        if self.inputClkTickOffset:
            for c in self.inputClkTickOffset:
                assert c >= 0 and c >= self.inputClkTickOffset[0]

        self.inputWireDelay = HlsNetNode_numberForEachInputNormalized(self, r.inputWireDelay, schedulerResolution)
        if self.inputWireDelay:
            for l in self.inputWireDelay:
                assert l <= self.inputWireDelay[0]

        self.outputWireDelay = HlsNetNode_numberForEachOutputNormalized(self, r.outputWireDelay, schedulerResolution)
        self.outputClkTickOffset = HlsNetNode_numberForEachOutput(self, r.outputClkTickOffset)
        self.isMulticlock = any(self.inputClkTickOffset) or any(self.outputClkTickOffset)
        iCnt = len(self._inputs)
        assert len(self.inputWireDelay) == iCnt
        assert len(self.inputClkTickOffset) == iCnt
        oCnt = len(self._outputs)
        assert len(self.outputWireDelay) == oCnt
        assert len(self.outputClkTickOffset) == oCnt

        return self

    def resolveRealization(self):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def rtlAllocOutDeclr(self, allocator: "ArchElement", o: HlsNetNodeOut, startTime: SchedTime) -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated, ("It is pointless to ask for forward declaration if node is already RTL allocated", self, "in", allocator)
        assert allocator.netNodeToRtl.get(o, None) is None, ("Must not be redeclared", allocator, o)
        assert startTime >= o.obj.scheduledOut[o.out_i], (o, startTime, o.obj.scheduledOut[o.out_i])
        assert not HdlType_isVoid(o._dtype), (o, "Signals of void types should not have representation in RTL")

        name = f"{o.getPrettyName():s}_forwardDeclr"
        s = allocator._sig(name, o._dtype)
        tir = allocator.rtlRegisterOutputRtlSignal(o, s, False, True, False)
        return tir

    def getAllocatedRTL(self, allocator: "ArchElement"):
        assert self._isRtlAllocated, self
        return []

    def rtlAlloc(self, allocator: "ArchElement"):
        assert not self._isRtlAllocated, self
        raise NotImplementedError(
            "Override this method in derived class", self)

    def createSubNodeRefrenceFromPorts(self, beginTime: SchedTime, endTime: SchedTime,
                                       inputs: List[HlsNetNodeIn], outputs: List[HlsNetNodeOut]) -> "HlsNetNodePartRef":
        raise NotImplementedError(
            "Override this method in derived class", self)

    def partsComplement(self, otherParts: List["HlsNetNodePartRef"]):
        """
        Create a parts which contains the rest of node not contained in otherParts.
        """
        raise NotImplementedError(
            "Override this method in derived class", self)

    def iterAllNodesFlat(self, itTy: NODE_ITERATION_TYPE):
        yield self

    def _get_rtl_context(self):
        return self.netlist.ctx

    def debugIterShadowConnectionDst(self) -> Generator[Tuple["HlsNetNode", bool], None, None]:
        """
        Iter nodes which are not connected but are somehow related.
        The bool in tuple is isExplicitBackedge flag.

        :note: The information is used for visualization purposes.
            The isExplicitBackedge flag is improves readability of graph.
            As it makes edges to follow natural direction which results in better consistency of layers.
        """
        return
        yield

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {self._id:d}>"


def HlsNetNode_numberForEachInput(node: HlsNetNode, val: Union[float, Tuple[float]]) -> Tuple[Union[int, float]]:
    if isinstance(val, (float, int)):
        return tuple(val for _ in node._inputs)
    else:
        val = list(val)
        assert len(val) == len(node._inputs), (node, val, node._inputs)
        return val


def HlsNetNode_numberForEachOutput(node: HlsNetNode, val: Union[float, Tuple[float]]) -> Tuple[Union[int, float]]:
    if isinstance(val, (float, int)):
        return tuple(val for _ in node._outputs)
    else:
        val = tuple(val)
        assert len(val) == len(node._outputs)
        return val


def HlsNetNode_numberForEachInputNormalized(node: HlsNetNode, val: Union[float, Tuple[float]], scale: float) -> Tuple[int]:
    if isinstance(val, (float, int)):
        return tuple(int(val // scale) for _ in node._inputs)
    else:
        val = tuple(val)
        assert len(val) == len(node._inputs), (node, val, node._inputs)
        return tuple(int(v // scale) for v in val)


def HlsNetNode_numberForEachOutputNormalized(node: HlsNetNode, val: Union[float, Tuple[float]], scale: float) -> Tuple[int]:
    if isinstance(val, (float, int)):
        return tuple(int(val // scale) for _ in node._outputs)
    else:
        val = list(val)
        assert len(val) == len(node._outputs)
        return tuple(int(v // scale) for v in val)


class HlsNetNodePartRef(HlsNetNode):
    """
    Abstract class for references of :class:`~.HlsNetNode` parts.

    :note: The reason for this class is that we need to split nodes during analysis passes when we can not modify nodes.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentNode: HlsNetNode, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self.parentNode = parentNode
        # deleting because real value is stored in parent node and this is just reference
        self._inputs = None
        self._outputs = None
        self.dependsOn = None
        self.usedBy = None
        self.scheduledIn = None
        self.scheduledOut = None
        self._subNodes: Optional["HlsNetlistClusterSearch"] = None
