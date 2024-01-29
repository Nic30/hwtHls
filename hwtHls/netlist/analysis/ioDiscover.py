from functools import lru_cache
from itertools import chain
from typing import Union, Dict, List, Set

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk


class HlsNetlistAnalysisPassIoDiscover(HlsNetlistAnalysisPass):
    """
    Discover netlist nodes responsible for IO operations and associated synchronization.
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.ioByInterface: Dict[Interface, List[Union[HlsNetNodeRead, HlsNetNodeWrite]]] = {}
        self.interfaceList: UniqList[Interface] = UniqList()
        self.extraReadSync: Dict[HlsNetNodeRead, UniqList[HlsNetNodeExplicitSync]] = {}

    @lru_cache(int(1e6))
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
                if o._dtype != HVoidOrdering:
                    for u in users:
                        u: HlsNetNodeIn
                        yield from self._detectExplicitSyncIsSameClkCycleFromOutputs(u, clkEndTime)

    # def _detectExplicitSyncIsSameClkCycleFromInputs(self, dataOut: HlsNetNodeOut, clkStartTime: int):
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
    #            if dep._dtype != HVoidOrdering and dep._dtype != HVoidExternData:
    #                yield from self._detectExplicitSyncIsSameClkCycleFromInputs(dep, clkStartTime)
    #
    @classmethod
    def _findIo(cls, n: HlsNetNodeAggregate, inputs: List[HlsNetNodeRead], outputs: List[HlsNetNodeWrite]):
        for sn in n._subNodes:
            if isinstance(sn, HlsNetNodeRead):
                inputs.append(sn)
            elif isinstance(sn, HlsNetNodeWrite):
                outputs.append(sn)
            elif isinstance(sn, HlsNetNodeAggregate):
                cls._findIo(n, inputs, outputs)

    def run(self):
        assert not self.ioByInterface, "Must be run only once"
        netlist = self.netlist
        assert netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassRunScheduler) is not None, "Should be performed only after scheduling"
        ioByInterface = self.ioByInterface
        interfaceList = self.interfaceList
        resolvedExplicitSync: Set[HlsNetNodeExplicitSync] = set()
        clkPeriod = netlist.normalizedClkPeriod
        inputs: List[HlsNetNodeRead] = []
        outputs: List[HlsNetNodeWrite] = []
        for n in netlist.nodes:
            if isinstance(n, HlsNetNodeAggregate):
                self._findIo(n, inputs, outputs)

        for op in chain(netlist.inputs, inputs):
            op: HlsNetNodeRead
            i = op.src
            if i is None:
                continue
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

        for op in chain(netlist.outputs, outputs):
            op: HlsNetNodeWrite
            i = op.dst
            if i is None:
                continue
            assert isinstance(i, (tuple, RtlSignalBase, InterfaceBase)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList  is None:
                opList = ioByInterface[i] = []
                interfaceList.append(i)
            opList.append(op)

            # clkStartTime = start_clk(op.scheduledOut[0], clkPeriod) * clkPeriod
            # extraSync = self.extraReadSync.get(op, None)
            # for sync in self._detectExplicitSyncIsSameClkCycleFromInputs(op.dependsOn[0], clkStartTime):
            #    if extraSync is None:
            #        extraSync = self.extraReadSync[op] = UniqList()
            #    extraSync.append(sync)
            #    resolvedExplicitSync.add(sync)

        # for n in netlist.nodes:
        #    if isinstance(n, HlsNetNodeExplicitSync) and n not in resolvedExplicitSync:
        #        assert n in resolvedExplicitSync, (n, "Sync was not assigned to any IO, this is likely to result in internal deadlock.")
