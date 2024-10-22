from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsAndRtlNetlistPass():
    """
    A base class for passes which are working on netlist level.
    Passes of this type are used after code was translated to hardware netlist to customize it for target architecture.
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx, *args, **kwargs):
        return HlsNetlistPass.runOnHlsNetlist(self, netlist, *args, **kwargs)

    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        pass
