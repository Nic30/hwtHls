from itertools import chain
from math import ceil
from typing import Dict, Tuple

from hwtHls.clk_math import start_clk
from hwtHls.netlist.nodes.ops import HlsConst, AbstractHlsOp
from hwtHls.scheduler.asap import asap


# from hwtHls.scheduler.alap import alap
class HlsScheduler():

    def __init__(self, parentHls: "HlsPipeline"):
        self.parentHls = parentHls

    def apply_scheduelization_dict(self, sched: Dict[AbstractHlsOp, Tuple[float, float]]):
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
        schedulization = [[] for _ in range(clk_count + 1)]
        constants = set()
        for node in chain(self.parentHls.inputs, self.parentHls.nodes, self.parentHls.outputs):
            if isinstance(node, HlsConst):
                # constants has time specified by it's user
                constants.add(node)
                continue
            else:
                assert isinstance(node, AbstractHlsOp), node
                time_start = []
                for i in node._inputs:
                    s, _ = sched[i]
                    time_start.append(s)

                time_end = []
                for o in node._outputs:
                    _, e = sched[o]
                    time_end.append(e)

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
            node.scheduledInEnd = time_end
            # assert node.scheduledIn <= node.scheduledInEnd

        for node in constants:
            node: AbstractHlsOp
            # [TODO] constants are cheduled multiple times
            parent = node.usedBy[0]
            p_input = parent[0]
            node.scheduledInEnd = node.scheduledIn = [
                p_input.obj.scheduledIn[p_input.in_i], ]

            time_start, _ = node.scheduledIn, node.scheduledInEnd
            clk_index = start_clk(time_start[0], clk_period)
            schedulization[clk_index].append(node)

        if not schedulization[-1]:
            schedulization.pop()

        self.schedulization = schedulization

    def schedule(self, resource_constrain):
        if resource_constrain:
            raise NotImplementedError("This scheduler does not support resource constraints")

        hls = self.parentHls
        for n in hls.nodes:
            n.resolve_realization()
        asap(hls.outputs, hls.clk_period)
        # alap(hls.outputs, hls.clk_period)

        sched = {
            n: (min(n.alap_start[0], n.alap_end[0]),
                     max(n.alap_start[0], n.alap_end[0]))
            for n in hls.nodes
        }

        self.apply_scheduelization_dict(sched)
