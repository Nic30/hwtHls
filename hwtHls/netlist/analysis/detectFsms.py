from itertools import chain
from typing import List, Set, Union, Dict, Callable, Optional

from hwt.hwIO import HwIO
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands, \
    BetweenSyncIsland
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk


# from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
class IoFsm():
    """
    :ivar hwIO: An HwIO instance for which this FSM is generated for. For debugging purposes.
    :ivar states: list of list of nodes for each state, some states may be empty,
        index in states corresponds to clock period index in scheduling
    :ivar syncIslands: a list of unique synchronization islands touching this FSM
    :note: We can not extract FSM transitions there because it would greatly complicate FSM merging and splitting
    :note: States are being executed in order specified in sates list.
        Non linear transitions must be explicitly discovered in ArchElementFsm.
    """

    def __init__(self, hwIO: Optional[HwIO], syncIslands: SetList[BetweenSyncIsland]):
        self.hwIO = hwIO
        self.states: List[List[HlsNetNode]] = []
        self.syncIslands = syncIslands

    def addState(self, clkI: int):
        """
        :param clkI: an index of clk cycle where this state was scheduled
        """
        # stateNodes: List[HlsNetNode] = []
        # stI = len(self.states)
        assert clkI >= 0, clkI
        try:
            return self.states[clkI]
        except IndexError:
            pass

        for _ in range(clkI + 1 - len(self.states)):
            self.states.append([])

        return self.states[clkI]

    def hasUsedStateForClkI(self, clkI: int) -> bool:
        return clkI < len(self.states) and self.states[clkI]


