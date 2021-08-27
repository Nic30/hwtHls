from hwt.hdl.operator import isConst
from hwtHls.codeOps import HlsConst
from hwtHls.scheduler.errors import UnresolvedChild, TimeConstraintError


def child_asap_time(ch):
    if ch.asap_end is None:
        if isinstance(ch, HlsConst):
            return 0
        else:
            raise UnresolvedChild()
    else:
        return ch.asap_end


def asap_filter_inputs(inputs, realInputs):
    newlyDiscoveredInputs = set()
    # init start times, filter inputs
    for node in inputs:
        if not node.fixed_schedulation and not node.dependsOn:
            if node.latency_pre is None:
                raise AssertionError("Missing realization for node", node)
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
                if node.latency_pre is None:
                    raise AssertionError("Missing realization for node", node)
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
            # print(node.__class__.__name__,
            #      node.asap_start / clk_period, node.asap_end / clk_period)
            asap_filter_inputs((node,), nextUnresolved)

            for prev in node.dependsOn:
                if prev.asap_end is None and isinstance(prev, HlsConst):
                    prev.asap_start = prev.asap_end = node.asap_start

            maxTime = max(maxTime, node.asap_end)

        unresolved = nextUnresolved

    # some of nodes does not have to be discovered because
    # they have no connection to any input
    for node in outputs:
        if node.asap_start is None:
            assert isConst(node.src), (node, "was not schedule, possibly not connected correctly in data flow graph")
            node.asap_start = 0
            node.asap_end = 0
            node.src.asap_start = 0
            node.src.asap_end = 0

    return maxTime

