from hwtHls.netlist.context import HlsNetlistCtx


class HlsNetlistPass():

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx, *args, **kwargs):
        log = netlist._dbgLogPassExec
        if log is not None:
            log.write(f"Running analysis: {self.__class__.__name__} on {netlist}\n")
        self.runOnHlsNetlistImpl(netlist, *args, **kwargs)

    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        raise NotImplementedError("Should be implemented in child class", self)
