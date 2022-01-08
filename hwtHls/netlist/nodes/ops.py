from copy import copy
from typing import List, Union, Optional, Tuple, Generator

from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.allocator.connectionsOfStage import SignalsOfStages
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import epsilon, start_of_next_clk_period
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    _reprMinify
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.scheduler.errors import TimeConstraintError


TimeSpec = Union[float, Tuple[float, ...]]


class HlsNetNode():
    """
    Abstract class for nodes in circuit which are subject to HLS scheduling

    :ivar name: optional suggested name for this object (for debbuging purposes)
    :ivar usedBy: for each output list of operation and its input index which are using this output
    :ivar dependsOn: for each input operation and index of its output with data required
        to perform this operation
    :ivar asap_start: scheduled time of start of operation using ASAP scheduler for each input
    :ivar asap_end: scheduled time of end of operation using ASAP scheduler for each output
    :ivar alap_start: scheduled time of start of operation using ALAP scheduler for each input
    :ivar alap_end: scheduled time of end of operation using ALAP scheduler for each output
    :ivar scheduledIn: final scheduled time of start of operation for each input
    :ivar scheduledOut: final scheduled time of end of operation for each output

    :attention: inputs must be soted 1st must have lowest latency

    :ivar latency_pre: combinational latency before first register
        in compoent for this operation (for each input)
    :ivar latency_post: combinational latency after last register
        in compoent for this operation (for each output, 0 corresponds to a same time as input[0])
    :ivar cycles_latency: number of clk cycles for data to get from input
        to output (for each output, 0 corresponds to a same clock cycle as input[0])
    :ivar cycles_dealy: number of clk cycles required to process data
         (for each output, 0 corresponds to a same clock cycle as input[0])
    :ivar _inputs: list of inputs of this node
    :ivar _outputs: list of inputs of this node
    """

    def __init__(self, parentHls: "HlsPipeline", name: str=None):
        self.name = name
        self.hls = parentHls
        self._id = parentHls.nodeCtx.getUniqId()

        self.usedBy: List[List[HlsNetNodeIn]] = []
        self.dependsOn: List[HlsNetNodeOut] = []
        self._inputs: List[HlsNetNodeIn] = []
        self._outputs: List[HlsNetNodeOut] = []

        self.asap_start: Optional[TimeSpec] = None
        self.asap_end: Optional[TimeSpec] = None
        self.alap_start: Optional[TimeSpec] = None
        self.alap_end: Optional[TimeSpec] = None
        # True if scheduled to specific time
        self.fixed_schedulation = False
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledOut: Optional[TimeSpec] = None

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        """
        The recursive function of ASAP scheduling
        """
        if self.asap_end is None:
            if self.dependsOn:
                if pathForDebug is not None:
                    if self in pathForDebug:
                        raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                    else:
                        pathForDebug.append(self)

                input_times = (d.obj.scheduleAsap(clk_period, pathForDebug)[d.out_i] for d in self.dependsOn)
                self.resolve_realization()

                # now we have times when the value is available on input
                # and we must resolve the minimal time so each input timing constraints are satisfied
                time_when_all_inputs_present = 0.0
    
                for (available_in_time, in_delay, in_cycles) in zip(input_times, self.latency_pre, self.in_cycles_offset):
                    if in_delay >= clk_period:
                        raise TimeConstraintError(
                            "Impossible scheduling, clk_period too low for ",
                            self.latency_pre, self.latency_post, self)
                    
                    next_clk_time = start_of_next_clk_period(available_in_time, clk_period)
                    time_budget = next_clk_time - available_in_time
    
                    if in_delay >= time_budget:
                        available_in_time = next_clk_time
    
                    normalized_time = (available_in_time
                                       +in_delay
                                       +in_cycles * clk_period)
    
                    if normalized_time >= time_when_all_inputs_present:
                        # latest_input_i = in_i
                        time_when_all_inputs_present = normalized_time
    
                self.asap_start = tuple(
                    time_when_all_inputs_present - (in_delay + in_cycles * clk_period)
                    for (in_delay, in_cycles) in zip(self.latency_pre, self.in_cycles_offset)
                )
    
                self.asap_end = tuple(
                    time_when_all_inputs_present + out_delay + out_cycles * clk_period
                    for (out_delay, out_cycles) in zip(self.latency_post, self.cycles_latency)
                )
                if pathForDebug is not None:
                    pathForDebug.pop()
    
            else:
                self.asap_start = (0.0,)
                self.asap_end = (0.0,)
    
        return self.asap_end
        
    def _add_input(self) -> HlsNetNodeIn:
        i = HlsNetNodeIn(self, len(self._inputs))
        self.dependsOn.append(None)
        self._inputs.append(i)
        return i

    def _add_output(self):
        self.usedBy.append([])
        o = HlsNetNodeOut(self, len(self._outputs))
        self._outputs.append(o)
        return o

    def _numberForEachInput(self, val: Union[float, Tuple[float]]):
        if isinstance(val, (float, int)):
            return [val for _ in self._inputs]
        else:
            val = list(val)
            assert len(val) == len(self._inputs), (self, val, self._inputs)
            return val

    def _numberForEachOutput(self, val: Union[float, Tuple[float]]):
        if isinstance(val, (float, int)):
            return tuple(val for _ in self._outputs)
        else:
            val = list(val)
            assert len(val) == len(self._outputs)
            return val

    def assignRealization(self, r: OpRealizationMeta):
        self.realization = r
        self.in_cycles_offset = self._numberForEachInput(copy(r.latency_pre))
        self.latency_pre = self._numberForEachInput(copy(r.latency_pre))
        self.latency_post = self._numberForEachOutput(copy(r.latency_post))
        self.cycles_latency = self._numberForEachOutput(copy(r.cycles_latency))
        self.cycles_delay = self._numberForEachOutput(copy(r.cycles_delay))

        return self

    def resolve_realization(self):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def allocate_instance(self,
            allocator: "HlsAllocator",
            used_signals: SignalsOfStages):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def _get_rtl_context(self):
        return self.hls.ctx

    def debug_iter_shadow_connection_dst(self) -> Generator["HlsNetNode", None, None]:
        """
        Iter nodes which are not connected or somehow related to this but do not use a standard connection.
        (The information is used for visualization.)
        """
        return
        yield


