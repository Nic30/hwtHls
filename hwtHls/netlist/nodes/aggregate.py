from collections import deque
from typing import List, Optional, Tuple, Generator, Set, Deque

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode, _tupleAppend, \
    NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, OutputMinUseTimeGetter, \
    SchedTime
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwtHls.typingFuture import override


class HlsNetNodeAggregatePortIn(HlsNetNode):
    """
    A node which represents an input port to a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentIn: HlsNetNodeIn, dtype: HdlType, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addOutput(dtype, name)
        self.parentIn = parentIn

    @override
    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def _setScheduleZero(self, t: SchedTime):
        self.scheduledZero = t
        self.scheduledIn = ()
        self.scheduledOut = (t,)

    @override
    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]],
                     beginOfFirstClk: SchedTime,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        """
        Copy the ASAP time from outside output to this input port
        """
        # resolve time for input of this cluster
        if self.scheduledOut is None:
            if self.realization is None:
                self.resolveRealization()
            dep = self.parentIn.obj.dependsOn[self.parentIn.in_i]
            t = dep.obj.scheduleAsap(pathForDebug, beginOfFirstClk, outputTimeGetter)[dep.out_i]
            if outputTimeGetter is None:
                t = dep.obj.scheduleAsap(pathForDebug, beginOfFirstClk, None)[dep.out_i]  # + epsilon
            else:
                t = outputTimeGetter(dep, pathForDebug, beginOfFirstClk)

            self._setScheduleZero(t)
        return self.scheduledOut

    @override
    def rtlAlloc(self, allocator: "ArchElement"):
        assert not self._isRtlAllocated, self
        assert len(self._outputs) == 1, self
        op_out = self._outputs[0]
        parentInPort = self.parentIn
        parentDrive = parentInPort.obj.dependsOn[parentInPort.in_i]
        assert op_out._dtype == parentDrive._dtype, ("Aggregate port must be of same time as port which drives it",
                                                     self, parentDrive, op_out._dtype, parentDrive._dtype)
        rtl = allocator.netNodeToRtl[parentDrive]  # this port must be forward declared,
        # so it is guaranteed that the RTL is present
        allocator.netNodeToRtl[op_out] = rtl
        self._isRtlAllocated = True
        return rtl

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} i={self.parentIn.in_i} parent={self.parentIn.obj._id:d}>"


class HlsNetNodeAggregatePortOut(HlsNetNode):
    """
    A node which represents an output port from a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentOut: HlsNetNodeIn, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addInput(name)
        self.parentOut = parentOut

    def _setScheduleZero(self, t: SchedTime):
        self.scheduledZero = t
        self.scheduledIn = (t,)
        self.scheduledOut = ()

    @override
    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    @override
    def scheduleAlapCompaction(self, endOfLastClk: SchedTime,
                               outputMinUseTimeGetter:Optional[OutputMinUseTimeGetter]) -> Generator["HlsNetNode", None, None]:
        """
        Copy ALAP time from uses of outside port
        """
        if outputMinUseTimeGetter is not None:
            raise NotImplementedError()
        uses = self.parentOut.obj.usedBy[self.parentOut.out_i]
        t = min(u.obj.scheduledIn[u.in_i] for u in uses)
        self._setScheduleZero(t)
        return
        yield

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} i={self.parentOut.out_i} parent={self.parentOut.obj._id:d}>"


