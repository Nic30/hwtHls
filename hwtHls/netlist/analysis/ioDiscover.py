from itertools import chain
from typing import Union, Dict, List

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup


class HlsNetlistAnalysisPassIoDiscover(HlsNetlistAnalysisPass):
    """
    Discover netlist nodes responsible for IO operations and associated synchronization.
    :note:Primary use for this analysis is to
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.ioByInterface: Dict[Interface, UniqList[Union[HlsNetNodeRead, HlsNetNodeWrite]]] = {}
        self.interfaceList: UniqList[Interface] = UniqList()

    def runOnHlsNetlist(self, netlist: "HlsNetlistCtx"):
        assert not self.ioByInterface, "Must be run only once"
        netlist = self.netlist
        assert netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassRunScheduler) is not None, "Should be performed only after scheduling"
        ioByInterface = self.ioByInterface
        interfaceList = self.interfaceList
        outputs: List[HlsNetNodeWrite] = []

        for op in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if isinstance(op, HlsNetNodeRead):
                pass
            elif isinstance(op, HlsNetNodeWrite):
                outputs.append(op)
                continue
            else:
                assert op.__class__ is not HlsNetNodeExplicitSync, ("nodes of this type should already been lowered", op)
                assert not isinstance(op, HlsNetNodeReadSync), ("nodes of this type should already been lowered", op)
                continue

            op: HlsNetNodeRead
            i = op.src
            if i is None:
                continue

            assert isinstance(i, (RtlSignalBase, InterfaceBase, MultiPortGroup, BankedPortGroup)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList is None:
                opList = ioByInterface[i] = UniqList()
                interfaceList.append(i)

            opList.append(op)

        for op in chain(netlist.outputs, outputs):
            op: HlsNetNodeWrite
            i = op.dst
            if i is None:
                continue
            assert isinstance(i, (tuple, RtlSignalBase, InterfaceBase, MultiPortGroup, BankedPortGroup)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList  is None:
                opList = ioByInterface[i] = UniqList()
                interfaceList.append(i)
            opList.append(op)

