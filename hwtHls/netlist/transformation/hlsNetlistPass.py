from hwtHls.netlist.context import HlsNetlistCtx


class HlsNetlistPass():

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx, *args, **kwargs):
        #from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
        for cb in netlist.callbacksBeforePass:
            cb(self.__class__, self, netlist)
        pa = self.runOnHlsNetlistImpl(netlist, *args, **kwargs)
        for cb in netlist.callbacksAfterPass:
            cb(self.__class__, self, netlist)
        # assert isinstance(pa, PreservedAnalysisSet), (self.__class__, "runOnHlsNetlistImpl should return PreservedAnalysisSet", pa)
        assert netlist.subNodes, ("Netlist was completly optimized out", self)
        netlist.invalidateAnalysisUsingPreservedAnalysisSet(pa)

    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx, *args, **kwargs):
        raise NotImplementedError("Should be implemented in child class", self)