class HlsNetNodeAggregate(HlsNetNode):
    """
    Container of cluster of nodes.

    :note: Usually used as a container of nodes which do have some special scheduling requirements.

    :ivar isFragmented: flag which is True if the node was split on parts and if parts should be used for allocation instead
        of this whole object.
    :ivar _inputsInside: a list of nodes which are representing an input port of this node inside of this node
    :ivar _outputsInside: a list of nodes which are representing an output port of this node inside of this node
    """

    def __init__(self, netlist: "HlsNetlistCtx", subNodes: UniqList[HlsNetNode], name: str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        assert isinstance(subNodes, UniqList), subNodes
        self._subNodes = subNodes
        self._isFragmented = False
        self._inputsInside: List[HlsNetNodeAggregatePortIn] = []
        self._outputsInside: List[HlsNetNodeAggregatePortOut] = []

    @override
    def _addOutput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeOut, HlsNetNodeIn]:
        o = HlsNetNode._addOutput(self, t, name)
        oPort = HlsNetNodeAggregatePortOut(self.netlist, o, name)
        self._outputsInside.append(oPort)
        self._subNodes.append(oPort)
        if time is None:
            assert self.scheduledOut is None
        else:
            oPort._setScheduleZero(time)
            if self.scheduledOut:
                self.scheduledOut = _tupleAppend(self.scheduledOut, time)
            else:
                self.scheduledOut = (time,)

        return o, oPort._inputs[0]

    @override
    def _addInput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeIn, HlsNetNodeOut]:
        i = HlsNetNode._addInput(self, name)
        iPort = HlsNetNodeAggregatePortIn(self.netlist, i, t, name)
        if time is None:
            assert self.scheduledIn is None
        else:
            iPort._setScheduleZero(time)
            if self.scheduledIn:
                self.scheduledIn = _tupleAppend(self.scheduledIn, time)
            else:
                self.scheduledIn = (time,)

        self._inputsInside.append(iPort)
        self._subNodes.append(iPort)
        return i, iPort._outputs[0]

    @override
    def _removeOutput(self, index:int):
        HlsNetNode._removeOutput(self, index)
        outInside = self._outputsInside.pop(index)
        assert outInside is not None
        self._subNodes.remove(outInside)

    @override
    def _removeInput(self, index:int):
        HlsNetNode._removeInput(self, index)
        inInside = self._inputsInside.pop(index)
        assert inInside is not None
        self._subNodes.remove(inInside)

    @override
    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        HlsNetNode.destroy(self)
        self._subNodes = None
        self._totalInputCnt = None
        self._inputsInside = None
        self._outputsInside = None

    @override
    def copyScheduling(self, schedule: SchedulizationDict):
        for n in self._subNodes:
            n.copyScheduling(schedule)
        schedule[self] = (self.scheduledZero, self.scheduledIn, self.scheduledOut)

    @override
    def setScheduling(self, schedule: SchedulizationDict):
        for n in self._subNodes:
            n.setScheduling(schedule)
        (self.scheduledZero, self.scheduledIn, self.scheduledOut) = schedule[self]

    @override
    def moveSchedulingTime(self, offset: SchedTime):
        HlsNetNode.moveSchedulingTime(self, offset)
        for n in self._subNodes:
            n.moveSchedulingTime(offset)

    @override
    def checkScheduling(self):
        HlsNetNode.checkScheduling(self)
        for n in self._subNodes:
            n.checkScheduling()

        # assert that io of this node has correct times
        for outerIn, port in zip(self._inputs, self._inputsInside):
            outerIn: HlsNetNodeIn
            port: HlsNetNodeAggregatePortIn
            outerDep = self.dependsOn[outerIn.in_i]
            outerDepT = outerDep.obj.scheduledOut[outerDep.out_i]
            outerInT = self.scheduledIn[outerIn.in_i]
            assert outerDepT <= outerInT, (outerDepT, outerInT, outerDep, outerIn)
            portT = port.scheduledOut[0]
            assert outerInT <= portT, (outerInT, portT, outerIn, port)

        for outer, port in zip(self._outputs, self._outputsInside):
            outer: HlsNetNodeOut
            port: HlsNetNodeAggregatePortOut
            intern: HlsNetNodeOut = port.dependsOn[0]
            assert outer.obj is self
            assert intern.obj in self._subNodes, (self, intern.obj)
            t = self.scheduledOut[outer.out_i]
            # assert t == intern.obj.scheduledOut[intern.out_i], (intern, t, intern.obj.scheduledOut[intern.out_i])
            assert t == port.scheduledIn[0]

    @override
    def resetScheduling(self):
        for n in self._subNodes:
            n.resetScheduling()
        HlsNetNode.resetScheduling(self)

    def copySchedulingFromChildren(self):
        self.scheduledIn = tuple(i.scheduledOut[0] for i in self._inputsInside)
        self.scheduledOut = tuple(o.scheduledIn[0] for o in self._outputsInside)
        self.scheduledZero = max(self.scheduledIn) if self.scheduledIn else\
                             min(self.scheduledOut) if self.scheduledOut else\
                             min(n.scheduledZero for n in self._subNodes)

    def _getAlapOutsideOutMinUseTime(self,
                                     inPort: HlsNetNodeAggregatePortIn,
                                     endOfLastClk: SchedTime,
                                     currentMinUseTime: SchedTime,
                                     outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]) -> SchedTime:
        assert not any(inPort.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter)), (inPort, "Should only copy input times from outside")
        t = min(currentMinUseTime, inPort.scheduledOut[0])

        if outputMinUseTimeGetter is not None:
            outerOut = inPort.parentIn.obj.dependsOn[inPort.parentIn.in_i]
            t = outputMinUseTimeGetter(outerOut, t)

        return t

    @override
    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]],
                     beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        raise NotImplementedError(
            "Override this method in derived class", self)

    @override
    def scheduleAlapCompaction(self, endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def scheduleAlapCompactionForSubnodes(self, endOfLastClk: SchedTime, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        """
        Run ALAP scheduling for all submodes including HlsNetNodeAggregatePortOut nodes.
        """
        toSearch: Deque[HlsNetNode] = deque()
        toSearchSet: Set[HlsNetNode] = set()
        for oPort in self._outputsInside:
            assert len(oPort.dependsOn) == 1, oPort
            node = oPort.dependsOn[0].obj
            if node not in toSearchSet:
                toSearch.append(node)
                toSearchSet.add(node)

        for node in self._subNodes:
            node: HlsNetNode
            if isinstance(node, HlsNetNodeAggregate) or (
                node.realization is not None and
                    (any(node.inputClkTickOffset) or any(node.outputClkTickOffset))
                    ) or not any(any(users) for users in node.usedBy):
                if node not in toSearchSet:
                    toSearch.append(node)
                    toSearchSet.add(node)

        assert toSearch, self
        while toSearch:
            node0: HlsNetNode = toSearch.popleft()
            toSearchSet.remove(node0)
            assert len(toSearch) == len(toSearchSet), (toSearch, toSearchSet)
            for node1 in node0.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter):
                if node1 not in toSearchSet:
                    toSearch.append(node1)
                    toSearchSet.add(node1)

    @override
    def rtlAllocOutDeclr(self, allocator: "ArchElement", o: HlsNetNodeOut, startTime: SchedTime)\
            ->TimeIndependentRtlResource:
        internOutPort: HlsNetNodeAggregatePortOut = self._outputsInside[o.out_i]
        outOfInternDriverNode: HlsNetNodeOut = internOutPort.dependsOn[0]
        tir = outOfInternDriverNode.obj.rtlAllocOutDeclr(allocator, outOfInternDriverNode, startTime)
        assert o not in allocator.netNodeToRtl, o
        allocator.netNodeToRtl[o] = tir
        return tir

    @override
    def rtlAlloc(self, allocator: "ArchElement"):
        """
        Instantiate layers of bitwise operators. (Just delegation to sub nodes)
        """
        raise AssertionError("This node should be disaggregated before instantiation to avoid"
                             " complicated cases where parts are scattered over many arch elements.")

    def disaggregate(self):
        """
        A reverse operation for :meth:`~.HlsNetlistClusterSearch.substituteWithNode`

        :note: only reconnects the nodes internally stored in this cluster, it does not move nodes anywhere
            (it may be required to add them to nodes list in netlist if they were removed previously)
        """
        assert len(self._inputs) == len(self._inputsInside), (self, len(self._inputs), len(self._inputsInside))
        assert len(self._outputs) == len(self._outputsInside), (self, len(self._outputs), len(self._outputsInside))

        for boundaryIn, inputPort in zip(self._inputs, self._inputsInside):
            boundaryIn: HlsNetNodeIn
            inputPort: HlsNetNodeAggregatePortIn
            # remove boundaryIn from uses of its dependency and add all internal uses instead

            # if external input was substituted we have to also substituted it in internal nodes
            outerOutput = self.dependsOn[boundaryIn.in_i]
            internUses = inputPort.usedBy[0]
            for ii in internUses:
                ii.obj.dependsOn[ii.in_i] = outerOutput

            oldUsedBy = outerOutput.obj.usedBy[outerOutput.out_i]
            usedBy = outerOutput.obj.usedBy[outerOutput.out_i] = [
                i
                for i in oldUsedBy
                if i is not boundaryIn
            ]
            usedBy.extend(internUses)

        for boundaryOut, outPort in zip(self._outputs, self._outputsInside):
            internOutput = outPort.dependsOn[0]
            outerUsedBy = self.usedBy[boundaryOut.out_i]
            for u in outerUsedBy:
                u.obj.dependsOn[u.in_i] = internOutput

            internUsedBy = internOutput.obj.usedBy[internOutput.out_i]
            for u in internUsedBy:
                assert u.obj in self._subNodes, (internOutput, u, "Must be used only inside of cluster")
                if u.obj is outPort:
                    continue
                outerUsedBy.append(u)
            internOutput.obj.usedBy[internOutput.out_i] = outerUsedBy

        for n in self._subNodes:
            if isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)):
                continue
            yield n

    @override
    def iterAllNodesFlat(self, itTy: NODE_ITERATION_TYPE):
        if itTy == NODE_ITERATION_TYPE.PREORDER:
            yield self

        for n in self._subNodes:
            yield from n.iterAllNodesFlat(itTy)

        if itTy == NODE_ITERATION_TYPE.POSTORDER:
            yield self

    def filterNodesUsingSet(self, removed: Set[HlsNetNode], recursive=False):
        if removed:
            for iNode in self._inputsInside:
                if iNode in removed:
                    raise NotImplementedError()

            for oNode in self._outputsInside:
                if oNode in removed:
                    raise NotImplementedError()

            self._subNodes[:] = (n for n in self._subNodes if n not in removed)
            if recursive:
                for n in self._subNodes:
                    if isinstance(n, HlsNetNodeAggregate):
                        n.filterNodesUsingSet(removed, recursive=recursive)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {sorted([n._id for n in self._subNodes])}>"

