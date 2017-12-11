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


def asap_filter_inputs(inputs, realInputs):
    newlyDiscoveredInputs = set()
    # init start times, filter inputs
    for node in inputs:
        if not node.fixed_schedulation and not node.dependsOn:
            node.asap_start = 0.0
            node.asap_end = node.latency_pre + node.latency_post

        for n in node.usedBy:
            if n.fixed_schedulation:
                newlyDiscoveredInputs.add(n)
            elif n.asap_start is not None:
                continue
            else:
                realInputs.add(n)

    if newlyDiscoveredInputs:
        asap_filter_inputs(newlyDiscoveredInputs, realInputs)


def asap(inputs, outputs, clk_period):
    """
    As Soon As Possible scheduler

    :return: maximum schedueled timme, decorate nodes
        with asap_start,end time
    """
    # [TODO] cycle delays/latencies
    #print("asap")
    maxTime = 0
    unresolved = set()
    asap_filter_inputs(inputs, unresolved)

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

            assert not node.fixed_schedulation
            node.asap_start = node_t
            node.asap_end = node_t + node.latency_pre
            #print(node.__class__.__name__,
            #      node.asap_start / clk_period, node.asap_end / clk_period)
            asap_filter_inputs((node, ), nextUnresolved)

            for prev in node.dependsOn:
                if prev.asap_end is None and isinstance(prev, HlsConst):
                    prev.asap_start = prev.asap_end = node.asap_start

            maxTime = max(maxTime, node.asap_end)

        unresolved = nextUnresolved

    # some of nodes does not have to be discovered because
    # they have no connection to any input
    for node in outputs:
        if node.asap_start is None:
            assert isConst(node.what), node
            node.asap_start = 0
            node.asap_end = 0
            node.what.asap_start = 0
            node.what.asap_end = 0

    return maxTime


def alap_filter_outputs(outputs, realOutputs, minimum_latency):
    newlyDiscovered = set()
    for node in outputs:
        if node.fixed_schedulation:
            assert node.alap_end <= minimum_latency, (
                node.alap_end, minimum_latency)
        elif not node.usedBy:
            node.alap_end = minimum_latency
            node.alap_start = node.alap_end - node.latency_pre

        for n in node.dependsOn:
            if n.fixed_schedulation:
                newlyDiscovered.add(n)
            elif n.alap_start is not None:
                continue
            else:
                realOutputs.add(n)

    if newlyDiscovered:
        asap_filter_inputs(newlyDiscovered, realOutputs)


def alap(outputs, clk_period, minimum_latency):
    """
    As Late As Possible scheduler + remove nodes which are not effecting
    any output

    :param minimum_latency: Minimum hls latency returned by ASAP
    """
    # print("alap")
    # [TODO] cycle delays/latencies
    unresolved = set()
    # round to end of last cycle
    _minimum_latency = minimum_latency
    minimum_latency = (end_clk(minimum_latency, clk_period) + 1) * clk_period
    # print(_minimum_latency, minimum_latency)
    alap_filter_outputs(outputs, unresolved, minimum_latency)
    # walk from outputs to inputs and note time
    while unresolved:
        nextUnresolved = set()

        for node in unresolved:
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

            assert not node.fixed_schedulation
            node.alap_end = node_end_t
            node.alap_start = node_end_t - node.latency_pre
            # print(node.__class__.__name__,
            #       node.alap_start / clk_period, node.alap_end / clk_period)
            alap_filter_outputs((node, ), nextUnresolved, minimum_latency)

        unresolved = nextUnresolved


class HlsScheduler():
    def __init__(self, parentHls: Hls):
        self.parentHls = parentHls

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
        # print(clk_count)
        # render nodes in clk_periods
        schedulization = [[] for _ in range(clk_count + 1)]
        constants = set()
        for node in self.parentHls.nodes:
            if isinstance(node, HlsConst):
                # constants has time specified by it's user
                constants.add(node)
            else:
                time_start, time_end = sched[node]
                assert (time_start is not None
                        and time_start >= 0
                        and time_start <= time_end), (
                    node, time_start, time_end)

            clk_index = start_clk(time_start, clk_period)
            # print(clk_index)
            schedulization[clk_index].append(node)
            node.scheduledIn = time_start
            node.scheduledInEnd = time_end
            assert node.scheduledIn <= node.scheduledInEnd

        for node in constants:
            time_start, time_end = node.scheduledIn, node.scheduledInEnd
            clk_index = start_clk(time_start, clk_period)
            schedulization[clk_index].append(node)

        self.schedulization = schedulization

    def schedule(self):
        hls = self.parentHls
        maxTime = asap(hls.inputs, hls.outputs, hls.clk_period)
        alap(hls.outputs, self.parentHls.clk_period, maxTime)
        sched = {n: (n.alap_start, n.alap_end)
                 for n in hls.nodes}

        self.apply_scheduelization_dict(sched)
