from typing import Optional, List, Generator, Callable

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime, OutputTimeGetter, \
    OutputMinUseTimeGetter
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION


class HlsNetNodeAggregatePortIn(HlsNetNode):
    """
    A node which represents an input port to a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentIn: HlsNetNodeIn, dtype: HdlType, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        HlsNetNode._addOutput(self, dtype, "inside")
        self.parentIn = parentIn

    def getDep(self) -> Optional[HlsNetNodeOut]:
        return self.parentIn.obj.dependsOn[self.parentIn.in_i]

    def depOnOtherSide(self) -> Optional[HlsNetNodeOut]:
        """
        For :class:`HlsNetNodeAggregatePortIn` driven by :class:`HlsNetNodeAggregatePortOut` return what drives :class:`HlsNetNodeAggregatePortOut`
        """
        return HlsNetNodeAggregatePortOut.getDepInside(self.getDep())

    @override
    def _addInput(self, *args, **kwargs) -> HlsNetNodeIn:
        raise AssertionError("This type of node should have just one output")

    @override
    def _addOutput(self, *args, **kwargs) -> HlsNetNodeIn:
        raise AssertionError("This type of node should have just one output")

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
            depObjSchedOut = dep.obj.scheduleAsap(pathForDebug, beginOfFirstClk, outputTimeGetter)
            try:
                t = depObjSchedOut[dep.out_i]
            except (TypeError, IndexError):
                raise AssertionError("scheduleAsap did not return expected list of times for each output", dep.obj)
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
        if HdlType_isVoid(dataOut._dtype):
            tir = []
        else:
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

        self._isRtlAllocated = True
        return tir

    def __repr__(self):
        parentIn = self.parentIn
        return f"<{self.__class__.__name__:s} {self._id:d} {'' if self.name is None else f'{self.name} '} {parentIn.obj._id:d}:i{parentIn.in_i}>"


class HlsNetNodeAggregatePortOut(HlsNetNode):
    """
    A node which represents an output port from a :class:`~.HlsNetNodeAggregate` node inside of a node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentOut: HlsNetNodeIn, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        HlsNetNode._addInput(self, "inside")
        self.parentOut = parentOut

    @override
    def _addInput(self, *args, **kwargs) -> HlsNetNodeIn:
        raise AssertionError("This type of node should have just one output")

    @override
    def _addOutput(self, *args, **kwargs) -> HlsNetNodeIn:
        raise AssertionError("This type of node should have just one output")

    def _setScheduleZero(self, t: SchedTime):
        self.scheduledZero = t
        self.scheduledIn = (t,)
        self.scheduledOut = ()

    @staticmethod
    def getDepInside(parentOut: HlsNetNodeOut) -> Optional[HlsNetNodeOut]:
        return parentOut.obj._outputsInside[parentOut.out_i].dependsOn[0]

    @override
    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)

    @override
    def scheduleAlapCompaction(self, endOfLastClk: SchedTime,
                               outputMinUseTimeGetter:Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]) -> Generator["HlsNetNode", None, None]:
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
            assert internO.obj in allocator.subNodes, (
                "Driver of HlsNetNodeAggregatePortOut must be in the parent ArchElement",
                self, internO.obj, allocator, internO.obj.parent)
            oTir = allocator.rtlAllocHlsNetNodeOut(internO)
            # propagate output value to output of parent
            # :note: if this was previously declared using forward declaration rtlRegisterOutputRtlSignal should update its drive
            outTime = outerO.obj.scheduledOut[outerO.out_i]
            allocator.rtlRegisterOutputRtlSignal(outerO, oTir.get(outTime).data, False, False, False)

        self._isRtlAllocated = True
        return []

    def __repr__(self):
        parentOut = self.parentOut
        return f"<{self.__class__.__name__:s} {self._id:d} {'' if self.name is None else f'{self.name} '} {parentOut.obj._id:d}:o{parentOut.out_i}>"

