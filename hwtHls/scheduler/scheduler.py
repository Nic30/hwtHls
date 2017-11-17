from math import ceil

from hwt.hdl.operator import isConst
from hwtHls.codeObjs import HlsConst
from hwtHls.hls import Hls


class UnresolvedChild(Exception):
    """
    Exception raised when children should be lazyloaded first
    """
    pass


def child_asap_time(ch):
    if ch.asap_end is None:
        if isinstance(ch, HlsConst):
            return 0
        else:
            raise UnresolvedChild()
    else:
        return ch.asap_end


def parent_alap_time(ch):
    if ch.alap_start is None:
        if isinstance(ch, HlsConst):
            return 0
        else:
            raise UnresolvedChild()
    else:
        return ch.alap_start


class HlsScheduler():
    def __init__(self, parentHls: Hls):
        self.parentHls = parentHls

    def asap(self):
        """
        As Soon As Possible scheduler

        :return: maximum schedueled timme, decorate nodes
            with asap_start,end time
        """
        # [TODO] fine grained latency
        # [TODO] clock cycle respect
        # [TODO] pre-post latencies
        # [TODO] cycle delays/latencies

        maxTime = 0
        unresolved = []
        # init start times
        for node in self.parentHls.inputs:
            node.asap_start = node.asap_end = 0
            unresolved.extend(node.usedBy)

        # walk from inputs to outputs and decorate nodes with time
        while unresolved:
            nextUnresolved = []
            for node in unresolved:
                try:
                    node_t = max(map(child_asap_time, node.dependsOn))
                except UnresolvedChild:
                    # skip this node because we will find it
                    # after its dependency will be completed
                    # (unresolved children will be resolved and it will
                    # run resolution for this node again)
                    continue

                node.asap_start = node_t
                node.asap_end = node_t + node.latency_pre

                nextUnresolved.extend(node.usedBy)

                for prev in node.dependsOn:
                    if prev.asap_end is None and isinstance(prev, HlsConst):
                        prev.asap_start = prev.asap_end = node.asap_start

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

    def alap_and_rm_unused(self):
        """
        As Late As Possible scheduler + remove nodes which are not effecting
        any output

        :return: maximum schedueled timme
        """
        # [TODO] fine grained latency
        # [TODO] clock cycle respect
        # [TODO] pre-post latencies
        # [TODO] cycle delays/latencies
        unresolved = []
        for node in self.parentHls.outputs:
            # has no predecessors
            # [TODO] input read latency
            node.alap_end = 0
            node.alap_start = -node.latency_pre
            unresolved.extend(node.dependsOn)

        # walk from outputs to inputs and note time
        while unresolved:
            nextUnresolved = []

            for o in unresolved:
                if isinstance(o, HlsConst):
                    continue
                try:
                    if node.usedBy:
                        node_t = max(map(parent_alap_time, node.usedBy))
                    else:
                        node_t = 0
                except UnresolvedChild:
                    # skip this node because we will find it
                    # after its dependency will be completed
                    # (unresolved children will be resolved and it will
                    # run resolution for this node again)
                    continue

                o.alap_end = node_t
                o.alap_start = node_t - o.latency_pre
                nextUnresolved.extend(o.dependsOn)

            unresolved = nextUnresolved

        timeOffset = -min(map(lambda x: ceil(x.alap_start),
                              self.parentHls.inputs))

        # remove nodes which does not have alap time set
        # (are not connected to output)
        def time_fix_and_clean(node):
            if isinstance(node, HlsConst):
                return True
            if node.alap_end is None:
                return False
            else:
                node.alap_end += timeOffset
                return True

        self.parentHls.nodes = list(filter(time_fix_and_clean,
                                           self.parentHls.nodes))

        return timeOffset

    def schedule(self):
        # discover time interval where operations can be schedueled
        self.alap_and_rm_unused()
        maxTime = self.asap()

        # self.alap()
        schedulization = [[] for _ in range(ceil(maxTime) + 1)]
        # [DEBUG] scheduele by asap only
        for node in self.parentHls.nodes:
            time = node.asap_start
            assert time is not None, node
            schedulization[int(time)].append(node)
            node.scheduledIn = time

        self.schedulization = schedulization