class HlsNetlistAnalysisPassDetectFsms(HlsNetlistAnalysisPass):
    """
    Collect a scheduled netlist nodes which do have a constraint which prevents them to be scheduled as a pipeline and
    also collect all nodes which are tied with them into FSM states.
    """

    def __init__(self):
        super(HlsNetlistAnalysisPassDetectFsms, self).__init__()
        self.fsms: List[IoFsm] = []

    def _floodNetInClockCyclesWalkDepsAndUses(self, node: HlsNetNode,
                               alreadyUsed: Set[HlsNetNode],
                               predicate: Callable[[HlsNetNode], bool],
                               fsm: IoFsm,
                               seenInClks: Dict[int, Set[HlsNetNode]]):
        clkPeriod = node.netlist.normalizedClkPeriod

        for dep in node.dependsOn:
            dep: HlsNetNodeOut
            obj: HlsNetNode = dep.obj
            clkI = start_clk(obj.scheduledOut[dep.out_i], clkPeriod)
            if predicate(obj):
                self._floodNetInClockCycles(obj, clkI, alreadyUsed, predicate, fsm, seenInClks)

        for uses in node.usedBy:
            for use in uses:
                use: HlsNetNodeIn
                obj: HlsNetNode = use.obj
                clkI = start_clk(obj.scheduledIn[use.in_i], clkPeriod)
                if predicate(obj):
                    self._floodNetInClockCycles(obj, clkI, alreadyUsed, predicate, fsm, seenInClks)

    def _floodNetInClockCycles(self,
                               node: HlsNetNode,
                               nodeClkI: int,
                               alreadyUsed: Set[HlsNetNode],
                               predicate: Callable[[HlsNetNode], bool],
                               fsm: IoFsm,
                               seenInClks: Dict[int, Set[HlsNetNode]]):
        # check if we truly want to add this node
        seen = seenInClks.get(nodeClkI, None)
        if seen is None:
            # out of this FSM
            return

        if node not in seen and node not in alreadyUsed:
            stateNodeList = fsm.states[nodeClkI]
            seen.add(node)
            alreadyUsed.add(node)
            allNodeClks = tuple(node.iterScheduledClocks())
            assert len(allNodeClks) == 1, node
            self._appendNodeToState(allNodeClks[0], node, stateNodeList)

            self._floodNetInClockCyclesWalkDepsAndUses(node, alreadyUsed, predicate, fsm, seenInClks)

    def _appendNodeToState(self, clkI: int, n: HlsNetNode, stateNodeList: List[HlsNetNode],):
        clkPeriod: SchedTime = n.netlist.normalizedClkPeriod
        # add nodes to st while asserting that it is from correct time
        for t in n.scheduledIn:
            assert start_clk(t, clkPeriod) == clkI, n
        for t in n.scheduledOut:
            assert int(t // clkPeriod) == clkI, n

        stateNodeList.append(n)

    def collectInFsmNodes(self) -> Dict[HlsNetNode, SetList[IoFsm]]:
        "Collect nodes which are part of some fsm"
        inFsm: Dict[HlsNetNode, SetList[IoFsm]] = {}
        for fsm in self.fsms:
            for nodes in fsm.states:
                for n in nodes:
                    cur = inFsm.get(n, None)
                    if cur is None:
                        cur = inFsm[n] = SetList()
                    cur.append(fsm)

        return inFsm

    def _getClkIOfAccess(self, a: Union[HlsNetNodeRead, HlsNetNodeWrite], clkPeriod: SchedTime):
        return start_clk(a.scheduledIn[0] if a.scheduledIn else a.scheduledOut[0], clkPeriod)

    def _discardIncompatibleNodes(self, fsm: IoFsm):
        """
        * remove HlsNetNodeLoopStatus if associated gate is not part of this fsm
        * remove HlsNetNodeLoopControlPort if associated status is not part of this fsm
        """
        allNodes = None
        for st in fsm.states:
            toRm = set()
            for n in st:
                if n in toRm:
                    continue
                if isinstance(n, HlsNetNodeLoopStatus):
                    if allNodes is None:
                        # lazy resolved allNodes from performance reasons
                        allNodes = set(chain(*fsm.states))
                    n: HlsNetNodeLoopStatus
                    for g in chain(n.fromReenter, n.fromExitToHeaderNotify):
                        g: LoopChanelGroup
                        for cw in g.members:
                            c = cw.associatedRead
                            if c not in allNodes:
                                toRm.add(n)
                                break
                # elif isinstance(n, HlsNetNodeLoopControlPort):
                #    if allNodes is None:
                #        # lazy resolved allNodes from performance reasons
                #        allNodes = set(chain(*fsm.states))
                #    n: HlsNetNodeLoopControlPort
                #    if n._loopStatus not in allNodes or any(c not in allNodes for c in chain(n._loopStatus.fromReenter, n._loopStatus.fromExit)):
                #        toRm.add(n)

            if toRm:
                st[:] = (n for n in st if n not in toRm)

    @override
    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        ioDiscovery: HlsNetlistAnalysisPassIoDiscover = netlist.getAnalysis(HlsNetlistAnalysisPassIoDiscover)
        ioByInterface = ioDiscovery.ioByInterface
        syncIslands: HlsNetlistAnalysisPassBetweenSyncIslands = netlist.getAnalysis(HlsNetlistAnalysisPassBetweenSyncIslands)
        clkPeriod: SchedTime = netlist.normalizedClkPeriod

        def floodPredicateExcludeOtherIoWithOwnFsm(n: HlsNetNode):
            if isinstance(n, HlsNetNodeRead):
                n: HlsNetNodeRead
                accesses = ioByInterface.get(n.src, None)
                if accesses and len(accesses) > 1:
                    return False

            elif isinstance(n, HlsNetNodeWrite):
                n: HlsNetNodeWrite
                accesses = ioByInterface.get(n.dst, None)
                if accesses and len(accesses) > 1:
                    return False

            return True

        alreadyUsed: Set[HlsNetNode] = set()
        for i in ioDiscovery.interfaceList:
            accesses = ioByInterface[i]
            if len(accesses) > accesses[0].maxIosPerClk:
                # if is is accessed on multiple places we need to create a FSM which will control access to it
                islands = SetList()
                for a in accesses:
                    inIsl, outIsl = syncIslands.syncIslandOfNode[a]
                    if (isinstance(a, HlsNetNodeRead) and inIsl is not None) or outIsl is None:
                        isl = inIsl
                    else:
                        isl = outIsl
                    assert isl is not None, a
                    islands.append(isl)

                assert None not in islands, (islands, accesses)

                # all accesses which are not in same clock cycle must be mapped to individual FSM state
                # every interface may spot a FSM
                fsm = IoFsm(i, islands)
                allClkI: SetList[int] = SetList()
                for a in accesses:
                    clkI = self._getClkIOfAccess(a, clkPeriod)
                    allClkI.append(clkI)
                allClkI.sort()
                # prepare fsm states
                seenInClks: Dict[int, Set[HlsNetNode]] = {}
                for clkI in allClkI:
                    seen = seenInClks.get(clkI, None)
                    seen = set()
                    seenInClks[clkI] = seen
                    fsm.addState(clkI)

                for a in sorted(accesses, key=lambda a: a.scheduledIn[0] if a.scheduledIn else a.scheduledOut[0]):
                    a: Union[HlsNetNodeRead, HlsNetNodeWrite]
                    clkI = self._getClkIOfAccess(a, clkPeriod)
                    self._floodNetInClockCycles(a, clkI, alreadyUsed, floodPredicateExcludeOtherIoWithOwnFsm, fsm, seenInClks)

                stCnt = sum(1 if st else 0 for st in fsm.states)
                if stCnt > 1:
                    self._discardIncompatibleNodes(fsm)
                    # initialize with transition table with always jump to next state sequentially
                    # for i in range(stCnt):
                    #    fsm.transitionTable[i] = {(i + 1) % stCnt: 1}  # {next st: cond}

                    # for i in range(stCnt - 1):
                    #    fsm.transitionTable[i] = {(i + 1): 1}
                    # fsm.transitionTable[stCnt - 1] = {}
                    self.fsms.append(fsm)
