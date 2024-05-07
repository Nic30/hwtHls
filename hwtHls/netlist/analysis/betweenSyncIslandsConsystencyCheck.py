from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassBetweenSyncIslandsConsystencyCheck(HlsNetlistPass):

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        syncNodes = netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassBetweenSyncIslands)
        assert syncNodes is not None, "HlsNetlistAnalysisPassBetweenSyncIslands analysis not present at all"
        for n in netlist.iterAllNodes():
            assert n in syncNodes.syncIslandOfNode, n
        
        seenInputs = {}
        seenOutputs = {}
        for isl in syncNodes.syncIslands:
            for i in isl.inputs:
                if i in seenInputs:
                    raise AssertionError("Input already input of a different island", i, seenInputs[i], isl)
                seenInputs[i] = isl
            for o in isl.outputs:
                if o in seenOutputs:
                    raise AssertionError("Output already output of a different island", o, seenOutputs[o], isl)
                seenOutputs[o] = isl
