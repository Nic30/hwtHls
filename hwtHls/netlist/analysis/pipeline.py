from itertools import chain
from typing import List, Set

from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.ops import HlsNetNode
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.clk_math import start_clk


class NetlistPipeline():
    """
    Container about the nodes in a single pipeline which are suitable for
    an implementation in pipeline due favorable data dependencies.
    """

    def __init__(self, stages: List[List[HlsNetNode]]):
        self.stages = stages


class HlsNetlistAnalysisPassDiscoverPipelines(HlsNetlistAnalysisPass):
    """
    Every node which is not part of FSM is a part of pipeline.
    This pass collect largest continuous segments of the netlist.
    """

    def __init__(self, hls: "HlsPipeline"):
        HlsNetlistAnalysisPass.__init__(self, hls)
        self.pipelines: List[NetlistPipeline] = []

    def run(self):
        fsms: HlsNetlistAnalysisPassDiscoverFsm = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        io_aggregation = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverIo).io_by_interface
        allFsmNodes: Set[HlsNetNode] = fsms.collectInFsmNodes()
        clk_period = self.hls.clk_period
        globalPipeline = []

        for node in chain(self.hls.inputs, self.hls.nodes, self.hls.outputs):
            if node not in allFsmNodes:
                if isinstance(node, HlsNetNodeRead):
                    if len(io_aggregation[node.src]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface", node.src, io_aggregation[node.src])

                elif isinstance(node, HlsNetNodeWrite):
                    if len(io_aggregation[node.dst]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface")
                  
                clk_index = start_clk(node.scheduledIn[0], clk_period)
                if len(globalPipeline) <= clk_index:
                    for _ in range(clk_index - len(globalPipeline) + 1):
                        globalPipeline.append([])
                globalPipeline[clk_index].append(node)

        if globalPipeline:
            self.pipelines.append(NetlistPipeline(globalPipeline))
