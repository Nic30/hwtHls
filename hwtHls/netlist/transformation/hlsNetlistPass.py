from hwtHls.netlist.context import HlsNetlistCtx


class HlsNetlistPass():

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        raise NotImplementedError("Should be implemented in child class", self)
