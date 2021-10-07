from heapq import heappush, heappop
from itertools import chain
from typing import List, Callable, Dict, Tuple, Union

from hwt.hdl.operatorDefs import OpDefinition
from hwtHls.clk_math import start_clk, end_clk, epsilon
from hwtHls.codeOps import HlsConst, HlsOperation, AbstractHlsOp, HlsWrite, \
    HlsRead, OperationIn, OperationOut
from hwtHls.hlsPipeline import HlsSyntaxError
from hwtHls.scheduler.scheduler import HlsScheduler, asap


def getComponentConstrainingFn(clk_period: float, comp_constrain: Dict[OpDefinition, int]):
    """
    Build component constraining function for specified comp_constrain
    and clk_period

    :param comp_constrain: dict {operation: max count per clk}
    """
    comp_per_clk = {}

    def constrainFn(node, sched, startTime, endTime):
        s_clk = start_clk(startTime, clk_period)
        e_clk = end_clk(endTime, clk_period)
        clk_shift = 0

        if s_clk != e_clk:
            # component is crossing clk cycle
            assert e_clk - s_clk == 1, node
            clk_shift = 1

        if isinstance(node, HlsOperation):
            o = node.operator
            constr = comp_constrain.get(o, None)
            if constr is not None:
                assert constr > 0, (o, "Count of available units too low")
                while True:
                    clk_usages = comp_per_clk.setdefault(
                        s_clk + clk_shift, {})
                    comp_usage_in_clk = clk_usages.setdefault(o, 0)
                    if comp_usage_in_clk + 1 <= constr:
                        # component can be schedueled in this clk cycle
                        clk_usages[o] += 1
                        break
                    else:
                        # scheduele component later
                        clk_shift += 1

        if clk_shift:
            _startTime = (s_clk + clk_shift) * clk_period
            endTime = endTime - startTime + _startTime
            startTime = _startTime

        return startTime, endTime

    return constrainFn


class ListSchedItem():

    def __init__(self, priority, node):
        self.priority = priority
        self.node = node

    def __lt__(self, other):
        return self.priority < other.priority


def list_schedueling(inputs: List[HlsRead], nodes: List[AbstractHlsOp],
                     outputs: List[HlsWrite],
                     constrainFn:Callable[[AbstractHlsOp, Dict[AbstractHlsOp, Tuple[float, float]], float, float], float],
                     priorityFn:Callable[[AbstractHlsOp], float]
                     ) -> Dict[Union[Tuple[int, AbstractHlsOp], Tuple[AbstractHlsOp, int]], Tuple[float, float]]:
    """
    :param inputs: list of HlsRead objects
    :param nodes: list of HlsOperation instances
    :param outputs: list of HlsWrite objects
    :param constrainFn: function (node, sched, startTime, endTime)
        -> True if node can be schedueled
    :param priorityFn: function (node) -> Union[int, float]
        lower = higher priority
    """
    # node: (start time, end time)
    sched = {}
    # cache for priority values
    priority = {
        n: ListSchedItem(priorityFn(n), n)
        for n in chain(inputs, nodes, outputs)
    }

    h = []  # heap for unresolved nodes
    for n in nodes:
        if isinstance(n, HlsConst):
            # constants will be scheduled to same time as operations later
            continue
        heappush(h, priority[n])

    while h:
        item = heappop(h)
        node = item.node
        assert node not in sched
        startTime = 0.0
        for parent in node.dependsOn:
            if parent is None:
                continue
            try:
                p_times = sched[parent]
            except KeyError:
                if not isinstance(parent.obj, HlsConst):
                    # imposible to schedule due req. not scheduled yet
                    startTime = None
                    break
                p_times = (0.0, 0.0)

            startTime = max(startTime, p_times[1])

        if startTime is None:
            # imposible to schedule due req. not met
            p = item.priority
            item.priority = max(
                (0.0 if isinstance(d.obj, HlsConst) else priority[d.obj].priority
                for d in node.dependsOn))
            if item.priority == p:
                item.priority += epsilon
            # or h[0].priority == p
            assert item.priority >= p, (node, item.priority, p)
            heappush(h, item)
            # scheduling is postponed untill children are scheduled
            continue

        pre = node.latency_pre
        pre = (max(pre) if pre else 0.0)
        post = node.latency_post
        post = (max(post) if post else 0.0)
        endTime = startTime + pre + post

        startTime, endTime = constrainFn(node, sched, startTime, endTime)

        # start can be behind all ends of parents

        # assign start/end for individual inputs/outputs
        for ii, i_pre_time in enumerate(node.latency_pre):
            sched[OperationIn(node, ii)] = (startTime - (pre - i_pre_time) , endTime)

        for oi, o_post_time in enumerate(node.latency_post):
            sched[OperationOut(node, oi)] = (startTime, endTime - post + o_post_time)

        # total span of operation
        # sched[node] = (startTime, endTime)

    return sched


class ListSchedueler(HlsScheduler):

    def schedule(self, resource_constrain):
        hls = self.parentHls
        clk_period = self.parentHls.clk_period
        # discover time interval where operations can be schedueled
        for n in hls.nodes:
            n.resolve_realization()
        # maxTime = self.asap()
        asap(hls.outputs, clk_period)
        # self.alap(maxTime)

        if resource_constrain is None:
            resource_constrain = {}

        constrainFn = getComponentConstrainingFn(
            clk_period, resource_constrain)

        def priorityFn(node):
            if not node.asap_start:
                return 0.0
            else:
                return min(node.asap_start)

        sched = list_schedueling(
            hls.inputs, hls.nodes, hls.outputs,
            constrainFn, priorityFn)

        if not sched:
            raise HlsSyntaxError("Everything was removed durning optimization")

        self.apply_scheduelization_dict(sched)
