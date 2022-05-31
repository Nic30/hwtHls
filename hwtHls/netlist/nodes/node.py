from math import inf, isfinite
from typing import List, Optional, Union, Tuple, Generator, Dict

from hwt.hdl.types.hdlType import HdlType
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period, start_clk
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from itertools import zip_longest

TimeSpec = Union[float, Tuple[int, ...]]
SchedulizationDict = Dict["HlsNetNode", Tuple[Tuple[int, ...], Tuple[int, ...]]]


class HlsNetNode():
    """
    Abstract class for nodes in circuit which are subject to HLS scheduling

    :ivar name: optional suggested name for this object (for debugging purposes)
    :ivar usedBy: for each output list of operation and its input index which are using this output
    :ivar dependsOn: for each input operation and index of its output with data required
        to perform this operation
    :ivar scheduledIn: final scheduled time of start of operation for each input
    :ivar scheduledOut: final scheduled time of end of operation for each output

    :attention: inputs must be sorted 1st must have lowest latency

    :ivar latency_pre: combinational latency before first register
        in component for this operation (for each input)
    :ivar latency_post: combinational latency after last register
        in component for this operation (for each output, 0 corresponds to a same time as input[0])
    :ivar cycles_latency: number of clk cycles for data to get from input
        to output (for each output, 0 corresponds to a same clock cycle as input[0])
    :ivar cycles_dealy: number of clk cycles required to process data
         (for each output, 0 corresponds to a same clock cycle as input[0])
    :ivar _inputs: list of inputs of this node
    :ivar _outputs: list of inputs of this node
    """

    def __init__(self, netlist: "HlsNetlistCtx", name: str=None):
        self.name = name
        self.netlist = netlist
        self._id = netlist.nodeCtx.getUniqId()

        self.usedBy: List[List[HlsNetNodeIn]] = []
        self.dependsOn: List[HlsNetNodeOut] = []
        self._inputs: List[HlsNetNodeIn] = []
        self._outputs: List[HlsNetNodeOut] = []

        # True if scheduled to specific time
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledOut: Optional[TimeSpec] = None
    
    def getInputDtype(self, i:int) -> HdlType:
        return self.dependsOn[i]._dtype

    def copyScheduling(self, schedule: SchedulizationDict):
        schedule[self] = (self.scheduledIn, self.scheduledOut)

    def checkScheduling(self):
        """
        Assert that the scheduling is consistent.
        """
        assert self.scheduledIn is not None, self
        assert self.scheduledOut is not None, self
        for i, iT, dep in zip_longest(self._inputs, self.scheduledIn, self.dependsOn):
            assert isinstance(iT, int), (i, iT)
            oT = dep.obj.scheduledOut[dep.out_i]
            assert isinstance(oT, int), (dep, oT)
            assert iT >= oT, (dep, "->", i, iT, oT, "output connected to this input must be scheduled before this input so value is available")
            assert iT >= 0, (iT, self, i, "Scheduled before start of the time")
            assert oT >= 0, (oT, dep, "Scheduled before start of the time")

    def resetScheduling(self):
        self.scheduledIn = None
        self.scheduledOut = None
    
    def moveSchedulingTime(self, offset: int):
        self.scheduledIn = tuple(t + offset for t in self.scheduledIn)
        self.scheduledOut = tuple(t + offset for t in self.scheduledOut)
    
    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        """
        The recursive function of ASAP scheduling
        """
        if self.scheduledOut is None:
            if self.dependsOn:
                if pathForDebug is not None:
                    if self in pathForDebug:
                        raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                    else:
                        pathForDebug.append(self)

                input_times = (d.obj.scheduleAsap(pathForDebug)[d.out_i] for d in self.dependsOn)
                self.resolve_realization()

                # now we have times when the value is available on input
                # and we must resolve the minimal time so each input timing constraints are satisfied
                time_when_all_inputs_present = 0
                clkPeriod = self.netlist.normalizedClkPeriod
                for (available_in_time, in_delay, in_cycles) in zip(input_times, self.latency_pre, self.in_cycles_offset):
                    if in_delay >= clkPeriod:
                        raise TimeConstraintError(
                            "Impossible scheduling, clkPeriod too low for ",
                            self.latency_pre, self.latency_post, self)
                    
                    next_clk_time = start_of_next_clk_period(available_in_time, clkPeriod)
                    time_budget = next_clk_time - available_in_time
    
                    if in_delay >= time_budget:
                        available_in_time = next_clk_time
    
                    normalized_time = (available_in_time
                                       +in_delay
                                       +in_cycles * clkPeriod)
    
                    if normalized_time >= time_when_all_inputs_present:
                        # latest_input_i = in_i
                        time_when_all_inputs_present = normalized_time
    
                self.scheduledIn = tuple(
                    time_when_all_inputs_present - (in_delay + in_cycles * clkPeriod)
                    for (in_delay, in_cycles) in zip(self.latency_pre, self.in_cycles_offset)
                )
    
                self.scheduledOut = tuple(
                    time_when_all_inputs_present + out_delay + out_cycles * clkPeriod
                    for (out_delay, out_cycles) in zip(self.latency_post, self.cycles_latency)
                )
                if pathForDebug is not None:
                    pathForDebug.pop()
    
            else:
                self.resolve_realization()
                self.scheduledIn = tuple(0 for _ in self._inputs)
                self.scheduledOut = self.latency_post[:]
    
        return self.scheduledOut

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        # if all dependencies have inputs scheduled we shedule this node and try successors
        if self.scheduledIn is not None:
            return self.scheduledIn

        assert self.usedBy, ("Compaction should be called only for nodes with dependencies, others should be moved only manually", self)
        asapIn, asapOut = asapSchedule[self]
        outTimes = []
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        oMinTime = inf
        for asapOutT, uses in zip(asapOut, self.usedBy):
            asapOutT: float
            # find earliest time where this output is used
            if uses:
                oT = inf 
                for dependentIn in uses:
                    dependentIn: HlsNetNodeIn
                    iT = dependentIn.obj.scheduleAlapCompaction(asapSchedule)[dependentIn.in_i]
                    oT = min(oT, iT)
                oMinTime = min(oMinTime, oT)
            else:
                # the port is unused we must first check other outputs
                oT = inf
            outTimes.append(oT)
        
        clkPeriod = self.netlist.normalizedClkPeriod
        epsilon = self.netlist.scheduler.epsilon
        # resolve time for unused outputs
        for oI, (asapOutT, oT) in enumerate(zip(asapOut, outTimes)):
            asapOutT: float
            if isfinite(oT):
                continue
            oTSuggestedByAsap = start_of_next_clk_period(asapOutT, clkPeriod) - ffdelay - epsilon
            if isfinite(oMinTime):
                oT = max(oTSuggestedByAsap, oMinTime)
            else:
                oT = oTSuggestedByAsap
                oMinTime = oTSuggestedByAsap

            outTimes[oI] = oT

        if outTimes:
            timeWhenEarliesOutputRequired = min(ot - lp for (ot, lp) in zip(outTimes, self.latency_post))
            # we have to check if every input has enought time for its delay
            # and optionally move this node to previous vlock cycle
            for (in_delay, in_cycles) in zip(self.latency_pre, self.in_cycles_offset):
                if in_delay + ffdelay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        self.latency_pre, self.latency_post, self)
                inTime = timeWhenEarliesOutputRequired - in_delay - in_cycles * clkPeriod
                prevClkEndTime = start_clk(timeWhenEarliesOutputRequired, clkPeriod) * clkPeriod
                
                if inTime <= prevClkEndTime:
                    # must shift whole node sooner in time because the input of input can not be satisfied
                    # in a clock cycle where the input is currently scheduled
                    timeWhenEarliesOutputRequired = start_clk(timeWhenEarliesOutputRequired, clkPeriod) * clkPeriod - ffdelay - epsilon
        else:
            # no outputs, we must use some asap input time and move to end of the clock
            assert self._inputs, (self, "Node without any port")
            timeWhenEarliesOutputRequired = start_of_next_clk_period(asapIn[0], clkPeriod) - ffdelay - epsilon
        
        self.scheduledIn = tuple(
            timeWhenEarliesOutputRequired - (in_delay + in_cycles * clkPeriod)
            for (in_delay, in_cycles) in zip(self.latency_pre, self.in_cycles_offset)
        )
    
        self.scheduledOut = tuple(
            timeWhenEarliesOutputRequired + out_delay + out_cycles * clkPeriod
            for (out_delay, out_cycles) in zip(self.latency_post, self.cycles_latency)
        )
        return self.scheduledIn
        
    def iterScheduledClocks(self):
        clkPeriod = self.netlist.normalizedClkPeriod
        beginTime = inf
        endTime = 0
        for i in self.scheduledIn:
            beginTime = min(beginTime, i)
            
        for o in self.scheduledOut:
            endTime = max(endTime, o)
        if not self.scheduledIn:
            beginTime = endTime
        
        startClkI = start_clk(beginTime, clkPeriod)
        endClkI = int(endTime // clkPeriod)
        yield from range(startClkI, endClkI + 1)


    def _removeInput(self, i:int):
        """
        :attention: does not disconnect the input
        """
        self._inputs.pop(i)
        self.dependsOn.pop(i)
        for i in self._inputs[i:]:
            i.in_i -= 1

    def _add_input(self) -> HlsNetNodeIn:
        i = HlsNetNodeIn(self, len(self._inputs))
        self.dependsOn.append(None)
        self._inputs.append(i)
        return i

    def _add_output(self, t: HdlType):
        self.usedBy.append([])
        o = HlsNetNodeOut(self, len(self._outputs), t)
        self._outputs.append(o)
        return o

    def assignRealization(self, r: OpRealizationMeta):
        schedulerResolution: float = self.netlist.scheduler.resolution
        self.realization = r
        self.in_cycles_offset = HlsNetNode_numberForEachInput(self, r.in_cycles_offset)
        self.latency_pre = HlsNetNode_numberForEachInputNormalized(self, r.latency_pre, schedulerResolution)
        self.latency_post = HlsNetNode_numberForEachOutputNormalized(self, r.latency_post, schedulerResolution)
        self.cycles_latency = HlsNetNode_numberForEachOutputNormalized(self, r.cycles_latency, schedulerResolution)
        self.cycles_delay = HlsNetNode_numberForEachOutput(self, r.cycles_delay)

        return self

    def resolve_realization(self):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def allocateRtlInstanceOutDeclr(self, allocator: "AllocatorArchitecturalElement", o: HlsNetNodeOut, startTime: int) -> TimeIndependentRtlResource:
        assert allocator.netNodeToRtl.get(o, None) is None, ("Must not be redeclared", o)
        s = allocator._sig(f"{allocator.namePrefix}forwardDeclr{self._id:d}_{o.out_i:d}", o._dtype)
        res = allocator.netNodeToRtl[o] = TimeIndependentRtlResource(s, startTime, allocator)
        return res
      
    def allocateRtlInstance(self, allocator: "AllocatorArchitecturalElement"):
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
        Iter nodes which are not connected or somehow related to this but do not use a standard connection.
        (The information is used for visualization.)
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

    :note: The reason for this class is that we need to split nodes during analysis passes when we can not modify the nodes.
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

