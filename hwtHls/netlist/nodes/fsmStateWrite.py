from typing import Dict, List, Tuple

from hwt.code import SwitchLogic
from hwt.hdl.statements.statement import HdlStatement
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn


class HlsNetNodeFsmStateWrite(HlsNetNode):
    """
    Node which is multiplexing inputs to parent ArchElementFsm state register.
    This node has an input port for every possible next state value. This port is 1b condition
    and the node works in a same way as HlsNetNodeOperatorMux would (lower index=higher priority).
    
    :ivar portToNextStateId: a dictionary for mapping of input to id of the state.
    :note: encoding from HlsAndRtlNetlistAnalysisPassFsmStateEncoding must be used to translate state id to an actual value
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetNode.__init__(self, netlist, name=None)
        self.portToNextStateId: Dict[HlsNetNodeIn, int] = {}

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNode.clone(self, memo, keepTopPortsConnected)
        if isNew:
            for cos in self.connections:
                assert cos.isUnused()
            y.portToNextStateId = {memo[port]: stId for port, stId in self.portToNextStateId.items()}

        return y, isNew

    @override
    def rtlAlloc(self, allocator: "ArchElementFsm") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated
        stateReg = allocator._rtlStateReg
        if stateReg is None:
            assert len(self._inputs) <= 1, self
        else:
            stateEncodingA: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = self.netlist.getAnalysisIfAvailable(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
            assert stateEncodingA is not None, ("HlsAndRtlNetlistAnalysisPassFsmStateEncoding should be already prepared before calling rtlAlloc")
            stateEncoding = stateEncodingA.stateEncoding[self.parent]

            # build next state logic from transitionTable
            nextStateCases: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            for i, _c, t in zip(self._inputs, self.dependsOn, self.scheduledIn):
                dstStId = self.portToNextStateId[i]
                dstStVal = stateEncoding[dstStId]
                c = allocator.rtlAllocHlsNetNodeOutInTime(_c, t)
                assert isinstance(c, TimeIndependentRtlResourceItem), (_c, c)
                cSig = c.data
                assert cSig._dtype.bit_length() == 1, c

                nextStateCases.append((cSig, stateReg(stateEncoding[dstStVal])))
            
            con: "ConnectionsOfStage" = allocator.connections.getForTime(self.scheduledIn[0])
            con.stateChangeDependentDrives.append(SwitchLogic(nextStateCases))

        self._isRtlAllocated = True
        return []

    @override
    def resolveRealization(self):
        assert not self._inputs
        assert not self._outputs
        self.inputWireDelay = (0 for _ in range(len(self._inputs)))
        self.inputClkTickOffset = (0  for _ in range(len(self._inputs)))
        self.outputWireDelay = ()
        self.outputClkTickOffset = ()

