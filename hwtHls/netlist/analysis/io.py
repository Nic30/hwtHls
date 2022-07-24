from typing import Union, Dict, List

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, \
    HlsNetNodeExplicitSync, HOrderingVoidT
from hwtHls.netlist.nodes.ports import HlsNetNodeIn
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync


class HlsNetlistAnalysisPassDiscoverIo(HlsNetlistAnalysisPass):
    """
    Discover netlist nodes responsible for IO operations and associated synchonization.
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.ioByInterface: Dict[Interface, List[Union[HlsNetNodeRead, HlsNetNodeWrite]]] = {}
        self.interfaceList: UniqList[Interface] = UniqList() 
        self.extraReadSync: Dict[HlsNetNodeRead, HlsNetNodeExplicitSync] = {}
    
    def _detectExplicitSyncIsSameClkCycle(self, dataIn: HlsNetNodeIn, clkEndTime: int):
        if dataIn.obj.scheduledIn[dataIn.in_i] > clkEndTime:
            return
        obj = dataIn.obj
        if isinstance(obj, (HlsNetNodeWrite, HlsNetNodeReadSync)):
            # HlsNetNodeReadSync is not dependent on channel data
            # HlsNetNodeWrite is end of data thread
            return

        if obj.__class__ is HlsNetNodeExplicitSync:
            yield dataIn.obj
        else:
            for o, users in zip(obj._outputs, obj.usedBy):
                if o._dtype != HOrderingVoidT:
                    for u in users:
                        u: HlsNetNodeIn
                        yield from self._detectExplicitSyncIsSameClkCycle(u, clkEndTime)
        
    def run(self):
        assert not self.ioByInterface
        assert self.netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassRunScheduler) is not None, "Should be performed only after scheduling"
        ioByInterface = self.ioByInterface
        interfaceList = self.interfaceList
        for op in self.netlist.inputs:
            op: HlsNetNodeRead
            i = op.src
            assert isinstance(i, (RtlSignalBase, InterfaceBase)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList  is None:
                opList = ioByInterface[i] = []
                interfaceList.append(i)
            opList.append(op)
            clkEndTime = start_clk(op.scheduledOut[0], self.netlist.normalizedClkPeriod) + self.netlist.normalizedClkPeriod
            extraSync = None
            for u in op.usedBy[0]:
                for sync in self._detectExplicitSyncIsSameClkCycle(u, clkEndTime):
                    assert extraSync is None or extraSync is sync, ("There can be only one extra HlsNetNodeExplicitSync node per read", op, extraSync, sync)
                    extraSync = sync

            if extraSync is not None:
                self.extraReadSync[op] = extraSync

        for op in self.netlist.outputs:
            op: HlsNetNodeWrite
            i = op.dst
            assert isinstance(i, (RtlSignalBase, InterfaceBase)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList  is None:
                opList = ioByInterface[i] = []
                interfaceList.append(i)
            opList.append(op)

