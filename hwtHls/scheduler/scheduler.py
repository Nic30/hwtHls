from math import ceil

from hwt.hdl.operator import isConst
from hwtHls.clk_math import start_clk, end_clk
from hwtHls.codeOps import HlsConst
from hwtHls.hls import Hls


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


class HlsScheduler():
    def __init__(self, parentHls: Hls):
        self.parentHls = parentHls

    def asap(self):
        """
        As Soon As Possible scheduler

        :return: maximum schedueled timme, decorate nodes
            with asap_start,end time
        """
        # [TODO] pre-post latencies
        # [TODO] cycle delays/latencies

        maxTime = 0
        unresolved = set()
        clk_period = self.parentHls.clk_period
        # init start times
        for node in self.parentHls.inputs:
            node.asap_start = 0
            node.asap_end = node.latency_pre + node.latency_post
            unresolved.update(
                [n for n in node.usedBy if not n.fixed_schedulation])

        # walk from inputs to outputs and decorate nodes with time
        while unresolved:
            nextUnresolved = set()
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
                        if node.latency_pre + node.latency_post >= clk_period:
                            raise TimeConstraintError(
                                "Impossible scheduling, clk_period too low for ",
                                node.latency_pre, node.latency_post, node)

                node.asap_start = node_t
                node.asap_end = node_t + node.latency_pre

                nextUnresolved.update(
                    [n for n in node.usedBy if not n.fixed_schedulation])

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
        # [TODO] pre-post latencies
        # [TODO] cycle delays/latencies
        unresolved = set()

        for node in self.parentHls.outputs:
            # has no predecessors
            # [TODO] input read latency
            node.alap_end = minimum_latency
            node.alap_start = node.alap_end - node.latency_pre
            unresolved.update(
                [n for n in node.dependsOn if not n.fixed_schedulation])

        clk_period = self.parentHls.clk_period
        # walk from outputs to inputs and note time
        while unresolved:
            nextUnresolved = set()

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
                nextUnresolved.update(
                    [n for n in node.dependsOn if not n.fixed_schedulation])

            unresolved = nextUnresolved

    def apply_scheduelization_dict(self, sched):
        """
        :pram sched: dict {node: (startTime, endTime)}
        """
        clk_period = self.parentHls.clk_period
        maxTime = max(map(lambda x: x[1], sched.values()))

        if maxTime == 0:
            clk_count = 1
        else:
            clk_count = ceil(maxTime / clk_period)

        # render nodes in clk_periods
        schedulization = [[] for _ in range(clk_count)]
        constants = set()
        for node in self.parentHls.nodes:
            if isinstance(node, HlsConst):
                # constants has time specified by it's user
                constants.add(node)
            else:
                time_start, time_end = sched[node]
                assert time_start is not None and time_start >= 0, node

            schedulization[int(time_start * clk_period)].append(node)
            node.scheduledIn = time_start
            node.scheduledInEnd = time_end
            assert node.scheduledIn <= node.scheduledInEnd

        for node in constants:
            time_start, time_end = node.scheduledIn, node.scheduledInEnd
            schedulization[int(time_start * clk_period)].append(node)

        self.schedulization = schedulization

    def schedule(self):
        hls = self.parentHls
        maxTime = self.asap()
        self.alap(maxTime)
        sched = {n: (n.alap_start, n.alap_end) for n in hls.nodes}

        self.apply_scheduelization_dict(sched)
