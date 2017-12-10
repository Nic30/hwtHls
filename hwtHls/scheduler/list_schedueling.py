from heapq import heappush, heappop
from itertools import chain
from hwt.pyUtils.arrayQuery import arr_all


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
    :param constrainFn: function (thisNode, acutalScheduelization, privateDict)
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
    h_next = []
    openedNodes = set()
    for n in inputs:
        heappush(h, priority[n])
        openedNodes.add(n)

    constrPriv = {}  # private dict for constrainFn
    while h:
        item = heappop(h)
        node = item.node
        startTime = 0
        for parent in node.dependsOn:
            startTime = max(startTime, sched[parent][1])
        endTime = startTime + node.latency_pre + node.latency_post

        startTime, endTime = constrainFn(
            node, sched, startTime, endTime, constrPriv)

        openedNodes.remove(node)
        # start can be behind all ends of parents
        sched[node] = (startTime, endTime)
        for child in node.usedBy:
            if child not in openedNodes \
                    and arr_all(child.dependsOn,  # [TODO] maybe not required if priority is correct
                                lambda x: x in sched):
                heappush(h_next, priority[child])
                openedNodes.add(child)

        if not h:
            h = h_next

    return sched
