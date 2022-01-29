from typing import List, Set, Union, Dict

from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.clk_math import start_clk
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


class IoFsm():

    def __init__(self, intf: Interface):
        self.intf = intf
        self.states: List[List[HlsNetNode]] = []
        self.transitionTable: Dict[int, Dict[int, Union[bool, RtlSignal]]] = {}


class HlsNetlistAnalysisPassDiscoverFsm(HlsNetlistAnalysisPass):
    """
    Collect a scheuled netlist nodes which do have a constraint which prevents them to be scheduled as a pipeline and
    collect also all nodes which are tied with them into FSM states.
    """

    def __init__(self, hls: "HlsPipeline"):
        HlsNetlistAnalysisPass.__init__(self, hls)
        self.fsms: List[IoFsm] = []
    
    def _floodNetInSameCycle(self, clk_i: int, o: HlsNetNode, seen:Set[HlsNetNode]):
        seen.add(o)
        yield o
        clk_period = self.hls.clk_period
        for dep in o.dependsOn:
            dep: HlsNetNodeOut
            obj = dep.obj
            if obj not in seen:
                if int((obj.scheduledOut[dep.out_i]) // clk_period) == clk_i:
                    yield from self._floodNetInSameCycle(clk_i, obj, seen)

        for uses in o.usedBy:
            for use in uses:
                use: HlsNetNodeIn
                obj = use.obj
                if obj not in seen:
                    if start_clk(obj.scheduledIn[use.in_i], clk_period) == clk_i:
                        yield from self._floodNetInSameCycle(clk_i, obj, seen)

    def collectInFsmNodes(self) -> Set[HlsNetNode]:
        "Collect nodes which are part of some fsm"
        inFsm: Set[HlsNetNode] = set()
        for fsm in self.fsms:
            for nodes in fsm.states:
                inFsm.update(nodes)
        return inFsm

    def run(self):
        io_aggregation = self.hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverIo).io_by_interface
        clk_period = self.hls.clk_period
        for i, accesses in sorted(io_aggregation.items(), key=lambda x: getSignalName(x[0])):
            if len(accesses) > 1:
                # all accesses which are not in same clock cycle must be mapped to individual FSM state
                # every interface may spot a FSM
                fsm = IoFsm(i)
                seenClks: Dict[int, Set[HlsNetNode]] = {}
                for a in sorted(accesses, key=lambda a: a.scheduledIn[0]):
                    a: Union[HlsNetNodeRead, HlsNetNodeWrite]
                    clkI = start_clk(a.scheduledIn[0], clk_period)
                    seen = seenClks.get(clkI, None)
                    # there can be multiple IO operations on same IO in same clock cycle, if this is the case
                    # we must avoid adding duplicit nodes
                    if seen is None:
                        seen = set()
                        seenClks[clkI] = seen
                        st = []
                        fsm.states.append(st)
                    else:
                        st = fsm.states[-1]

                    st.extend(self._floodNetInSameCycle(clkI, a, seen))

                stCnt = len(fsm.states)
                if stCnt > 1:
                    for i in range(stCnt):
                        fsm.transitionTable[i] = {(i + 1) % stCnt: 1}
    
                    self.fsms.append(fsm)
