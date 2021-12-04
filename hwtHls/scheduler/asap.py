from typing import List, Optional

from hwtHls.clk_math import start_of_next_clk_period
from hwtHls.netlist.nodes.io import HlsWrite
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwt.pyUtils.uniqList import UniqList


def _asap(node: AbstractHlsOp, clk_period: float, pathForDebug: Optional[UniqList[AbstractHlsOp]]) -> float:
    """
    The recursive function of ASAP scheduling
    """
    if node.asap_end is None:
        if node.dependsOn:
            if pathForDebug is not None:
                if node in pathForDebug:
                    raise AssertionError("Cycle in graph", node, [n._id for n in pathForDebug[pathForDebug.index(node):]])
                else:
                    pathForDebug.append(node)

            # print(node)
            input_times = (_asap(d.obj, clk_period, pathForDebug)[d.out_i] for d in node.dependsOn)
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

                normalized_time = (available_in_time
                                   +in_delay
                                   +in_cycles * clk_period)

                if normalized_time >= time_when_all_inputs_present:
                    latest_input_i = in_i
                    time_when_all_inputs_present = normalized_time

            node_zero_time = (time_when_all_inputs_present
                              -node.in_cycles_offset[latest_input_i] * clk_period
                              -node.latency_pre[latest_input_i])
            node.asap_start = tuple(
                node_zero_time + in_delay + in_cycles * clk_period
                for (in_delay, in_cycles) in zip(node.latency_pre, node.in_cycles_offset)
            )

            node.asap_end = tuple(
                time_when_all_inputs_present + out_delay + out_cycles * clk_period
                for (out_delay, out_cycles) in zip(node.latency_post, node.cycles_latency)
            )
            if pathForDebug is not None:
                pathForDebug.pop()

        else:
            node.asap_start = (0.0, )
            node.asap_end = (0.0, )
            if isinstance(node, HlsWrite):
                node.src.asap_start = (0.0, )
                node.src.asap_end = (0.0, )

    return node.asap_end


def asap(outputs: List[HlsWrite], clk_period: float):
    """
    As Soon As Possible scheduler
    * The graph must not contain cycles.
    * DFS from outputs, decorate nodes with asap_start,asap_end time.
    """
    try:
        # normal run without checking for cycles
        for o in outputs:
            _asap(o, clk_period, None)
        return
    except RecursionError:
        pass

    # debug run which will raise an exception containing cycle node ids
    path = UniqList()
    for o in outputs:
        _asap(o, clk_period, path)

