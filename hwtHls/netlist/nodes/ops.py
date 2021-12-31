from copy import copy
from typing import List, Union, Optional, Tuple, Generator

from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.clk_math import epsilon, start_of_next_clk_period
from hwtHls.clk_math import start_clk
from hwtHls.netlist.nodes.ports import HlsOperationIn, HlsOperationOut, \
    _reprMinify
from hwtHls.platform.opRealizationMeta import OpRealizationMeta

TimeSpec = Union[float, Tuple[float, ...]]


class AbstractHlsOp():
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

        self.usedBy: List[List[HlsOperationIn]] = []
        self.dependsOn: List[HlsOperationOut] = []
        self._inputs: List[HlsOperationIn] = []
        self._outputs: List[HlsOperationOut] = []

        self.asap_start: Optional[TimeSpec] = None
        self.asap_end: Optional[TimeSpec] = None
        self.alap_start: Optional[TimeSpec] = None
        self.alap_end: Optional[TimeSpec] = None
        # True if scheduled to specific time
        self.fixed_schedulation = False
        self.scheduledIn: Optional[TimeSpec] = None
        self.scheduledOut: Optional[TimeSpec] = None

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["AbstractHlsOp"]]) -> List[float]:
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
    
                # print(node)
                input_times = (d.obj.scheduleAsap(clk_period, pathForDebug)[d.out_i] for d in self.dependsOn)
                # now we have times when the value is available on input
                # and we must resolve the minimal time so each input timing constraints are satisfied
                time_when_all_inputs_present = 0.0
                latest_input_i = None
    
                for in_i, (available_in_time, in_delay, in_cycles) in enumerate(
                        zip(input_times, self.latency_pre, self.in_cycles_offset)):
                    next_clk_time = start_of_next_clk_period(available_in_time, clk_period)
                    time_budget = next_clk_time - available_in_time
    
                    if in_delay >= time_budget:
                        available_in_time = next_clk_time
    
                    normalized_time = (available_in_time
                                       +in_delay
                                       +in_cycles * clk_period)
    
                    if normalized_time >= time_when_all_inputs_present:
                        latest_input_i = in_i
                        time_when_all_inputs_present = normalized_time
    
                node_zero_time = (time_when_all_inputs_present
                                  -self.in_cycles_offset[latest_input_i] * clk_period
                                  -self.latency_pre[latest_input_i])
                self.asap_start = tuple(
                    node_zero_time + in_delay + in_cycles * clk_period
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
        
    def _add_input(self) -> HlsOperationIn:
        i = HlsOperationIn(self, len(self._inputs))
        self.dependsOn.append(None)
        self._inputs.append(i)
        return i

    def _add_output(self):
        self.usedBy.append([])
        o = HlsOperationOut(self, len(self._outputs))
        self._outputs.append(o)
        return o

    def _numberForEachInput(self, val: Union[float, Tuple[float]]):
        if isinstance(val, (float, int)):
            return [val for _ in self.dependsOn]
        else:
            val = list(val)
            assert len(val) == self.dependsOn, (val, self.dependsOn)
            return val

    def _numberForEachOutput(self, val: Union[float, Tuple[float]]):
        if isinstance(val, (float, int)):
            return tuple(val for _ in self.usedBy)
        else:
            val = list(val)
            assert len(val) == self.usedBy
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
            allocator:"HlsAllocator",
            used_signals:UniqList[TimeIndependentRtlResourceItem]):
        raise NotImplementedError(
            "Override this method in derived class", self)

    def get_earliest_clk(self):
        """Earliest schedule step (by ASAP)"""
        return start_clk(self.asap_start, self.hls.clk_period)

    def get_latest_clk(self):
        """Earliest schedule step (by ALAP)"""
        return start_clk(self.alap_start, self.hls.clk_period)

    def get_mobility(self):
        """
        :return: number of clk periods between earliest and latest schedulization time
        """
        m = self.get_latest_clk() - self.get_earliest_clk()
        assert m >= 0, (self, self.get_earliest_clk(),
                        self.get_latest_clk(),
                        self.asap_start / self.hls.clk_period,
                        self.alap_start / self.hls.clk_period)
        return m

    def get_probability(self, step):
        """Calculate probability of scheduling operation to this step"""
        if step < self.get_earliest_clk() or step > self.get_latest_clk():
            return 0.0

        return 1 / (self.get_mobility() + 1)

    def _get_rtl_context(self):
        return self.hls.ctx

    def instantiateHlsOperationInTime(self,
                                   allocator: "HlsAllocator",
                                   time:float,
                                   used_signals: UniqList[TimeIndependentRtlResourceItem]
                                   ) -> TimeIndependentRtlResourceItem:
        try:
            _o = allocator.node2instance[self]
        except KeyError:
            _o = None

        if _o is None:
            # if dependency of this node is not instantiated yet
            # instantiate it
            _o = allocator._instantiate(self, used_signals)
        else:
            used_signals.append(_o)

        return _o.get(time)

    def debug_iter_shadow_connection_dst(self) -> Generator["AbstractHlsOp", None, None]:
        """
        Iter nodes which are not connected or somehow related to this but do not use a standard connection.
        (The information is used for visualization.)
        """
        return
        yield


class HlsConst(AbstractHlsOp):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, parentHls: "HlsPipeline", val: HValue):
        self.val = val
        AbstractHlsOp.__init__(self, parentHls, None)
        self._add_output()

    def get(self, time: float):
        return self.val

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
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


class HlsOperation(AbstractHlsOp):
    """
    Abstract implementation of RTL operator

    :ivar operator: parent RTL operator for this hsl operator
    """

    def __init__(self, parentHls: "HlsPipeline",
                 operator: OpDefinition,
                 operand_cnt: int,
                 bit_length: int,
                 name=None):
        super(HlsOperation, self).__init__(parentHls, name=name)
        self.bit_length = bit_length
        self.operator = operator
        for i in range(operand_cnt):
            self.dependsOn.append(None)
            self._inputs.append(HlsOperationIn(self, i))
        # add containers for io pins
        self.usedBy.append([])
        self._outputs.append(HlsOperationOut(self, 0))

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
                          used_signals: UniqList[TimeIndependentRtlResourceItem]
                          ) -> TimeIndependentRtlResource:
        op_out = HlsOperationOut(self, 0)
        try:
            return allocator.node2instance[op_out]
        except KeyError:
            pass

        operands = []
        for in_i, dep in enumerate(self.dependsOn):
            o = dep.obj
            _o = o.instantiateHlsOperationInTime(allocator, self.scheduledIn[in_i], used_signals)
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
        allocator._registerSignal(op_out, tis, used_signals)
        return tis

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s}>"
        else:
            deps = ", ".join([_reprMinify(o) for o in self.dependsOn])
            return f"<{self.__class__.__name__:s} {self._id:d} {self.operator.id:s} [{deps:s}]>"

