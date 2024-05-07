from itertools import chain
from typing import List, Optional, Dict

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn


class NetlistLoop():

    def __init__(self, loopStatusNode: HlsNetNodeLoopStatus, nodes: List[HlsNetNode], parent: Optional["NetlistLoop"]):
        self.statusNode = loopStatusNode
        self.nodes = nodes
        self.parent = parent

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.statusNode._id:d}, len(nodes)={len(self.nodes):d}>"


class HlsNetlistAnalysisPassDetectLoops(HlsNetlistAnalysisPass):
    """
    Discover sub-circuits in netlist which are implementing loop.
    Loop is recognized by HlsNetNodeLoopStatus and loop channels.

    :note: Loop is nested if has no exit or exit leads to parent loop.
    """

    def __init__(self):
        super(HlsNetlistAnalysisPassDetectLoops, self).__init__()
        self.loops: List[UniqList[HlsNetNode]] = []
        self.syncOfNode: Dict[HlsNetNode, Optional[NetlistLoop]] = {}

    @staticmethod
    def discoverLoopNodes(loopStatus: HlsNetNodeLoopStatus) -> List[HlsNetNode]:
        toSearch = [loopStatus]

        for lcg in chain(loopStatus.fromEnter, loopStatus.fromReenter, loopStatus.fromExitToHeaderNotify):
            lcg: LoopChanelGroup
            for n in lcg.members:
                toSearch.append(n.associatedRead)

        foundNodes = []
        seenNodes = set()

        while toSearch:
            n: HlsNetNode = toSearch.pop()
            if n in seenNodes:
                continue
            else:
                seenNodes.add(n)

            foundNodes.append(n)

            for dep in n.dependsOn:
                depObj = dep.obj
                if isinstance(depObj, HlsNetNodeConst) and len(depObj.usedBy[dep.out_i]) == 1:
                    foundNodes.append(depObj)
                    seenNodes.add(depObj)

            for outPort, users in zip(n._outputs, n.usedBy):
                if HdlType_isNonData(outPort._dtype):
                    continue
                for u in users:
                    u: HlsNetNodeIn
                    uObj = u.obj
                    if uObj in seenNodes:
                        continue
                    toSearch.append(uObj)

        # search for tailing HlsNetNodeDelayClkTick nodes
        delays = []
        for n in foundNodes:
            if not isinstance(n, HlsNetNodeExplicitSync):
                continue
            n: HlsNetNodeExplicitSync
            # searchSuccessorDelays = True
            # if isinstance(n, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)):
            #     role = n._loopChannelGroup.connectedLoops.getRoleForLoop(loopStatus)
            #     if role in (LOOP_CHANEL_GROUP_ROLE.)
            oo = n._orderingOut
            if oo is None:
                continue

            for u in n.usedBy[oo.out_i]:
                u: HlsNetNodeIn
                n1 = u.obj
                if n1 in seenNodes:
                    continue
                seenNodes.add(n1)
                if isinstance(n1, HlsNetNodeDelayClkTick):
                    delays.append(n1)

        return foundNodes + delays

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        allLoopNodes = set()
        loops = self.loops

        for n in netlist.nodes:
            if isinstance(n, HlsNetNodeAggregate):
                raise NotImplementedError(n)
            elif isinstance(n, HlsNetNodeLoopStatus):
                loopNodes = self.discoverLoopNodes(n)
                assert loopNodes, "At least loop status should be there"
                duplicitNodes = set(_n._id for _n in allLoopNodes).intersection(set(_n._id for _n in loopNodes))
                assert not duplicitNodes, (
                    "Each node must be exactly in a single loop",
                    n,
                    "duplicit:", sorted(duplicitNodes),
                    "newLoop:", sorted([_n._id for _n in loopNodes]),
                    "cur:", sorted([_n._id for _n in allLoopNodes]),
                )
                allLoopNodes.update(loopNodes)
                loops.append(NetlistLoop(n, loopNodes, None))
        # [FIXME] loop hierarchy

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} loops={[loop.statusNode._id for loop in self.loops]}>"
