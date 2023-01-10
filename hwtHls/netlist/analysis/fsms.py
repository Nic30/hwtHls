from typing import List, Set, Union, Dict, Tuple, Callable

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.netlist.analysis.syncReach import HlsNetlistAnalysisPassSyncReach, \
    BetweenSyncNodeIsland


class IoFsm():
    """
    :ivar intf: An interface instance for which this FSM is generated for.
    :ivar states: list of list of nodes for each state
    :ivar stateClkI: maps the state index to an index of clk tick where the state was originally scheduled
    :ivar clkIToStateI: reverse map of stateClkI
    :ivar transitionTable: a dictionary source stateI to dictionary destination stateI to condition for transition
    :ivar syncIslands: a list of unique synchronization islands touching this FSM
    """

    def __init__(self, intf: Interface, syncIslands: UniqList[BetweenSyncNodeIsland]):
        self.intf = intf
        self.states: List[List[HlsNetNode]] = []
        self.stateClkI: Dict[int, int] = {}
        self.clkIToStateI: Dict[int, int] = {}
        self.transitionTable: Dict[int, Dict[int, Union[bool, RtlSignal]]] = {}
        self.syncIslands = syncIslands

    def addState(self, clkI: int):
        """
        :param clkI: an index of clk cycle where this state was scheduled
        """
        stateNodes: List[HlsNetNode] = []
        stI = len(self.states)
        self.stateClkI[stI] = clkI
        self.clkIToStateI[clkI] = stI
        self.states.append(stateNodes)

        return stateNodes


