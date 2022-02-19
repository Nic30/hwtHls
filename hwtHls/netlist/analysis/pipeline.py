from typing import List, Dict

from hwt.pyUtils.uniqList import UniqList
from hwtHls.clk_math import start_clk
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode


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
    
    @staticmethod
    def iterNodeScheduledClocks(node: HlsNetNode, clk_period: float):
        seen = []
        for i in node.scheduledIn:
            clkI = start_clk(i, clk_period)
            if clkI not in seen:
                yield clkI
            seen.append(clkI)
        for o in node.scheduledOut:
            clkI = int(o // clk_period)
            if clkI not in seen:
                yield clkI
            seen.append(clkI)

    @staticmethod
    def _extendIfRequired(list_, lastIndex):
        if len(list_) <= lastIndex:
            for _ in range(lastIndex - len(list_) + 1):
                list_.append([])

    def run(self):
        fsms: HlsNetlistAnalysisPassDiscoverFsm = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        io_aggregation = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverIo).io_by_interface
        allFsmNodes: Dict[HlsNetNode, UniqList[IoFsm]] = fsms.collectInFsmNodes()
        clk_period = self.hls.clk_period
        globalPipeline = []

        for node in self.hls.iterAllNodes():
            node: HlsNetNode
            fsms = allFsmNodes.get(node, None)
            if fsms is None:
                if isinstance(node, HlsNetNodeRead):
                    if len(io_aggregation[node.src]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface", node.src, io_aggregation[node.src])

                elif isinstance(node, HlsNetNodeWrite):
                    if len(io_aggregation[node.dst]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface")
                
                for clk_index in self.iterNodeScheduledClocks(node, clk_period):
                    clk_index = start_clk(node.scheduledIn[0], clk_period)
                    self._extendIfRequired(globalPipeline, clk_index)
                    globalPipeline[clk_index].append(node)
            else:
                allClks = tuple(self.iterNodeScheduledClocks(node, clk_period))
                if len(allClks) > 1:
                    for clk_index in allClks:
                        for fsm in fsms:
                            fsm: IoFsm
                            if clk_index not in fsm.stateClkI.values():
                                self._extendIfRequired(globalPipeline, clk_index)
                                globalPipeline[clk_index].append(node)
                
        if globalPipeline:
            self.pipelines.append(NetlistPipeline(globalPipeline))
