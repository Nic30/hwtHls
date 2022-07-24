from typing import List, Set, Union, Dict, Tuple, Callable

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


class IoFsm():
    """
    :ivar stateClkI: maps the state index to an index of clk tick where the state was originally scheduled
    """

    def __init__(self, intf: Interface):
        self.intf = intf
        self.states: List[List[HlsNetNode]] = []
        self.stateClkI: Dict[int, int] = {}
        self.transitionTable: Dict[int, Dict[int, Union[bool, RtlSignal]]] = {}

    def addState(self, clkI: int):
        """
        :param clkI: an index of clk cycle where this state was scheduled
        """
        nodes = []
        self.stateClkI[len(self.states)] = clkI
        self.states.append(nodes)

        return nodes


class HlsNetlistAnalysisPassDiscoverFsm(HlsNetlistAnalysisPass):
    """
    Collect a scheduled netlist nodes which do have a constraint which prevents them to be scheduled as a pipeline and
    collect also all nodes which are tied with them into FSM states.
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.fsms: List[IoFsm] = []

    def _floodNetInSameCycle(self, clk_i: int, o: HlsNetNode,
                             seen:Set[HlsNetNode],
                             alreadyUsed: Set[HlsNetNode],
                             predicate: Callable[[HlsNetNode], bool]):
        seen.add(o)
        alreadyUsed.add(o)

        allNodeClks = tuple(o.iterScheduledClocks())
        clkPeriod = self.netlist.normalizedClkPeriod
        if len(allNodeClks) > 1:
            inClkInputs = [i for t, i in zip(o.scheduledIn, o._inputs) if start_clk(t, clkPeriod) == clk_i]
            inClkOutputs = [o for t, o in zip(o.scheduledOut, o._outputs) if start_clk(t, clkPeriod) == clk_i]
            subO = o.createSubNodeRefrenceFromPorts(clk_i * clkPeriod, (clk_i + 1) * clkPeriod,
                inClkInputs, inClkOutputs)
            yield subO
        else:
            yield o

        for dep in o.dependsOn:
            dep: HlsNetNodeOut
            obj = dep.obj
            if obj not in seen and obj not in alreadyUsed and start_clk(obj.scheduledOut[dep.out_i], clkPeriod) == clk_i and predicate(obj):
                yield from self._floodNetInSameCycle(clk_i, obj, seen, alreadyUsed, predicate)

        for uses in o.usedBy:
            for use in uses:
                use: HlsNetNodeIn
                obj = use.obj
                if obj not in seen and obj not in alreadyUsed and start_clk(obj.scheduledIn[use.in_i], clkPeriod) == clk_i and predicate(obj):
                    yield from self._floodNetInSameCycle(clk_i, obj, seen, alreadyUsed, predicate)

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

    def run(self):
        ioDiscovery: HlsNetlistAnalysisPassDiscoverIo = self.netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverIo)
        ioByInterface = ioDiscovery.ioByInterface
        clkPeriod = self.netlist.normalizedClkPeriod

        def floodPredicateExcludeOtherIoWithOwnFsm(n: HlsNetNode):
            if isinstance(n, HlsNetNodeRead):
                n: HlsNetNodeRead
                accesses = io_aggregation.get(n.src, None)
                if accesses and len(accesses) > 1:
                    return False
            elif isinstance(n, HlsNetNodeWrite):
                n: HlsNetNodeWrite
                accesses = io_aggregation.get(n.dst, None)
                if accesses and len(accesses) > 1:
                    return False
            return True

        alreadyUsed: Set[HlsNetNode] = set()
        for i, accesses in sorted(io_aggregation.items(), key=lambda x: getSignalName(x[0])):
            if len(accesses) > 1:
                # all accesses which are not in same clock cycle must be mapped to individual FSM state
                # every interface may spot a FSM
                fsm = IoFsm(i)
                seenClks: Dict[int, Set[HlsNetNode]] = {}
                for a in sorted(accesses, key=lambda a: a.scheduledIn[0] if a.scheduledIn else a.scheduledOut[0]):
                    a: Union[HlsNetNodeRead, HlsNetNodeWrite]
                    clkI = start_clk(a.scheduledIn[0] if a.scheduledIn else a.scheduledOut[0], clkPeriod)
                    seen = seenClks.get(clkI, None)
                    # there can be multiple IO operations on same IO in same clock cycle, if this is the case
                    # we must avoid adding duplicit nodes
                    if seen is None:
                        seen = set()
                        seenClks[clkI] = seen
                        st = fsm.addState(clkI)
                    else:
                        st = fsm.states[-1]

                    for n in self._floodNetInSameCycle(clkI, a, seen, alreadyUsed, floodPredicateExcludeOtherIoWithOwnFsm):
                        # add nodes to st while asseting that it is from correct time
                        if isinstance(n, HlsNetNodePartRef):
                            for i in n._subNodes.inputs:
                                for use in i.obj.usedBy[i.out_i]:
                                    if use.obj in n._subNodes.nodes:
                                        assert (use.obj.scheduledIn[use.in_i] // clkPeriod) == clkI, (n, use)
 
                        else:
                            for t in n.scheduledIn:
                                assert start_clk(t, clkPeriod) == clkI, n
                            for t in n.scheduledOut:
                                assert int(t // clkPeriod) == clkI, n
 
                        st.append(n)

                stCnt = len(fsm.states)
                if stCnt > 1:
                    for i in range(stCnt):
                        fsm.transitionTable[i] = {(i + 1) % stCnt: 1}

                    # for i in range(stCnt - 1):
                    #    fsm.transitionTable[i] = {(i + 1): 1}
                    # fsm.transitionTable[stCnt - 1] = {}
                    self.fsms.append(fsm)
