from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPass():

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx, *args, **kwargs):
        log = netlist._dbgLogPassExec
        if log is not None:
            log.write(f"Running analysis: {self.__class__.__name__} on {netlist}\n")
        pa = self.runOnHlsNetlistImpl(netlist, *args, **kwargs)
        assert isinstance(pa, PreservedAnalysisSet), (self.__class__, "runOnHlsNetlistImpl should return PreservedAnalysisSet", pa)
        if not pa.isAll:
            if not pa:
                for v in netlist._analysis_cache.values():
                    v.invalidate(netlist)
            else:
                toRm = []
                for k, v in netlist._analysis_cache.items():
                    if k in pa or k.__class__ in pa:
                        continue
                    else:
                        toRm.append(k)
                for k in toRm:
                    netlist.invalidateAnalysis(k)

    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        raise NotImplementedError("Should be implemented in child class", self)
