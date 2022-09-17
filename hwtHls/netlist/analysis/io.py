from typing import Union, Dict, List, Set

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, \
    HlsNetNodeExplicitSync, HOrderingVoidT, HExternalDataDepT
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.scheduler.clk_math import start_clk


class HlsNetlistAnalysisPassDiscoverIo(HlsNetlistAnalysisPass):
    """
    Discover netlist nodes responsible for IO operations and associated synchronization.
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.ioByInterface: Dict[Interface, List[Union[HlsNetNodeRead, HlsNetNodeWrite]]] = {}
        self.interfaceList: UniqList[Interface] = UniqList() 
        self.extraReadSync: Dict[HlsNetNodeRead, UniqList[HlsNetNodeExplicitSync]] = {}
    
    def _detectExplicitSyncIsSameClkCycleFromOutputs(self, dataIn: HlsNetNodeIn, clkEndTime: int):
        if dataIn.obj.scheduledIn[dataIn.in_i] > clkEndTime:
            return
        obj = dataIn.obj
        if isinstance(obj, (HlsNetNodeWrite, HlsNetNodeReadSync)):
            # HlsNetNodeReadSync is not dependent on channel data
            # HlsNetNodeWrite is end of data thread
            return

        if obj.__class__ is HlsNetNodeExplicitSync:
            yield obj
        else:
            for o, users in zip(obj._outputs, obj.usedBy):
                if o._dtype != HOrderingVoidT:
                    for u in users:
                        u: HlsNetNodeIn
                        yield from self._detectExplicitSyncIsSameClkCycleFromOutputs(u, clkEndTime)
    
    #def _detectExplicitSyncIsSameClkCycleFromInputs(self, dataOut: HlsNetNodeOut, clkStartTime: int):
    #    if dataOut.obj.scheduledOut[dataOut.out_i] < clkStartTime:
    #        return
    #    obj = dataOut.obj
    #    if isinstance(obj, (HlsNetNodeRead, HlsNetNodeReadSync)):
    #        # HlsNetNodeReadSync is not dependent on channel data
    #        # HlsNetNodeRead is start of data thread
    #        return
    #
    #    if obj.__class__ is HlsNetNodeExplicitSync:
    #        yield obj
    #    else:
    #        for dep in  obj.dependsOn:
    #            if dep._dtype != HOrderingVoidT and dep._dtype != HExternalDataDepT:
    #                yield from self._detectExplicitSyncIsSameClkCycleFromInputs(dep, clkStartTime)
    #
    def run(self):
        assert not self.ioByInterface
        assert self.netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassRunScheduler) is not None, "Should be performed only after scheduling"
        ioByInterface = self.ioByInterface
        interfaceList = self.interfaceList
        resolvedExplicitSync: Set[HlsNetNodeExplicitSync] = set()
        clkPeriod = self.netlist.normalizedClkPeriod
        for op in self.netlist.inputs:
            op: HlsNetNodeRead
            i = op.src

            assert isinstance(i, (RtlSignalBase, InterfaceBase)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList is None:
                opList = ioByInterface[i] = []
                interfaceList.append(i)

            opList.append(op)
            clkEndTime = (start_clk(op.scheduledOut[0], clkPeriod) + 1) * clkPeriod
            extraSync = self.extraReadSync.get(op, None)
            for u in op.usedBy[0]:
                for sync in self._detectExplicitSyncIsSameClkCycleFromOutputs(u, clkEndTime):
                    if extraSync is None:
                        extraSync = self.extraReadSync[op] = UniqList()
                    extraSync.append(sync)
                    resolvedExplicitSync.add(sync)

        for op in self.netlist.outputs:
            op: HlsNetNodeWrite
            i = op.dst
            assert isinstance(i, (RtlSignalBase, InterfaceBase)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList  is None:
                opList = ioByInterface[i] = []
                interfaceList.append(i)
            opList.append(op)
            
            #clkStartTime = start_clk(op.scheduledOut[0], clkPeriod) * clkPeriod
            #extraSync = self.extraReadSync.get(op, None)
            #for sync in self._detectExplicitSyncIsSameClkCycleFromInputs(op.dependsOn[0], clkStartTime):
            #    if extraSync is None:
            #        extraSync = self.extraReadSync[op] = UniqList()
            #    extraSync.append(sync)
            #    resolvedExplicitSync.add(sync)

        for n in self.netlist.nodes:
            if isinstance(n, HlsNetNodeExplicitSync) and n not in resolvedExplicitSync:
                assert n in resolvedExplicitSync, (n, "Sync was not assigned to any IO, this is likely to result in internal deadlock.")
