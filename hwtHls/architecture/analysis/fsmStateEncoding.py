from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.hlsAndRtlNetlistAnalysisPass import HlsAndRtlNetlistAnalysisPass
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE


# a dictionary mapping state index to a value which will be used in RTL to represent this state.
FsmStateEncoding = dict[int, int]


class HlsAndRtlNetlistAnalysisPassFsmStateEncoding(HlsAndRtlNetlistAnalysisPass):
    """
    Recognize ArchElementFsm states and resolve its encoding to minimize number of bits used
    for the state.
    """

    def __init__(self) -> None:
        HlsAndRtlNetlistAnalysisPass.__init__(self)
        self.stateEncoding: dict["ArchElementFsm", FsmStateEncoding] = {}
        self.usedStates: dict["ArchElementFsm", list[int]] = {}

    @override
    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
        for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER):
            if isinstance(elm, ArchElementFsm):
                usedStates = []  # :note: all are reachable, because there is an implicit jump to next state in sequence
                for clkI, st in elm.iterStages():
                    if st:
                        usedStates.append(clkI)

                stateEncoding: FsmStateEncoding = {clkI: i for i, clkI in enumerate(usedStates)}
                self.stateEncoding[elm] = stateEncoding
                self.usedStates[elm] = usedStates
