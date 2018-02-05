from heapq import heappush, heappop
from itertools import chain

from hwtHls.clk_math import start_clk, end_clk
from hwtHls.codeOps import HlsConst, HlsOperation
from hwtHls.scheduler.scheduler import HlsScheduler, asap
from hwtHls.hls import HLS_Error


def getComponentConstrainingFn(clk_period: float, comp_constrain):
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
            assert e_clk - s_clk == 1
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


def list_schedueling(inputs, nodes, outputs, constrainFn, priorityFn):
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
    priority = {n: ListSchedItem(priorityFn(n), n)
                for n in chain(inputs, nodes, outputs)}

    h = []  # heap for unresolved nodes
    for n in nodes:
        if isinstance(n, HlsConst):
            continue
        heappush(h, priority[n])

    while h:
        item = heappop(h)
        node = item.node
        assert node not in sched
        startTime = 0
        for parent in node.dependsOn:
            try:
                p_times = sched[parent]
            except KeyError:
                if not isinstance(parent, HlsConst):
                    # imposible to schedule due req. not met
                    startTime = None
                    break
                p_times = (0, 0)

            startTime = max(startTime, p_times[1])

        if startTime is None:
            # imposible to schedule due req. not met
            p = item.priority
            item.priority = max(map(lambda x: 0 if isinstance(
                x, HlsConst) else priority[x].priority,
                node.dependsOn))
            # or h[0].priority == p
            assert item.priority >= p, (p, item.priority)
            heappush(h, item)
            continue

        endTime = startTime + node.latency_pre + node.latency_post

        startTime, endTime = constrainFn(node, sched, startTime, endTime)

        # start can be behind all ends of parents
        sched[node] = (startTime, endTime)

    return sched


class ListSchedueler(HlsScheduler):
    def schedule(self, resource_constrain):
        hls = self.parentHls
        clk_period = self.parentHls.clk_period
        # discover time interval where operations can be schedueled
        # maxTime = self.asap()
        asap(hls.inputs, hls.outputs, clk_period)
        # self.alap(maxTime)

        if resource_constrain is None:
            resource_constrain = {}

        constrainFn = getComponentConstrainingFn(
            clk_period, resource_constrain)

        def priorityFn(node):
            return node.asap_start

        sched = list_schedueling(
            hls.inputs, hls.nodes, hls.outputs,
            constrainFn, priorityFn)

        if not sched:
            raise HLS_Error("Everything was removed durning optimization")

        self.apply_scheduelization_dict(sched)
