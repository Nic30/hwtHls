from typing import List, Optional, Tuple, Generator

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict, OutputTimeGetter, OutputMinUseTimeGetter
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION


class HlsNetNodeAggregatePortIn(HlsNetNode):
    """
    A node which represents an input port to a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentIn: HlsNetNodeIn, dtype: HdlType, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addOutput(dtype, name)
        self.parentIn = parentIn

    def resolve_realization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def _setScheduleZero(self, t:int):
        self.scheduledZero = t
        self.scheduledIn = ()
        self.scheduledOut = (t,)

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]],
                     beginOfFirstClk: int,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        """
        Copy the ASAP time from outside output to this input port
        """
        # resolve time for input of this cluster
        if self.scheduledOut is None:
            self.resolve_realization()
            dep = self.parentIn.obj.dependsOn[self.parentIn.in_i]
            t = dep.obj.scheduleAsap(pathForDebug, beginOfFirstClk, outputTimeGetter)[dep.out_i]
            if outputTimeGetter is None:
                t = dep.obj.scheduleAsap(pathForDebug, beginOfFirstClk, None)[dep.out_i]  # + epsilon
            else:
                t = outputTimeGetter(dep, pathForDebug, beginOfFirstClk)
            self._setScheduleZero(t)
        return self.scheduledOut

    def __repr__(self):
        return f"<{self.__class__.__name__} {self._id} i={self.parentIn.in_i} parent={self.parentIn.obj}>"


class HlsNetNodeAggregatePortOut(HlsNetNode):
    """
    A node which represents an output port from a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentOut: HlsNetNodeIn, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addInput(name)
        self.parentOut = parentOut

    def _setScheduleZero(self, t:int):
        self.scheduledZero = t
        self.scheduledIn = (t,)
        self.scheduledOut = ()

    def resolve_realization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    def scheduleAlapCompaction(self, endOfLastClk:int, outputMinUseTimeGetter:Optional[OutputMinUseTimeGetter]) -> Generator["HlsNetNode", None, None]:
        """
        Copy ALAP time from uses of outside port
        """
        uses = self.parentOut.obj.usedBy[self.parentOut.out_i]
        t = min(u.obj.scheduledIn[u.in_i] for u in uses)
        self._setScheduleZero(t)
        return
        yield

    def __repr__(self):
        return f"<{self.__class__.__name__} {self._id} i={self.parentOut.out_i} parent={self.parentOut.obj}>"

        
class HlsNetNodeAggregate(HlsNetNode):
    """
    Container of cluster of nodes.

    :note: Usually used as a container of nodes which do have some special scheduling requirements.

    :ivar isFragmented: flag which is True if the node was split on parts and if parts should be used for allocation instead
        of this whole object.
    :ivar _inputsInside: a list of nodes which are representing an input port of this node inside of this node
    :ivar _outputsInside: a list of nodes which are representing an output port of this node inside of this node
    """

    def __init__(self, netlist:"HlsNetlistCtx", subNodes: UniqList[HlsNetNode], name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        assert isinstance(subNodes, UniqList), subNodes
        self._subNodes = subNodes
        self._isFragmented = False
        self._inputsInside: List[HlsNetNodeAggregatePortIn] = []
        self._outputsInside: List[HlsNetNodeAggregatePortOut] = []

    def _addOutput(self, t:HdlType, name:Optional[str]) -> Tuple[HlsNetNodeOut, HlsNetNodeIn]:
        o = HlsNetNode._addOutput(self, t, name)
        oPort = HlsNetNodeAggregatePortOut(self.netlist, o, name)
        self._outputsInside.append(oPort)
        self._subNodes.append(oPort)
        return o, oPort._inputs[0]

    def _addInput(self, t:HdlType, name:Optional[str]) -> Tuple[HlsNetNodeIn, HlsNetNodeOut]:
        i = HlsNetNode._addInput(self, name)
        iPort = HlsNetNodeAggregatePortIn(self.netlist, i, t, name)
        self._inputsInside.append(iPort)
        self._subNodes.append(iPort)
        return i, iPort._outputs[0]

    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        HlsNetNode.destroy(self)
        self._subNodes = None
        self._subNodes = None
        self._totalInputCnt = None
        self._inputsInside = None
        self._outputsInside = None
        
    def copyScheduling(self, schedule: SchedulizationDict):
        for n in self._subNodes:
            n.copyScheduling(schedule)
        schedule[self] = (self.scheduledZero, self.scheduledIn, self.scheduledOut)
    
    def setScheduling(self, schedule: SchedulizationDict):
        for n in self._subNodes:
            n.setScheduling(schedule)
        (self.scheduledZero, self.scheduledIn, self.scheduledOut) = schedule[self]

    def moveSchedulingTime(self, offset:int):
        HlsNetNode.moveSchedulingTime(self, offset)
        for n in self._subNodes:
            n.moveSchedulingTime(offset)

    def checkScheduling(self):
        HlsNetNode.checkScheduling(self)
        for n in self._subNodes:
            n.checkScheduling()

        # assert that io of this node has correct times
        for outer, port in zip(self._inputs, self._inputsInside):
            outer: HlsNetNodeOut
            port: HlsNetNodeAggregatePortIn
            pass

        for outer, port in zip(self._outputs, self._outputsInside):
            outer: HlsNetNodeOut
            port: HlsNetNodeAggregatePortOut
            intern: HlsNetNodeOut = port.dependsOn[0]
            assert outer.obj is self
            assert intern.obj in self._subNodes, (self, intern.obj)
            t = self.scheduledOut[outer.out_i]
            # assert t == intern.obj.scheduledOut[intern.out_i], (intern, t, intern.obj.scheduledOut[intern.out_i])
            assert t == port.scheduledIn[0]

    def resetScheduling(self):
        for n in self._subNodes:
            n.resetScheduling()
        HlsNetNode.resetScheduling(self)

    def copySchedulingFromChildren(self):
        self.scheduledIn = tuple(i.scheduledOut[0] for i in self._inputsInside)
        self.scheduledOut = tuple(o.scheduledIn[0] for o in self._outputsInside)
        self.scheduledZero = max(self.scheduledIn) if self.scheduledIn else min(self.scheduledOut)

    def _getAlapOutsideOutMinUseTime(self,
                                     inPort: HlsNetNodeAggregatePortIn,
                                     endOfLastClk: int,
                                     currentMinUseTime: int,
                                     outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]) -> int:
        assert not any(inPort.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter)), (inPort, "Should only copy input times from outside")
        t = min(currentMinUseTime, inPort.scheduledOut[0])

        if outputMinUseTimeGetter is not None:
            outerOut = inPort.parentIn.obj.dependsOn[inPort.parentIn.in_i]
            t = outputMinUseTimeGetter(outerOut, t)

        return t

    def scheduleAlapCompaction(self, endOfLastClk: int, outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter]):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]], outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        raise NotImplementedError(
            "Override this method in derived class", self)

    def allocateRtlInstance(self, allocator:"ArchElement"):
        """
        Instantiate layers of bitwise operators. (Just delegation to sub nodes)
        """
        raise AssertionError("This node should be disaggregated before instantiation to avoid complicated cases where parts are scattered over many arch elements.")

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

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {[n._id for n in self._subNodes]}>"

