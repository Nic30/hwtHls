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
            # node.asap_time = 0
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
                node.asap_end = node_t + node.latency
                nextUnresolved.extend(node.usedBy)
                maxTime = max(maxTime, node.asap_end)

            unresolved = nextUnresolved
        # some of nodes does not have to be discovered because
        # they have no connection
        for node in self.parentHls.outputs:
            try:
                _time = node.asap
            except AttributeError:
                assert isConst(node.what), node
                node.asap = 0
                node.what.asap = 0

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
            node.alap_time = t
            unresolved.extend(node.dependsOn)

        while unresolved:
            t -= 1
            nextUnresolved = []

            for o in unresolved:
                o.alap_time = t
                nextUnresolved.extend(o.dependsOn)

            unresolved = nextUnresolved

        timeOffset = -t
        for node in self.parentHls.nodes:
            node.alap_time += timeOffset

        return timeOffset

    def schedule(self):
        maxTime = self.asap()
        # self.alap()
        schedulization = [[] for _ in range(ceil(maxTime) + 1)]
        # [DEBUG] scheduele by asap only
        for node in self.parentHls.nodes:
            try:
                time = node.asap_start
            except AttributeError:
                assert isinstance(node, HlsConst)
                time = node.usedBy[0].asap_start
            schedulization[time].append(node)
            node.scheduledIn = time

        self.schedulization = schedulization
