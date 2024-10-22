from typing import Dict,  List

from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.architecture.analysis.hlsAndRtlNetlistAnalysisPass import HlsAndRtlNetlistAnalysisPass

# a dictionary mapping state index to a value which will be used in RTL to represent this state.
FsmStateEncoding = Dict[int, int]


class HlsAndRtlNetlistAnalysisPassFsmStateEncoding(HlsAndRtlNetlistAnalysisPass):
    """
    Recognize ArchElementFsm states and resolve its encoding to minimize number of bits used
    for the state.
    """

    def __init__(self) -> None:
        HlsAndRtlNetlistAnalysisPass.__init__(self)
        self.stateEncoding: Dict["ArchElementFsm", FsmStateEncoding] = {}
        self.usedStates: Dict["ArchElementFsm", List[int]] = {}

    @override
    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
        for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER):
            if isinstance(elm, ArchElementFsm):
                usedStates = [] # :note: all are reachable, because there is an implicit jump to next state in sequence 
                for clkI, st in elm.iterStages():
                    if st:
                        usedStates.append(clkI)
        
                stateEncoding: FsmStateEncoding = {clkI: i for i, clkI in enumerate(usedStates)}
                self.stateEncoding[elm] = stateEncoding
                self.usedStates[elm] = usedStates
