from itertools import chain
from typing import List, Optional, Union, Tuple, Generator

from hwt.hdl.types.hdlType import HdlType
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedulableNode
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


def _tupleWithoutItemOnIndex(arr: tuple, index: int):
    return tuple(item for i, item in enumerate(arr) if i != index)


def _tupleAppend(arr: tuple, v:int):
    return tuple(chain(arr, (v,)))


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

    def getInputDtype(self, i:int) -> HdlType:
        return self.dependsOn[i]._dtype

    def _removeInput(self, i: int):
        """
        :attention: does not disconnect the input
        """
        self.dependsOn.pop(i)
        self._inputs.pop(i)
        for inp in self._inputs[i:]:
            inp.in_i -= 1

        if self.realization is not None:
            self.inputClkTickOffset = _tupleWithoutItemOnIndex(self.inputClkTickOffset, i)
            self.inputWireDelay = _tupleWithoutItemOnIndex(self.inputWireDelay, i)
            if self.scheduledIn is not None:
                self.scheduledIn = _tupleWithoutItemOnIndex(self.scheduledIn, i)

    def _removeOutput(self, i: int):
        """
        :attention: does not disconnect the output
        """
        self.usedBy.pop(i)
        self._outputs.pop(i)
        for out in self._outputs[i:]:
            out.out_i -= 1

        if self.realization is not None:
            self.outputClkTickOffset = _tupleWithoutItemOnIndex(self.outputClkTickOffset, i)
            self.outputWireDelay = _tupleWithoutItemOnIndex(self.outputWireDelay, i)
            if self.scheduledOut is not None:
                self.scheduledOut = _tupleWithoutItemOnIndex(self.scheduledOut, i)

    def _addInput(self, name: Optional[str], addDefaultScheduling=False) -> HlsNetNodeIn:
        if addDefaultScheduling:
            if self.realization is not None:
                self.inputClkTickOffset = _tupleAppend(self.inputClkTickOffset, 0)
                self.inputWireDelay = _tupleAppend(self.inputWireDelay, 0)
                if self.scheduledIn is not None:
                    self.scheduledIn = _tupleAppend(self.scheduledIn, self.scheduledZero)
        else:
            assert self.realization is None, self

        i = HlsNetNodeIn(self, len(self._inputs), name)
        self._inputs.append(i)
        self.dependsOn.append(None)
        return i

    def _addOutput(self, t: HdlType, name: Optional[str], addDefaultScheduling=False) -> HlsNetNodeOut:
        if addDefaultScheduling:
            if self.realization is not None:
                self.outputClkTickOffset = _tupleAppend(self.outputClkTickOffset, 0)
                self.outputWireDelay = _tupleAppend(self.outputWireDelay, 0)
                if self.scheduledOut is not None:
                    self.scheduledOut = _tupleAppend(self.scheduledOut, self.scheduledZero)
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

    def allocateRtlInstanceOutDeclr(self, allocator: "ArchElement", o: HlsNetNodeOut, startTime: int) -> TimeIndependentRtlResource:
        assert allocator.netNodeToRtl.get(o, None) is None, ("Must not be redeclared", allocator, o)
        try:
            assert startTime >= o.obj.scheduledOut[o.out_i], (o, startTime, o.obj.scheduledOut[o.out_i])
        except:
            print("[debug] to rm")
            raise
        if len(self._outputs) == 1:
            assert o.out_i == 0, o
            if self.name:
                name = f"{allocator.namePrefix}forwardDeclr_{self.name:s}"
            else:
                name = f"{allocator.namePrefix}forwardDeclr_{self._id:d}"
        else:
            if self.name and o.name:
                name = f"{allocator.namePrefix}forwardDeclr_{self.name:s}_{o.name:s}"
            elif self.name:
                name = f"{allocator.namePrefix}forwardDeclr_{self.name:s}_{o.out_i:d}"
            elif o.name:
                name = f"{allocator.namePrefix}forwardDeclr_{self._id:d}_{o.name:s}"
            else:
                name = f"{allocator.namePrefix}forwardDeclr_{self._id:d}_{o.out_i:d}"
        s = allocator._sig(name, o._dtype)
        res = allocator.netNodeToRtl[o] = TimeIndependentRtlResource(s, startTime, allocator, False)
        return res

    def allocateRtlInstance(self, allocator: "ArchElement"):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def createSubNodeRefrenceFromPorts(self, beginTime: float, endTime: float,
                                       inputs: List[HlsNetNodeIn], outputs: List[HlsNetNodeOut]) -> "HlsNetNodePartRef":
        raise NotImplementedError(
            "Override this method in derived class", self)

    def partsComplement(self, otherParts: List["HlsNetNodePartRef"]):
        """
        Create a parts which contains the rest of node not contained in otherParts.
        """
        raise NotImplementedError(
            "Override this method in derived class", self)

    def _get_rtl_context(self):
        return self.netlist.ctx

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        """
        Iter nodes which are not connected but are somehow related.
        (The information is used for visualization purposes.)
        """
        return
        yield


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

    def iterChildReads(self):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def iterChildWrites(self):
        raise NotImplementedError(
            "Override this method in derived class", self)
