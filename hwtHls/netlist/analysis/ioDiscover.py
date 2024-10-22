from itertools import chain
from typing import Union, Dict, List

from hwt.hwIO import HwIO
from hwt.mainBases import HwIOBase
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsNetlistAnalysisPassIoDiscover(HlsNetlistAnalysisPass):
    """
    Discover netlist nodes responsible for IO operations and associated synchronization.
    :note:Primary use for this analysis is to
    """

    def __init__(self,):
        super(HlsNetlistAnalysisPassIoDiscover, self).__init__()
        self.ioByInterface: Dict[HwIO, SetList[Union[HlsNetNodeRead, HlsNetNodeWrite]]] = {}
        self.interfaceList: SetList[HwIO] = SetList()

    @override
    def runOnHlsNetlistImpl(self, netlist: "HlsNetlistCtx"):
        assert not self.ioByInterface, "Must be run only once"
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

            assert isinstance(i, (RtlSignalBase, HwIOBase, MultiPortGroup, BankedPortGroup)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList is None:
                opList = ioByInterface[i] = SetList()
                interfaceList.append(i)

            opList.append(op)

        for op in outputs:
            op: HlsNetNodeWrite
            i = op.dst
            if i is None:
                continue
            assert isinstance(i, (tuple, RtlSignalBase, HwIOBase, MultiPortGroup, BankedPortGroup)), (i, op)
            opList = ioByInterface.get(i, None)
            if opList  is None:
                opList = ioByInterface[i] = SetList()
                interfaceList.append(i)
            opList.append(op)

