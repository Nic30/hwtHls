from collections import deque
from itertools import chain
from typing import List, Optional, Tuple, Generator, Set, Deque

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedulizationDict, OutputTimeGetter, OutputMinUseTimeGetter, \
    SchedTime
from hwtHls.netlist.scheduler.clk_math import offsetInClockCycle, \
    indexOfClkPeriod
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwt.pyUtils.typingFuture import override


class HlsNetNodeAggregatePortIn(HlsNetNode):
    """
    A node which represents an input port to a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentIn: HlsNetNodeIn, dtype: HdlType, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addOutput(dtype, "inside")
        self.parentIn = parentIn

    @override
    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def _setScheduleZero(self, t: SchedTime):
        self.scheduledZero = t
        self.scheduledIn = ()
        self.scheduledOut = (t,)

    @override
    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]],
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
        dataOut = self._outputs[0]
        if not HdlType_isVoid(dataOut._dtype):
            parentInPort = self.parentIn
            parentDriver = parentInPort.obj.dependsOn[parentInPort.in_i]
            assert dataOut._dtype == parentDriver._dtype, ("Aggregate port must be of same time as port which drives it",
                                                         self, parentDriver, dataOut._dtype, parentDriver._dtype)
            otherArchElm: "ArchElement" = parentDriver.obj
            tir: Optional[TimeIndependentRtlResource] = otherArchElm.netNodeToRtl.get(parentDriver, None)
            # This port has not yet been allocated, it must use forward declaration
            # because there is no topological order in how the ArchElements are connected.
            time = otherArchElm.scheduledOut[parentDriver.out_i]
            if tir is None:
                tir = otherArchElm.rtlAllocOutDeclr(otherArchElm, parentDriver, time)
                assert tir is not None, parentDriver

            # make tir local to this element
            tir = allocator.rtlRegisterOutputRtlSignal(dataOut, tir.get(time).data, False, False, False)
        else:
            tir = []

        self._isRtlAllocated = True
        return tir

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} i={self.parentIn.in_i} parent={self.parentIn.obj._id:d}>"


class HlsNetNodeAggregatePortOut(HlsNetNode):
    """
    A node which represents an output port from a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentOut: HlsNetNodeIn, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addInput("inside")
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

    @override
    def rtlAlloc(self, allocator:"ArchElement"):
        assert not self._isRtlAllocated
        outerO = self.parentOut
        if not HdlType_isVoid(outerO._dtype):
            internO = self.dependsOn[0]
            assert internO is not None, ("Port must have a driver", self)
            oTir = allocator.rtlAllocHlsNetNodeOut(internO)
            # propagate output value to output of parent
            # :note: if this was previously declared using forward declaration rtlRegisterOutputRtlSignal should update its drive
            outTime = outerO.obj.scheduledOut[outerO.out_i]
            allocator.rtlRegisterOutputRtlSignal(outerO, oTir.get(outTime).data, False, False, False)

        self._isRtlAllocated = True
        return []

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} {'' if self.name is None else  f'{self.name} '}i={self.parentOut.out_i} parent={self.parentOut.obj._id:d}>"


class HlsNetNodeAggregate(HlsNetNode):
    """
    Container of cluster of nodes.

    :note: Usually used as a container of nodes which do have some special scheduling requirements.

    :ivar isFragmented: flag which is True if the node was split on parts and if parts should be used for allocation instead
        of this whole object.
    :ivar _inputsInside: a list of nodes which are representing an input port of this node inside of this node
    :ivar _outputsInside: a list of nodes which are representing an output port of this node inside of this node
    """

    def __init__(self, netlist: "HlsNetlistCtx", subNodes: SetList[HlsNetNode], name: str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        assert isinstance(subNodes, SetList), subNodes
        self._subNodes = subNodes
        self._isFragmented = False
        self._inputsInside: List[HlsNetNodeAggregatePortIn] = []
        self._outputsInside: List[HlsNetNodeAggregatePortOut] = []

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

            y._subNodes = SetList(n.clone(memo, True)[0] for n in self._subNodes)
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
            assert self.scheduledZero is None
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
        self._subNodes.append(oPort)
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
        self._subNodes.append(iPort)
        return i, iPort._outputs[0]

    @override
    def _removeOutput(self, index:int):
        HlsNetNode._removeOutput(self, index)
        outInside = self._outputsInside.pop(index)
        assert outInside is not None, self
        assert outInside.dependsOn[0] is None, ("Port must be disconnected inside of aggregate before remove", self)
        self._subNodes.remove(outInside)

    @override
    def _removeInput(self, index:int):
        HlsNetNode._removeInput(self, index)
        inInside = self._inputsInside.pop(index)
        assert inInside is not None
        assert not inInside.usedBy[0], ("Port must be disconnected inside of aggregate before remove", self)
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
    def scheduleAsap(self, pathForDebug: Optional[SetList["HlsNetNode"]],
                     beginOfFirstClk: SchedTime,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        if self.scheduledOut is not None:
            return self.scheduledOut
        else:
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

        if self._subNodes is None:
            raise AssertionError()

        for n in self._subNodes:
            yield from n.iterAllNodesFlat(itTy)

        if itTy == NODE_ITERATION_TYPE.POSTORDER:
            yield self

    def filterNodesUsingSet(self, removed: Set[HlsNetNode], recursive=False):
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

