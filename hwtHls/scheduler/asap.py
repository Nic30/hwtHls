from typing import List

from hwtHls.clk_math import start_of_next_clk_period
from hwtHls.netlist.nodes.ops import HlsConst, HlsOperation
from hwtHls.netlist.nodes.io import HlsWrite
from hwtHls.scheduler.errors import TimeConstraintError


def _asap(node: HlsOperation, clk_period: float) -> float:
    """
    The recursive function of ASAP scheduling
    """
    if node.asap_end is None:
        if node.dependsOn:
            # print(node)
            input_times = [_asap(d.obj, clk_period)[d.out_i] for d in node.dependsOn if d is not None]
            # now we have times when the value is available on input
            # and we must resolve the minimal time so each input timing constraints are satisfied
            time_when_all_inputs_present = 0.0
            latest_input_i = None
            if not hasattr(node, "latency_pre"):
                raise AssertionError("Missing timing info", node, node.usedBy)
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
                normalized_time = (available_in_time
                                   +in_delay
                                   +in_cycles * clk_period)
                if normalized_time >= time_when_all_inputs_present:
                    latest_input_i = in_i
                    time_when_all_inputs_present = normalized_time
            if latest_input_i is None:
                # no input
                node_zero_time = 0.0
            else:
                node_zero_time = (time_when_all_inputs_present
                                  -node.in_cycles_offset[latest_input_i] * clk_period
                                  -node.latency_pre[latest_input_i])
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
    * The graph must not contain cycles.
    * DFS from outputs, decorate nodes with asap_start,asap_end time.
    """
    for o in outputs:
        _asap(o, clk_period)
