from typing import List, Dict, Tuple

from hwt.pyUtils.uniqList import UniqList
from hwtHls.clk_math import start_clk
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef


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
    def _extendIfRequired(list_: List[list], lastIndex: int):
        if len(list_) <= lastIndex:
            for _ in range(lastIndex - len(list_) + 1):
                list_.append([])
    
    @classmethod
    def _addNodeToPipeline(cls, node: HlsNetNode, clk_period: float, pipeline: List[List[HlsNetNode]]):
        for clk_index in node.iterScheduledClocks(clk_period):
            clk_index = start_clk(node.scheduledIn[0], clk_period)
            cls._extendIfRequired(pipeline, clk_index)
            pipeline[clk_index].append(node)

    def run(self):
        fsms: HlsNetlistAnalysisPassDiscoverFsm = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        io_aggregation = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverIo).io_by_interface
        allFsmNodes, inFsmNodeParts = fsms.collectInFsmNodes()
        allFsmNodes: Dict[HlsNetNode, UniqList[IoFsm]]
        inFsmNodeParts: Dict[HlsNetNode, UniqList[Tuple[IoFsm, HlsNetNodePartRef]]]
        clk_period = self.hls.clk_period
        globalPipeline = []

        for node in self.hls.iterAllNodes():
            node: HlsNetNode
            assert not isinstance(node, HlsNetNodePartRef), node
            _node = node

            fsms = allFsmNodes.get(node, None)
            if fsms is None:
                parts = inFsmNodeParts.get(node, None)
                if parts is not None:
                    parts: UniqList[Tuple[IoFsm, HlsNetNodePartRef]]
                    # if this is the first part of the node seen
                    # for all parts which are not in any fsm 
                    for part in node.partsComplement([p for _, p in parts]):
                        for clkI in part.iterScheduledClocks(clk_period):
                            self._extendIfRequired(globalPipeline, clkI)
                            globalPipeline[clkI].append(part)                    
                    continue
                    
                elif isinstance(node, HlsNetNodeRead):
                    if len(io_aggregation[node.src]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface", node.src, io_aggregation[node.src])

                elif isinstance(node, HlsNetNodeWrite):
                    if len(io_aggregation[node.dst]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface")

                # this is just node which is part of no FSM,
                # we add it to global pipeline for each clock cycle where it is defined
                self._addNodeToPipeline(node, clk_period, globalPipeline)
                    
        if globalPipeline:
            # [todo] extract pipelines which do have no common src/dst and no common node
            self.pipelines.append(NetlistPipeline(globalPipeline))
