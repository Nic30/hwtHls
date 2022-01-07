from itertools import chain, zip_longest
from typing import Dict, Tuple

from hwtHls.netlist.nodes.ops import HlsConst, AbstractHlsOp
from hwtHls.scheduler.asap import asap


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
            node.scheduledIn = time_start
            node.scheduledOut = time_end

        for node in constants:
            node: AbstractHlsOp
            # [TODO] constants are scheduled multiple times
            parent = node.usedBy[0]
            p_input = parent[0]
            node.scheduledOut = node.scheduledIn = [
                p_input.obj.scheduledIn[p_input.in_i], ]

    def schedule(self):
        hls = self.parentHls
        asap(chain(hls.outputs, hls.nodes, hls.inputs), hls.clk_period)
        
        sched = {}
        for n in chain(hls.inputs, hls.nodes, hls.outputs):
            n: AbstractHlsOp
            for t, i in zip_longest(n.asap_start, n._inputs):
                sched[i] = t
            for t, o in zip_longest(n.asap_end, n._outputs):
                sched[o] = t

        self.apply_scheduelization_dict(sched)