class HlsNetNodeConst(HlsNetNode):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, parentHls: "HlsPipeline", val: HValue):
        self.val = val
        HlsNetNode.__init__(self, parentHls, None)
        self._add_output()

    def get(self, time: float):
        return self.val

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: SignalsOfStages
                          ) -> TimeIndependentRtlResource:
        s = self.val
        t = TimeIndependentRtlResource.INVARIANT_TIME
        return TimeIndependentRtlResource(s, t, allocator)

    def resolve_realization(self):
        self.latency_pre = ()
        self.latency_post = (0.0,)
        self.asap_start = (0.0,)
        self.asap_end = (0.0,)

    def __repr__(self, minify=False):
        if minify:
            return repr(self.val)
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.val}>"


class HlsNetNodeOperator(HlsNetNode):
    """
    Abstract implementation of RTL operator

    :ivar operator: parent RTL operator for this hsl operator
    """

    def __init__(self, parentHls: "HlsPipeline",
                 operator: OpDefinition,
                 operand_cnt: int,
                 bit_length: int,
                 name=None):
        super(HlsNetNodeOperator, self).__init__(parentHls, name=name)
        self.bit_length = bit_length
        self.operator = operator
        for i in range(operand_cnt):
            self.dependsOn.append(None)
            self._inputs.append(HlsNetNodeIn(self, i))
        # add containers for io pins
        self.usedBy.append([])
        self._outputs.append(HlsNetNodeOut(self, 0))

    def resolve_realization(self):
        hls = self.hls
        clk_period = hls.clk_period
        input_cnt = len(self.dependsOn)
        bit_length = self.bit_length

        if self.operator is AllOps.TERNARY:
            input_cnt = input_cnt // 2 + 1

        r = hls.platform.get_op_realization(
            self.operator, bit_length,
            input_cnt, clk_period)
        self.assignRealization(r)

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: SignalsOfStages
                          ) -> TimeIndependentRtlResource:
        op_out = self._outputs[0]
        try:
            return allocator.node2instance[op_out]
        except KeyError:
            pass

        operands = []
        for (dep, t) in zip(self.dependsOn, self.scheduledIn):
            _o = allocator.instantiateHlsNetNodeOutInTime(dep, t, used_signals)
            operands.append(_o)

        s = self.operator._evalFn(*(o.data for o in operands))
        if isinstance(s, HValue):
            t = TimeIndependentRtlResource.INVARIANT_TIME

        else:
            # create RTL signal expression base on operator type
            t = self.scheduledOut[0] + epsilon
            if s.hasGenericName:
                if self.name is not None:
                    s.name = self.name
                else:
                    s.name = f"v{self._id:d}"

        tis = TimeIndependentRtlResource(s, t, allocator)
        allocator._registerSignal(op_out, tis, used_signals.getForTime(t))
        return tis

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s}>"
        else:
            deps = ", ".join([_reprMinify(o) for o in self.dependsOn])
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s} [{deps:s}]>"

