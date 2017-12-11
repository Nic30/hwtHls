from heapq import heappush, heappop
from itertools import chain
from hwtHls.codeOps import HlsConst
from hwt.hdl.operator import isConst


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
        #print("node", item.priority, node)
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
