from typing import List, Dict, Tuple, Set, Optional

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands, \
    BetweenSyncIsland
from hwtHls.netlist.analysis.detectFsms import HlsNetlistAnalysisPassDetectFsms, IoFsm
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class NetlistPipeline():
    """
    Container about the nodes in a single pipeline which are suitable for
    an implementation in pipeline due favorable data dependencies.
    """

    def __init__(self, syncIsland: Optional[BetweenSyncIsland], stages: List[List[HlsNetNode]]):
        self.syncIsland = syncIsland
        self.stages = stages


class HlsNetlistAnalysisPassDetectPipelines(HlsNetlistAnalysisPass):
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
            # clk_index = start_clk(node.scheduledIn[0] if node.scheduledIn else node.scheduledOut[0], clkPeriod)
            cls._extendIfRequired(pipeline, clk_index)
            pipeline[clk_index].append(node)

    def run(self):
        fsms: HlsNetlistAnalysisPassDetectFsms = self.netlist.getAnalysis(HlsNetlistAnalysisPassDetectFsms)
        ioByInterface = self.netlist.getAnalysis(HlsNetlistAnalysisPassIoDiscover).ioByInterface
        allFsmNodes, inFsmNodeParts = fsms.collectInFsmNodes()
        allFsmNodes: Dict[HlsNetNode, UniqList[IoFsm]]
        inFsmNodeParts: Dict[HlsNetNode, UniqList[Tuple[IoFsm, HlsNetNodePartRef]]]
        clkPeriod = self.netlist.normalizedClkPeriod
        pipelines = self.pipelines
        syncIslands: HlsNetlistAnalysisPassBetweenSyncIslands = self.netlist.getAnalysis(HlsNetlistAnalysisPassBetweenSyncIslands)
        # interfaces which were checked to be accessed correctly
        alreadyCheckedIo: Set[Interface] = set()
        pipelineForIsland: Dict[BetweenSyncIsland, NetlistPipeline] = {}

        for node in self.netlist.iterAllNodes():
            node: HlsNetNode
            assert not isinstance(node, HlsNetNodePartRef), node
            _node = node

            fsms = allFsmNodes.get(node, None)
            if fsms is None:
                syncIsland = syncIslands.syncIslandOfNode[node]
                if isinstance(syncIsland, tuple):
                    syncIsland, oIsland = syncIsland
                    if syncIsland is None:
                        syncIsland = oIsland

                pipeline = pipelineForIsland.get(syncIsland, None)
                if pipeline is None:
                    pipeline = NetlistPipeline(syncIsland, [])
                    pipelineForIsland[syncIsland] = pipeline
                    pipelines.append(pipeline)

                pipelineStages = pipeline.stages

                parts = inFsmNodeParts.get(node, None)
                if parts is not None:
                    parts: UniqList[Tuple[IoFsm, HlsNetNodePartRef]]
                    # if this is the first part of the node seen
                    # for all parts which are not in any fsm
                    for part in node.partsComplement([p for _, p in parts]):
                        for clkI in part.iterScheduledClocks():
                            self._extendIfRequired(pipelineStages, clkI)
                            pipelineStages[clkI].append(part)
                    continue

                elif isinstance(node, HlsNetNodeRead) and node.src is not None and node.src not in alreadyCheckedIo:
                    clkI = None
                    for r in ioByInterface[node.src]:
                        if isinstance(r, HlsNetNodeRead):
                            r: HlsNetNodeRead
                            _clkI = r.scheduledOut[0] // clkPeriod
                            if clkI is None:
                                clkI = _clkI
                            elif clkI != _clkI:
                                raise AssertionError("In this phase each IO operation in different clock cycle should already have separate gate"
                                                     " if it wants to access same interface", node.src, ioByInterface[node.src])

                elif isinstance(node, HlsNetNodeWrite) and node.dst is not None and node.dst not in alreadyCheckedIo:
                    clkI = None
                    for w in ioByInterface[node.dst]:
                        if isinstance(w, HlsNetNodeWrite):
                            w: HlsNetNodeWrite
                            _clkI = w.scheduledIn[0] // clkPeriod
                            if clkI is None:
                                clkI = _clkI
                            elif clkI != _clkI:
                                raise AssertionError("In this phase each IO operation in different clock cycle should already have separate gate"
                                                     " if it wants to access same interface", node.dst, ioByInterface[node.dst])

                # this is just node which is part of no FSM,
                # we add it to global pipeline for each clock cycle where it is defined
                self._addNodeToPipeline(node, clkPeriod, pipelineStages)

