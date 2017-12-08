from math import ceil
import sys

from hwt.hdl.operator import isConst
from hwtHls.codeOps import HlsConst
from hwtHls.hls import Hls


epsilon = sys.float_info.epsilon


class UnresolvedChild(Exception):
    """
    Exception raised when children should be lazyloaded first
    """
    pass


class TimeConstraintError(Exception):
    """
    Exception raised when it is not possble to satisfy timing constraints
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


def start_clk(time, clk_period):
    """
    :return: index of clk period for start time
    """
    return max((time + epsilon) // clk_period,
               time // clk_period)


def end_clk(time, clk_period):
    """
    :return: index of clk period for end time
    """
    return min((time - epsilon) // clk_period,
               time // clk_period)


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
        clk_period = self.parentHls.clk_period
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
                else:
                    # Remaining time until clock tick
                    remaining_time = clk_period - (node_t % clk_period)
                    if node.latency_pre > remaining_time:
                        # Operation would exceed clock cycle -> align to clock
                        # rising edge
                        node_t += remaining_time
                        if node.latency_post + node.latency_pre >= clk_period:
                            raise TimeConstraintError(
                                "Impossible scheduling, clk_period too low for ", node)

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

    def alap(self, minimum_latency):
        """
        As Late As Possible scheduler + remove nodes which are not effecting
        any output

        :param minimum_latency: Minimum hls latency returned by ASAP
        """
        # [TODO] fine grained latency
        # [TODO] clock cycle respect
        # [TODO] pre-post latencies
        # [TODO] cycle delays/latencies
        unresolved = []

        for node in self.parentHls.outputs:
            # has no predecessors
            # [TODO] input read latency
            node.alap_end = minimum_latency
            node.alap_start = node.alap_end - node.latency_pre
            unresolved.extend(node.dependsOn)

        clk_period = self.parentHls.clk_period
        # walk from outputs to inputs and note time
        while unresolved:
            nextUnresolved = []

            for node in unresolved:
                if isinstance(node, HlsConst):
                    continue
                try:
                    if node.usedBy:
                        node_end_t = min(map(parent_alap_time, node.usedBy))
                    else:
                        node_end_t = minimum_latency
                except UnresolvedChild:
                    # skip this node because we will find it
                    # after its dependency will be completed
                    # (unresolved children will be resolved and it will
                    # run resolution for this node again)
                    continue
                else:
                    if node.latency_pre != 0:
                        clk_start = start_clk(
                            node_end_t - node.latency_pre, clk_period)
                        clk_end = end_clk(node_end_t, clk_period)

                       if clk_start != clk_end:
                            assert clk_end > clk_start and clk_end - clk_start <= 1, (
                                clk_start, clk_end, node)
                            node_end_t = clk_end * clk_period

                node.alap_end = node_end_t
                node.alap_start = node_end_t - node.latency_pre
                nextUnresolved.extend(node.dependsOn)

            unresolved = nextUnresolved

    def schedule(self):
        # discover time interval where operations can be schedueled
        maxTime = self.asap()
        self.alap(maxTime)

        if maxTime == 0:
            clk_count = 1
        else:
            clk_count = ceil(maxTime / self.parentHls.clk_period)

        # self.alap()
        schedulization = [[] for _ in range(clk_count)]
        # [DEBUG] scheduele by asap only
        for node in self.parentHls.nodes:
            time = node.alap_start
            assert time is not None, node
            schedulization[int(time * self.parentHls.clk_period)].append(node)
            node.scheduledIn = time
            node.scheduledInEnd = node.alap_end

        self.schedulization = schedulization
