from typing import Dict, Union

from hwt.hwIO import HwIO
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
from hwtHls.netlist.analysis.nodeParentAggregate import HlsNetlistAnalysisPassNodeParentAggregate
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwt.pyUtils.typingFuture import override
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup


class RtlArchPassIoPortPrivatization(RtlArchPass):
    """
    This pass divides port groups and assigns specific IO ports to a specific read/write nodes in a specific ArchElement instance.

    :note: Because circuit is after if-conversion the IO operations in same clock cycle are predicted to be concurrent.

    Assignment rules:
      * The scheduler asserts the limit of IO operations on specified IO port in same clock cycle.
      * The minimum amount of IO ports by ArchElement is derived from max number of IO per clock cycle in that element. 
      * IO port must be connected exactly to 1 arch. element.
      * list-scheduling algorithm is used to assign which IO port is used by which IO operation
    """

    def _privatizePortToIo(self,
                           elm: ArchElement,
                           ioNode: Union[HlsNetNodeRead, HlsNetNodeWrite],
                           port: HwIO,
                           ioDiscovery: HlsNetlistAnalysisPassIoDiscover,
                           portOwner: Dict[HwIO, ArchElement]):
        ioNodes = ioDiscovery.ioByInterface.get(port, None)
        if ioNodes is None:
            ioNodes = ioDiscovery.ioByInterface[port] = []
        ioNodes.append(ioNode)
        if port not in portOwner:
            ioDiscovery.interfaceList.append(port)
            portOwner[port] = elm
        if isinstance(ioNode, HlsNetNodeRead):
            ioNode.src = port
        else:
            assert isinstance(ioNode, HlsNetNodeWrite), ioNode
            ioNode.dst = port

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        ioDiscovery: HlsNetlistAnalysisPassIoDiscover = netlist.getAnalysis(HlsNetlistAnalysisPassIoDiscover)
        ioByInterface = ioDiscovery.ioByInterface
        hierarchy: HlsNetlistAnalysisPassNodeParentAggregate = netlist.getAnalysis(HlsNetlistAnalysisPassNodeParentAggregate)
        # clkPeriod: SchedTime = allocator.netlist.normalizedClkPeriod
        portOwner: Dict[HwIO, ArchElement] = {}
        # for each FSM we need to keep pool of assigned ports so we can reuse it in next clock cycle
        # because the ports can be shared between clock cycles.
        # fsmPortPool: Dict[Tuple[ArchElementFsm, Tuple[HwIO]], List[HwIO]] = {}
        for io in ioDiscovery.interfaceList:
            if isinstance(io, (MultiPortGroup, BankedPortGroup)):
                freePorts = list(reversed(io))  # reversed so we allocate ports with lower index fist
                ioNodes = ioByInterface.pop(io)  # operations which are using this port group
                for ioNode in sorted(ioNodes, key=lambda n: n.scheduledZero):
                    ioNode: Union[HlsNetNodeRead, HlsNetNodeWrite]
                    # clkIndex = indexOfClkPeriod(ioNode, ioNode.scheduledZero)
                    isRead = isinstance(ioNode, HlsNetNodeRead)
                    if not isRead:
                        assert isinstance(ioNode, HlsNetNodeWrite), ioNode
                    # [todo] update after ArchElement update
                    elm = hierarchy.nodePath[ioNode][0]
                    assert isinstance(elm, ArchElement), ("node should be placed in ArchElement and ArchElement instances should be only at top level")

                    elm: ArchElement
                    if isinstance(elm, ArchElementPipeline):
                        # different stages must not reuse same port
                        port = freePorts.pop()
                    elif isinstance(elm, ArchElementFsm):
                        # different states may reuse same port and reuse is preferred
                        raise NotImplementedError(elm)
                    else:
                        raise NotImplementedError(elm)
                    self._privatizePortToIo(elm, ioNode, port, ioDiscovery, portOwner)

        ioDiscovery.interfaceList[:] = (io for io in ioDiscovery.interfaceList if not isinstance(io, tuple))
