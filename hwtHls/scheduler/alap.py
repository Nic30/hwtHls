from hwtHls.clk_math import end_clk, start_clk
from hwtHls.netlist.nodes.ops import HlsConst
#from hwtHls.scheduler.asap import asap_filter_inputs
from hwtHls.scheduler.errors import UnresolvedChild


def parent_alap_time(ch):
    if ch.alap_start is None:
        if isinstance(ch, HlsConst):
            return 0
        else:
            raise UnresolvedChild()
    else:
        return ch.alap_start


#def alap():

#def alap_filter_outputs(outputs, realOutputs, minimum_latency):
#    newlyDiscovered = set()
#    for node in outputs:
#        if node.fixed_schedulation:
#            assert node.alap_end <= minimum_latency, (
#                node.alap_end, minimum_latency)
#        elif not node.usedBy:
#            node.alap_end = minimum_latency
#            node.alap_start = node.alap_end - node.latency_pre
#
#        for n in node.dependsOn:
#            if n.fixed_schedulation:
#                newlyDiscovered.add(n)
#            elif n.alap_start is not None:
#                continue
#            else:
#                realOutputs.add(n)
#
#    if newlyDiscovered:
#        asap_filter_inputs(newlyDiscovered, realOutputs)
#
#
#def alap(outputs, clk_period, minimum_latency):
#    """
#    As Late As Possible scheduler + remove nodes which are not effecting
#    any output
#
#    :param minimum_latency: Minimum hls latency returned by ASAP
#    """
#    # print("alap")
#    # [TODO] cycle delays/latencies
#    unresolved = set()
#    # round to end of last cycle
#    _minimum_latency = minimum_latency
#    minimum_latency = (end_clk(minimum_latency, clk_period) + 1) * clk_period
#    # print(_minimum_latency, minimum_latency)
#    alap_filter_outputs(outputs, unresolved, minimum_latency)
#    # walk from outputs to inputs and note time
#    while unresolved:
#        nextUnresolved = set()
#
#        for node in unresolved:
#            try:
#                if node.usedBy:
#                    node_end_t = min(map(parent_alap_time, node.usedBy))
#                else:
#                    node_end_t = minimum_latency
#            except UnresolvedChild:
#                # skip this node because we will find it
#                # after its dependency will be completed
#                # (unresolved children will be resolved and it will
#                # run resolution for this node again)
#                continue
#            else:
#                if node.latency_pre != 0:
#                    clk_start = start_clk(
#                        node_end_t - node.latency_pre, clk_period)
#                    clk_end = end_clk(node_end_t, clk_period)
#
#                    if clk_start != clk_end:
#                        assert clk_end > clk_start and clk_end - clk_start <= 1, (
#                            clk_start, clk_end, node)
#                        node_end_t = clk_end * clk_period
#
#            assert not node.fixed_schedulation
#            node.alap_end = node_end_t
#            node.alap_start = node_end_t - node.latency_pre
#            # print(node.__class__.__name__,
#            #       node.alap_start / clk_period, node.alap_end / clk_period)
#            alap_filter_outputs((node,), nextUnresolved, minimum_latency)
#
#        unresolved = nextUnresolved

