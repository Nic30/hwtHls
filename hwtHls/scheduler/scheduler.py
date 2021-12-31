from itertools import chain, zip_longest
from math import ceil
from typing import Dict, Tuple

from hwtHls.clk_math import start_clk
from hwtHls.netlist.nodes.ops import HlsConst, AbstractHlsOp
from hwtHls.scheduler.asap import asap
from hwtHls.scheduler.errors import TimeConstraintError


class HlsScheduler():
    """
    A class which holds the 
    """
    
    def __init__(self, parentHls: "HlsPipeline"):
        self.parentHls = parentHls

    def apply_scheduelization_dict(self, sched: Dict[AbstractHlsOp, Tuple[float, float]]):
        """
        :pram sched: dict {node: (startTime, endTime)}
        """
        clk_period = self.parentHls.clk_period
        maxTime = max(sched.values())

        if maxTime == 0:
            clk_count = 1
        else:
            clk_count = ceil(maxTime / clk_period)

        # render nodes in clk_periods
        schedulization = [[] for _ in range(clk_count + 1)]
        constants = set()
        for node in chain(self.parentHls.inputs, self.parentHls.nodes, self.parentHls.outputs):
            if isinstance(node, HlsConst):
                # constants has time specified by it's user
                constants.add(node)
                continue
            else:
                assert isinstance(node, AbstractHlsOp), node
                time_start = tuple(sched[i] for i in node._inputs)
                time_end = tuple(sched[o] for o in node._outputs)

                # assert (time_start is not None
                #        and time_start >= 0
                #        and time_start <= time_end), (
                #    node, time_start, time_end)
            if not time_start:
                assert not node._inputs, node
                time_start = time_end
            clk_index = start_clk(min(time_start), clk_period)

            schedulization[clk_index].append(node)
            node.scheduledIn = time_start
            node.scheduledOut = time_end
            # assert node.scheduledIn <= node.scheduledOut

        for node in constants:
            node: AbstractHlsOp
            # [TODO] constants are cheduled multiple times
            parent = node.usedBy[0]
            p_input = parent[0]
            node.scheduledOut = node.scheduledIn = [
                p_input.obj.scheduledIn[p_input.in_i], ]

            time_start, _ = node.scheduledIn, node.scheduledOut
            clk_index = start_clk(time_start[0], clk_period)
            schedulization[clk_index].append(node)

        if not schedulization[-1]:
            schedulization.pop()

        self.schedulization = schedulization

    def schedule(self):
        hls = self.parentHls
        for n in chain(hls.inputs, hls.nodes, hls.outputs):
            n.resolve_realization()
            for in_delay in n.latency_pre:
                if in_delay >= hls.clk_period:
                    raise TimeConstraintError(
                        "Impossible scheduling, clk_period too low for ",
                        n.latency_pre, n.latency_post, n)
            if not hasattr(n, "latency_pre"):
                raise AssertionError("Missing timing info", n, n.usedBy)
        asap(chain(hls.outputs, hls.nodes, hls.inputs), hls.clk_period)
        
        sched = {}
        for n in chain(hls.inputs, hls.nodes, hls.outputs):
            n: AbstractHlsOp
            for t, i in zip_longest(n.asap_start, n._inputs):
                sched[i] = t
            for t, o in zip_longest(n.asap_end, n._outputs):
                sched[o] = t

        self.apply_scheduelization_dict(sched)
