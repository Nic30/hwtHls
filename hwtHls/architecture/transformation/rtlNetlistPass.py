from hwtHls.netlist.context import HlsNetlistCtx


class RtlNetlistPass():
    """
    A base class for passes which are working on netlist level.
    Passes of this type are used after code was translated to hardware netlist to customize it for target architecture.
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        pass
