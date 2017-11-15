from math import ceil

from hwt.hdl.operator import isConst
from hwtHls.codeObjs import WriteOpPromise, HlsConst
from hwtHls.hls import Hls


class HlsScheduler():
    def __init__(self, parentHls: Hls):
        self.parentHls = parentHls

    def asap(self):
        """
        As Soon As Possible scheduler

        :return: maximum schedueled timme
        """
        # [TODO] fine grained latency

        maxTime = 0
        unresolved = []
        for node in self.parentHls.inputs:
            node.asap_start = 0
            node.asap_end = 0
            unresolved.extend(node.usedBy)

        while unresolved:
            nextUnresolved = []
            for node in unresolved:
                try:
                    node_t = max(map(lambda n: n.asap_end, node.dependsOn))
                except AttributeError:
                    # skip this node because we will find it
                    # after its dependency will be completed
                    continue
                node.asap_start = node_t
                node.asap_end = node_t + node.latency_pre
                nextUnresolved.extend(node.usedBy)
                maxTime = max(maxTime, node.asap_end)

            unresolved = nextUnresolved
        # some of nodes does not have to be discovered because
        # they have no connection
        for node in self.parentHls.outputs:
            if node.asap_start is None:
                assert isConst(node.what), node
                node.asap_start = 0
                node.asap_end = 0
                node.what.asap_start = 0
                node.what.asap_end = 0

        return maxTime

    def alap(self):
        """
        As Late As Possible scheduler

        :return: maximum schedueled timme
        """
        # [TODO] fine grained latency
        t = 0
        unresolved = []
        for node in self.parentHls.outputs:
            # has no predecessors
            # [TODO] input read latency
            node.alap_start = t
            unresolved.extend(node.dependsOn)

        while unresolved:
            t -= 1
            nextUnresolved = []

            for o in unresolved:
                o.alap_start = t
                nextUnresolved.extend(o.dependsOn)

            unresolved = nextUnresolved

        timeOffset = -t
        for node in self.parentHls.nodes:
            node.alap_start += timeOffset

        return timeOffset

    def schedule(self):
        maxTime = self.asap()
        # self.alap()
        schedulization = [[] for _ in range(ceil(maxTime) + 1)]
        # [DEBUG] scheduele by asap only
        for node in self.parentHls.nodes:
            time = node.asap_start
            if time is None:
                assert isinstance(node, HlsConst)
                time = node.asap_start = node.usedBy[0].asap_start
            schedulization[int(time)].append(node)
            node.scheduledIn = time

        self.schedulization = schedulization
