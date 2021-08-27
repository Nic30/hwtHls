from math import ceil

from hwtHls.clk_math import start_clk
from hwtHls.codeOps import HlsConst
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.scheduler.alap import alap
from hwtHls.scheduler.asap import asap


class HlsScheduler():

    def __init__(self, parentHls: HlsPipeline):
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
            # [TODO] constants are cheduled multiple times
            time_start, time_end = node.scheduledIn, node.scheduledInEnd
            clk_index = start_clk(time_start, clk_period)
            schedulization[clk_index].append(node)

        self.schedulization = schedulization

    def schedule(self, resource_constrain):
        if resource_constrain:
            raise NotImplementedError()

        hls = self.parentHls
        maxTime = asap(hls.inputs, hls.outputs, hls.clk_period)
        alap(hls.outputs, self.parentHls.clk_period, maxTime)
        sched = {n: (n.alap_start, n.alap_end)
                 for n in hls.nodes}

        self.apply_scheduelization_dict(sched)