class HlsNetlistAnalysisPassDiscoverFsm(HlsNetlistAnalysisPass):
    """
    Collect a scheduled netlist nodes which do have a constraint which prevents them to be scheduled as a pipeline and
    also collect all nodes which are tied with them into FSM states.
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.fsms: List[IoFsm] = []

    def _floodNetInClockCyclesWalkDepsAndUses(self, node: HlsNetNode,
                               alreadyUsed: Set[HlsNetNode],
                               predicate: Callable[[HlsNetNode], bool],
                               fsm: IoFsm,
                               seenInClks: Dict[int, Set[HlsNetNode]]):
        clkPeriod = self.netlist.normalizedClkPeriod

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
            stateNodeList = fsm.states[fsm.clkIToStateI[nodeClkI]]
            seen.add(node)
            alreadyUsed.add(node)
            allNodeClks = tuple(node.iterScheduledClocks())
            clkPeriod = self.netlist.normalizedClkPeriod
            assert allNodeClks, node
            if len(allNodeClks) > 1:
                # slice a multi-cycle node and pick the parts which belongs to some state of this generated FSM
                for clkI in allNodeClks:
                    if clkI not in seenInClks:
                        continue
                    # inClkInputs = [i for t, i in zip(node.scheduledIn, node._inputs) if start_clk(t, clkPeriod) == clkI]
                    # inClkOutputs = [o for t, o in zip(node.scheduledOut, node._outputs) if start_clk(t, clkPeriod) == clkI]
                    nodePart = node.createSubNodeRefrenceFromPorts(clkI * clkPeriod, (clkI + 1) * clkPeriod,
                        node._inputs, node._outputs)
                    if nodePart is None:
                        # due to internal structure of node there can be the case where we selected nothing
                        # because original node has only some delay at selected time
                        continue

                    stateNodeList = fsm.states[fsm.clkIToStateI[clkI]]
                    self._appendNodeToState(clkI, nodePart, stateNodeList)
            else:
                # append node as it is
                self._appendNodeToState(allNodeClks[0], node, stateNodeList)

            self._floodNetInClockCyclesWalkDepsAndUses(node, alreadyUsed, predicate, fsm, seenInClks)
        
    def _appendNodeToState(self, clkI: int, n: HlsNetNode, stateNodeList: List[HlsNetNode],):
        clkPeriod: int = self.netlist.normalizedClkPeriod
        # add nodes to st while asserting that it is from correct time
        if isinstance(n, HlsNetNodePartRef):
            if n._subNodes:
                for i in n._subNodes.inputs:
                    for use in i.obj.usedBy[i.out_i]:
                        if use.obj in n._subNodes.nodes:
                            assert (use.obj.scheduledIn[use.in_i] // clkPeriod) == clkI, (n, use)
     
        else:
            for t in n.scheduledIn:
                assert start_clk(t, clkPeriod) == clkI, n
            for t in n.scheduledOut:
                assert int(t // clkPeriod) == clkI, n
 
        stateNodeList.append(n)
        
    def collectInFsmNodes(self) -> Tuple[
            Dict[HlsNetNode, UniqList[IoFsm]],
            Dict[HlsNetNode, UniqList[Tuple[IoFsm, HlsNetNodePartRef]]]]:
        "Collect nodes which are part of some fsm"
        inFsm: Dict[HlsNetNode, UniqList[IoFsm]] = {}
        inFsmNodeParts: Dict[HlsNetNode, UniqList[Tuple[IoFsm, HlsNetNodePartRef]]] = {}
        for fsm in self.fsms:
            for nodes in fsm.states:
                for n in nodes:
                    cur = inFsm.get(n, None)
                    if cur is None:
                        cur = inFsm[n] = UniqList()
                    cur.append(fsm)
                    if isinstance(n, HlsNetNodePartRef):
                        n: HlsNetNodePartRef
                        otherParts = inFsmNodeParts.get(n.parentNode, None)
                        if otherParts is None:
                            otherParts = inFsmNodeParts[n.parentNode] = UniqList()
                        otherParts.append((fsm, n))

        return inFsm, inFsmNodeParts

    def _getClkIOfAccess(self, a: Union[HlsNetNodeRead, HlsNetNodeWrite], clkPeriod: int):
        return start_clk(a.scheduledIn[0] if a.scheduledIn else a.scheduledOut[0], clkPeriod)
    
    def run(self):
        ioDiscovery: HlsNetlistAnalysisPassIoDiscover = self.netlist.getAnalysis(HlsNetlistAnalysisPassIoDiscover)
        ioByInterface = ioDiscovery.ioByInterface
        syncReach: HlsNetlistAnalysisPassSyncReach = self.netlist.getAnalysis(HlsNetlistAnalysisPassSyncReach)
        clkPeriod: int = self.netlist.normalizedClkPeriod

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
            if len(accesses) > 1:
                syncIslands = UniqList()
                for a in accesses:
                    inIsl, outIsl = syncReach.syncIslandOfNode[a]
                    if isinstance(a, HlsNetNodeRead) or outIsl is None:
                        isl = inIsl
                    else:
                        isl = outIsl
                    try:
                        assert isl is not None, a
                    except:
                        raise
                    syncIslands.append(isl)
                assert None not in syncIslands, (syncIslands, accesses)

                # all accesses which are not in same clock cycle must be mapped to individual FSM state
                # every interface may spot a FSM
                fsm = IoFsm(i, syncIslands)
                seenInClks: Dict[int, Set[HlsNetNode]] = {}
                allClkI: UniqList[int] = UniqList()
                for a in accesses:
                    clkI = self._getClkIOfAccess(a, clkPeriod)
                    allClkI.append(clkI)
                allClkI.sort()
                # prepare fsm states
                for clkI in allClkI:
                    seen = seenInClks.get(clkI, None)
                    seen = set()
                    seenInClks[clkI] = seen
                    fsm.addState(clkI)

                for a in sorted(accesses, key=lambda a: a.scheduledIn[0] if a.scheduledIn else a.scheduledOut[0]):
                    a: Union[HlsNetNodeRead, HlsNetNodeWrite]
                    clkI = self._getClkIOfAccess(a, clkPeriod)
                    self._floodNetInClockCycles(a, clkI, alreadyUsed, floodPredicateExcludeOtherIoWithOwnFsm, fsm, seenInClks)

                stCnt = len(fsm.states)
                if stCnt > 1:
                    # initialize with tansition table with always jump to next state sequentially
                    for i in range(stCnt):
                        fsm.transitionTable[i] = {(i + 1) % stCnt: 1}  # {next st: cond}

                    # for i in range(stCnt - 1):
                    #    fsm.transitionTable[i] = {(i + 1): 1}
                    # fsm.transitionTable[stCnt - 1] = {}
                    self.fsms.append(fsm)
