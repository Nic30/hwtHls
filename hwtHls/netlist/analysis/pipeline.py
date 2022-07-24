from typing import List, Dict, Tuple, Set

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.scheduler.clk_math import start_clk


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

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.pipelines: List[NetlistPipeline] = []

    @staticmethod
    def _extendIfRequired(list_: List[list], lastIndex: int):
        if len(list_) <= lastIndex:
            for _ in range(lastIndex - len(list_) + 1):
                list_.append([])

    @classmethod
    def _addNodeToPipeline(cls, node: HlsNetNode, clkPeriod: int, pipeline: List[List[HlsNetNode]]):
        for clk_index in node.iterScheduledClocks():
            clk_index = start_clk(node.scheduledIn[0] if node.scheduledIn else node.scheduledOut[0], clkPeriod)
            cls._extendIfRequired(pipeline, clk_index)
            pipeline[clk_index].append(node)

    def run(self):
        fsms: HlsNetlistAnalysisPassDiscoverFsm = self.netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        ioByInterface = self.netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverIo).ioByInterface
        allFsmNodes, inFsmNodeParts = fsms.collectInFsmNodes()
        allFsmNodes: Dict[HlsNetNode, UniqList[IoFsm]]
        inFsmNodeParts: Dict[HlsNetNode, UniqList[Tuple[IoFsm, HlsNetNodePartRef]]]
        clkPeriod = self.netlist.normalizedClkPeriod
        globalPipeline = []

        # interfaces which were checked to be accessed correctly
        alreadyCheckedIo: Set[Interface] = set()
        for node in self.netlist.iterAllNodes():
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
                        for clkI in part.iterScheduledClocks():
                            self._extendIfRequired(globalPipeline, clkI)
                            globalPipeline[clkI].append(part)
                    continue

                elif isinstance(node, HlsNetNodeRead) and node.src not in alreadyCheckedIo:
                    clkI = None
                    for r in ioByInterface[node.src]:
                        r: HlsNetNodeRead
                        _clkI = r.scheduledOut[0] // clkPeriod
                        if clkI is None:
                            clkI = _clkI
                        elif clkI != _clkI:
                            raise AssertionError("In this phase each IO operation in different clock cycle should already have separate gate"
                                                 " if it wants to access same interface", node.src, ioByInterface[node.src])

                elif isinstance(node, HlsNetNodeWrite) and node.dst not in alreadyCheckedIo:
                    clkI = None
                    for w in ioByInterface[node.dst]:
                        w: HlsNetNodeWrite
                        _clkI = w.scheduledIn[0] // clkPeriod
                        if clkI is None:
                            clkI = _clkI
                        elif clkI != _clkI:
                            raise AssertionError("In this phase each IO operation in different clock cycle should already have separate gate"
                                                 " if it wants to access same interface", node.dst, ioByInterface[node.dst])

                # this is just node which is part of no FSM,
                # we add it to global pipeline for each clock cycle where it is defined
                self._addNodeToPipeline(node, clkPeriod, globalPipeline)

        if globalPipeline:
            # [todo] extract pipelines which do have no common src/dst and no common node
            self.pipelines.append(NetlistPipeline(globalPipeline))
