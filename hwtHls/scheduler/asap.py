from typing import List, Set, Tuple

from hwt.hdl.operator import isConst
from hwtHls.codeOps import HlsConst, AbstractHlsOp, HlsRead, HlsWrite, \
    HlsOperation
from hwtHls.scheduler.errors import UnresolvedChild, TimeConstraintError
from math import inf
from hwtHls.clk_math import start_of_next_clk_period


#def child_asap_time(_ch: Tuple[AbstractHlsOp, int]):
#    ch, i = _ch
#    if ch.asap_end is None:
#        if isinstance(ch, HlsConst):
#            return 0
#        else:
#            raise UnresolvedChild()
#    else:
#        return ch.asap_end[i]
#
# def asap_filter_inputs(inputs: List[AbstractHlsOp], realInputs: Set[AbstractHlsOp]):
#    newlyDiscoveredInputs: Set[AbstractHlsOp] = set()
#    # init start times, filter inputs
#    for node in inputs:
#        if not node.fixed_schedulation and not node.dependsOn:
#            if node.latency_pre is None:
#                raise AssertionError("Missing realization for node", node)
#            node.asap_start = [0.0  for _ in node.dependsOn]
#            latency_pre = 0.0
#            if node.latency_pre:
#                latency_pre = max(node.latency_pre)
#            if len(node.usedBy) > 1:
#                raise NotImplementedError(node)
#
#            node.asap_end = [latency_pre + lp for lp in node.latency_post]
#
#        for out_used_by in node.usedBy:
#            for (n, _) in out_used_by:
#                if n.fixed_schedulation:
#                    newlyDiscoveredInputs.add(n)
#                elif n.asap_start is not None:
#                    continue
#                else:
#                    realInputs.add(n)
#
#    if newlyDiscoveredInputs:
#        asap_filter_inputs(newlyDiscoveredInputs, realInputs)


def _asap(node: HlsOperation, clk_period: float) -> float:
    """
    The recursive function of ASAP scheduling
    """
    if node.asap_end is None:
        if node.dependsOn:
            input_times = [_asap(d.obj, clk_period)[d.out_i] for d in node.dependsOn]
            # now we have times when the value is available on input
            # and we must resolve the minimal time so each input timing constraints are satisfied
            time_when_all_inputs_present = 0.0
            latest_input_i = None
            for in_i, (available_in_time, in_delay, in_cycles) in enumerate(
                zip(input_times, node.latency_pre, node.in_cycles_offset)):
                next_clk_time = start_of_next_clk_period(available_in_time, clk_period)
                time_budget = next_clk_time - available_in_time
                if in_delay >= time_budget:
                    available_in_time = next_clk_time
                    if in_delay >= clk_period:
                        raise TimeConstraintError(
                            "Impossible scheduling, clk_period too low for ",
                            node.latency_pre, node.latency_post, node)
                normalized_time = available_in_time + in_delay + in_cycles * clk_period
                if normalized_time >= time_when_all_inputs_present:
                    latest_input_i = in_i
                    time_when_all_inputs_present = normalized_time
            node_zero_time = time_when_all_inputs_present - node.in_cycles_offset[latest_input_i] * clk_period - node.latency_pre[latest_input_i]
            asap_start = node.asap_start = []
            asap_end = node.asap_end = []

            for (in_delay, in_cycles) in zip(node.latency_pre, node.in_cycles_offset):
                asap_start.append(node_zero_time + in_delay + in_cycles * clk_period)
            for (out_delay, out_cycles) in zip(node.latency_post, node.cycles_latency):
                asap_end.append(time_when_all_inputs_present + out_delay + out_cycles * clk_period)

        elif isinstance(node, HlsConst):
            return [0.0, ]
        else:
            node.asap_start = [0.0, ]
            node.asap_end = [0.0, ]
            if isinstance(node, HlsWrite):
                node.src.asap_start = [0.0, ]
                node.src.asap_end = [0.0, ]

    return node.asap_end


def asap(outputs: List[HlsWrite], clk_period: float):
    """
    As Soon As Possible scheduler

    DFS from outputs, decorate nodes with asap_start,asap_end time

    :return: maximum schedueled timme
    """
    for o in outputs:
        _asap(o, clk_period)

# def asap(inputs: List[HlsRead], outputs: List[HlsWrite], clk_period: float):
#    """
#    As Soon As Possible scheduler
#
#    DFS from outputs, decorate nodes with asap_start,asap_end time
#
#    :return: maximum schedueled timme
#    """
#    # [TODO] cycle delays/latencies
#    maxTime = 0
#    unresolved: Set[AbstractHlsOp] = set()
#    asap_filter_inputs(inputs, unresolved)
#
#    # walk from inputs to outputs and decorate nodes with time
#    while unresolved:
#        nextUnresolved: Set[AbstractHlsOp] = set()
#        for node in unresolved:
#            try:
#                node_t = max((child_asap_time(c) for c in node.dependsOn))
#            except UnresolvedChild:
#                # skip this node because we will find it
#                # after its dependency will be completed
#                # (unresolved children will be resolved and it will
#                # run resolution for this node again)
#                continue
#            else:
#                # Remaining time until clock tick
#                remaining_time = clk_period - (node_t % clk_period)
#                node.resolve_realization()
#
#                if node.latency_pre[0] > remaining_time:
#                    # Operation would exceed clock cycle -> align to clock
#                    # rising edge
#                    node_t += remaining_time
#                    if max(node.latency_pre) + max(node.latency_post) >= clk_period:
#                        raise TimeConstraintError(
#                            "Impossible scheduling, clk_period too low for ",
#                            node.latency_pre, node.latency_post, node)
#
#            assert not node.fixed_schedulation, node
#            node.asap_start = [node_t for _ in node.dependsOn]
#            pre = max(node.latency_pre)
#            node.asap_end = [node_t + lp + pre for lp in node.latency_post]
#
#            assert node.asap_start[0] <= node.asap_end[0], (node, node.asap_start, node.asap_end)
#
#            # print(node.__class__.__name__,
#            #      node.asap_start / clk_period, node.asap_end / clk_period)
#            asap_filter_inputs((node,), nextUnresolved)
#
#            # assign time for potential pending constant nodes
#            for prev_n, prev_ii in node.dependsOn:
#                if prev_n.asap_end is None and isinstance(prev_n, HlsConst):
#                    prev_n.asap_start = prev_n.asap_end = [node.asap_start[prev_ii]]
#
#            maxTime = max(maxTime, *node.asap_end)
#
#        unresolved = nextUnresolved
#
#    # some of nodes does not have to be discovered because
#    # they have no connection to any input
#    for node in outputs:
#        node: HlsWrite
#        if node.asap_start is None:
#            assert isConst(node.src), (node, "was not scheduled, possibly not connected correctly in data flow graph")
#            node.asap_start = [0.0, ]
#            node.asap_end = [0.0, ]
#            node.src.asap_start = [0.0, ]
#            node.src.asap_end = [0.0, ]
#            node.src.asap_end = [0.0, ]
#
#    return maxTime

