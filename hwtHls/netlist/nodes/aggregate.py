from collections import deque
from copy import copy
from itertools import chain
from typing import List, Optional, Tuple, Set, Deque, Sequence, Callable

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, OutputMinUseTimeGetter, \
    SchedTime
from hwtHls.netlist.scheduler.clk_math import offsetInClockCycle, \
    indexOfClkPeriod


class HlsNetNodeAggregate(HlsNetNode):
    """
    Container of cluster of nodes.

    :note: Usually used as a container of nodes which do have some special scheduling requirements.

    :ivar _inputsInside: a list of nodes which are representing an input port of this node inside of this node
    :ivar _outputsInside: a list of nodes which are representing an output port of this node inside of this node
    """

    def __init__(self, netlist: "HlsNetlistCtx", subNodes: SetList[HlsNetNode], name: str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        assert isinstance(subNodes, SetList), subNodes
        self.subNodes = subNodes
        for n in subNodes:
            n.parent = self
        self._inputsInside: List[HlsNetNodeAggregatePortIn] = []
        self._outputsInside: List[HlsNetNodeAggregatePortOut] = []
        self.builder = HlsNetlistBuilder(self.netlist, self)

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNode.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y: HlsNetNodeAggregate
            # copy ports omitting desp/uses (to avoid cycle during object cloning)
            y._inputsInside = [HlsNetNodeAggregatePortIn(y.netlist, i, ii._outputs[0]._dtype, ii.name)
                               for i, ii in zip(y._inputs, self._inputsInside)]
            y._outputsInside = [HlsNetNodeAggregatePortOut(y.netlist, o, oi.name)
                                for o, oi in zip(y._outputs, self._outputsInside)]
            for orig, new in zip(chain(self._inputsInside, self._outputsInside), chain(y._inputsInside, y._outputsInside)):
                memo[id(orig)] = new

            y.subNodes = SetList(n.clone(memo, True)[0] for n in self.subNodes)
            # connect previously ommitted links
            for orig, new in zip(self._inputsInside, y._inputsInside):
                new: HlsNetNodeAggregatePortIn
                newUses = new.usedBy[0]
                for u in orig.usedBy[0]:
                    u: HlsNetNodeIn
                    newUses.append(u.obj.clone(memo, True)[0]._inputs[u.in_i])

            for orig, new in zip(self._outputsInside, y._outputsInside):
                dep: Optional[HlsNetNodeOut] = orig.dependsOn[0]
                new.dependsOn[0].append(None if dep is None else dep.obj.clone(memo, True)[0]._outputs[dep.out_i])

        return y, isNew

    @override
    def _addOutput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeOut, HlsNetNodeIn]:
        outputClkTickOffset: int = 0
        outputWireDelay: int = 0
        if time is None:
            assert self.scheduledZero is None, self
        else:
            assert self.scheduledZero is not None
            schedZero = self.scheduledZero
            clkPeriod = self.netlist.normalizedClkPeriod
            outputClkTickOffset = indexOfClkPeriod(time, clkPeriod) - indexOfClkPeriod(schedZero, clkPeriod)
            if outputClkTickOffset == 0:
                # schedZero is an offset in current clock window
                outputWireDelay = offsetInClockCycle(time, clkPeriod) - offsetInClockCycle(schedZero, clkPeriod)
            else:
                # schedZero is not important because start is from the beginning of selected clock window
                outputWireDelay = offsetInClockCycle(time, clkPeriod)

        o = HlsNetNode._addOutput(self, t, name, addDefaultScheduling=time is not None,
                                  outputClkTickOffset=outputClkTickOffset,
                                  outputWireDelay=outputWireDelay)
        assert time is None or self.scheduledOut[o.out_i] == time, (self.scheduledOut[o.out_i], time)
        oPort = HlsNetNodeAggregatePortOut(self.netlist, o, name)
        self._outputsInside.append(oPort)
        self.addNode(oPort)
        if time is None:
            assert self.scheduledOut is None
        else:
            oPort._setScheduleZero(time)
            if self.scheduledOut is not None:
                assert len(self.scheduledOut) == len(self._outputs)

        return o, oPort._inputs[0]

    @override
    def _addInput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeIn, HlsNetNodeOut]:
        inputClkTickOffset: int = 0
        inputWireDelay: int = 0
        schedZero = self.scheduledZero
        if time is None:
            assert schedZero is None
        else:
            assert schedZero is not None
            assert self.realization.mayBeInFFStoreTime, self
            netlist = self.netlist
            clkPeriod = netlist.normalizedClkPeriod
            inputClkTickOffset = indexOfClkPeriod(schedZero, clkPeriod) - indexOfClkPeriod(time, clkPeriod)
            if inputClkTickOffset == 0:
                # under normal circumstances where input is scheduled before scheduledZero time < schedZero
                inputWireDelay = schedZero - time
            else:
                inputWireDelay = (
                    (clkPeriod - offsetInClockCycle(time, clkPeriod))  # remaining until end of clk
                )

        i = HlsNetNode._addInput(self, name, addDefaultScheduling=time is not None,
                                 inputClkTickOffset=inputClkTickOffset,
                                 inputWireDelay=inputWireDelay)
        iPort = HlsNetNodeAggregatePortIn(self.netlist, i, t, name)
        if time is None:
            assert self.scheduledIn is None
        else:
            iPort._setScheduleZero(time)
            if self.scheduledIn is not None:
                assert len(self.scheduledIn) == len(self._inputs)

        self._inputsInside.append(iPort)
        self.addNode(iPort)
        return i, iPort._outputs[0]

    @override
    def _removeOutput(self, index:int):
        HlsNetNode._removeOutput(self, index)
        outInside = self._outputsInside.pop(index)
        assert outInside is not None, self
        assert outInside.dependsOn[0] is None, ("Port must be disconnected inside of aggregate before remove", self, outInside)
        self.subNodes.remove(outInside)

    @override
    def _removeInput(self, index:int):
        HlsNetNode._removeInput(self, index)
        inInside = self._inputsInside.pop(index)
        assert inInside is not None
        assert not inInside.usedBy[0], ("Port must be disconnected inside of aggregate before remove", self, inInside)
        self.subNodes.remove(inInside)

    def addNode(self, n: HlsNetNode):
        assert n.parent is None, (n, n.parent)
        n.parent = self
        self.subNodes.append(n)

    def addNodes(self, nodes: Sequence[HlsNetNode]):
        append = self.subNodes.append
        for n in nodes:
            assert n.parent is None, (n, n.parent)
            n.parent = self
            append(n)

    @override
    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        HlsNetNode.destroy(self)
        self.subNodes = None
        self._totalInputCnt = None
        self._inputsInside = None
        self._outputsInside = None

    @override
    def copyScheduling(self, schedule: SchedulizationDict):
        for n in self.subNodes:
            n.copyScheduling(schedule)
        schedule[self] = (self.scheduledZero, self.scheduledIn, self.scheduledOut)

    @override
    def setScheduling(self, schedule: SchedulizationDict):
        for n in self.subNodes:
            n.setScheduling(schedule)
        (self.scheduledZero, self.scheduledIn, self.scheduledOut) = schedule[self]

    @override
    def moveSchedulingTime(self, offset: SchedTime):
        HlsNetNode.moveSchedulingTime(self, offset)
        for n in self.subNodes:
            n.moveSchedulingTime(offset)

    @override
    def checkScheduling(self):
        HlsNetNode.checkScheduling(self)
        for n in self.subNodes:
            n.checkScheduling()

        # assert that io of this node has correct times
        for outerIn, port, outerInT in zip(self._inputs, self._inputsInside, self.scheduledIn):
            outerIn: HlsNetNodeIn
            port: HlsNetNodeAggregatePortIn
            outerDep = self.dependsOn[outerIn.in_i]
            outerDepT = outerDep.obj.scheduledOut[outerDep.out_i]
            assert outerDepT <= outerInT, (outerDepT, outerInT, outerDep, outerIn)
            portT = port.scheduledOut[0]
            try:
                assert outerInT == portT, (outerInT, portT, outerIn, port)
            except:
                raise
        for outer, port, t in zip(self._outputs, self._outputsInside, self.scheduledOut):
            outer: HlsNetNodeOut
            port: HlsNetNodeAggregatePortOut
            intern: HlsNetNodeOut = port.dependsOn[0]
            assert outer.obj is self
            assert intern.obj in self.subNodes, (self, intern.obj)
            # assert t == intern.obj.scheduledOut[intern.out_i], (intern, t, intern.obj.scheduledOut[intern.out_i])
            assert t == port.scheduledIn[0], (outer, port, "outside:", t, "inside:", port.scheduledIn[0])

    @override
    def resetScheduling(self):
        for n in self.subNodes:
            n.resetScheduling()
        HlsNetNode.resetScheduling(self)

    def copySchedulingFromChildren(self):
        self.scheduledIn = tuple(i.scheduledOut[0] for i in self._inputsInside)
        self.scheduledOut = tuple(o.scheduledIn[0] for o in self._outputsInside)
        self.scheduledZero = max(self.scheduledIn) if self.scheduledIn else\
                             min(self.scheduledOut) if self.scheduledOut else\
                             min(n.scheduledZero for n in self.subNodes)

    def _getAlapOutsideOutMinUseTime(self,
                                     inPort: HlsNetNodeAggregatePortIn,
                                     endOfLastClk: SchedTime,
                                     currentMinUseTime: SchedTime,
                                     outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                                     excludeNode: Optional[Callable[[HlsNetNode], bool]]) -> SchedTime:
        assert not any(inPort.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter, excludeNode)), (inPort, "Should only copy input times from outside")
        t = min(currentMinUseTime, inPort.scheduledOut[0])

        if outputMinUseTimeGetter is not None:
            outerOut = inPort.parentIn.obj.dependsOn[inPort.parentIn.in_i]
            t = outputMinUseTimeGetter(outerOut, t)

        return t

    @override
    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]],
                     beginOfFirstClk: SchedTime,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        if self.scheduledOut is None:
            if self.realization is None:
                self.resolveRealization()
            for o in self.subNodes:
                o.scheduleAsap(pathForDebug, 0, None)
            self.copySchedulingFromChildren()

        return self.scheduledOut

    @override
    def scheduleAlapCompaction(self, endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        inTimes = copy(self.scheduledIn)
        
        self.scheduleAlapCompactionForSubnodes(endOfLastClk, outputMinUseTimeGetter, excludeNode)

        self.copySchedulingFromChildren()

        for dep, origT, newT in zip(self.dependsOn, inTimes, self.scheduledIn):
            if origT != newT:
                yield dep.obj

    def scheduleAlapCompactionForSubnodes(self,
                                          endOfLastClk: SchedTime,
                                          outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                                          excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        """
        Run ALAP scheduling for all submodes including HlsNetNodeAggregatePortOut nodes.
        """
        toSearch: Deque[HlsNetNode] = deque()
        toSearchSet: Set[HlsNetNode] = set()
        for oPort in self._outputsInside:
            assert len(oPort.dependsOn) == 1, oPort
            node = oPort.dependsOn[0].obj
            if node not in toSearchSet and (excludeNode is None or not excludeNode(node)):
                toSearch.append(node)
                toSearchSet.add(node)

        for node in self.subNodes:
            node: HlsNetNode
            if isinstance(node, HlsNetNodeAggregate) or (
                node.realization is not None and
                    (any(node.inputClkTickOffset) or any(node.outputClkTickOffset))
                    ) or not any(any(users) for users in node.usedBy):
                if node not in toSearchSet and (excludeNode is None or not excludeNode(node)):
                    toSearch.append(node)
                    toSearchSet.add(node)

        while toSearch:
            node0: HlsNetNode = toSearch.popleft()
            toSearchSet.remove(node0)
            assert len(toSearch) == len(toSearchSet), (toSearch, toSearchSet)
            for node1 in node0.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter, excludeNode):
                if node1 not in toSearchSet and (excludeNode is None or not excludeNode(node)):
                    toSearch.append(node1)
                    toSearchSet.add(node1)

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
                assert u.obj in self.subNodes, (internOutput, u, "Must be used only inside of cluster")
                if u.obj is outPort:
                    continue
                outerUsedBy.append(u)
            internOutput.obj.usedBy[internOutput.out_i] = outerUsedBy

        # parent = self.parent
        # if parent is None:
        #    parent = self.netlist
        for n in self.subNodes:
            if isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)):
                continue
            n.parent = None
            # parent.addNode(n)
            yield n

        self.markAsRemoved()
        self.destroy()

    @override
    def iterAllNodesFlat(self, itTy: NODE_ITERATION_TYPE):
        assert not self._isMarkedRemoved, (self.__class__.__name__, self._id, self.name)
        if itTy == NODE_ITERATION_TYPE.PREORDER or itTy == NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER:
            yield self

        if self.subNodes is None:
            raise AssertionError("Must have subnodes", self)

        for n in self.subNodes:
            if n._isMarkedRemoved:
                continue
            yield from n.iterAllNodesFlat(itTy)

        if itTy == NODE_ITERATION_TYPE.POSTORDER or itTy == NODE_ITERATION_TYPE.ONLY_PARENT_POSTORDER:
            yield self

    def filterNodesUsingRemovedSet(self, recursive=False):
        return HlsNetlistCtx.filterNodesUsingRemovedSet(self, recursive=recursive)

    def filterNodesUsingSet(self, removed: Set[HlsNetNode], recursive=False, clearRemoved=True):
        if removed:
            toRm = []
            for iNode in self._inputsInside:
                if iNode in removed:
                    toRm.append(iNode)

            for iNode in toRm:
                self._removeInput(iNode.parentIn.in_i)

            toRm.clear()
            for oNode in self._outputsInside:
                if oNode in removed:
                    toRm.append(oNode)
            for oNode in toRm:
                self._removeOutput(oNode.parentOut.out_i)

            self.subNodes[:] = (n for n in self.subNodes if n not in removed)
            if recursive:
                for n in self.subNodes:
                    if isinstance(n, HlsNetNodeAggregate):
                        n.filterNodesUsingSet(removed, recursive=recursive, clearRemoved=False)

            if clearRemoved:
                removed.clear()

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}{' ' + self.name if self.name else ''}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d}{' ' + self.name if self.name else ''} {'<destroyed>' if self.subNodes is None else repr(sorted([n._id for n in self.subNodes]))}>"


class HlsNetNodeAggregateTmpForScheduling(HlsNetNodeAggregate):
    """
    Subclass of HlsNetNodeAggregate which is meant to be dissolved after scheduling
    """
    pass
