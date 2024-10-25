from collections import OrderedDict
from typing import Dict, Union, Tuple, List

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsArchPassIoPortPrivatization(HlsArchPass):
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

    def _constructArbitrationLogic(self, arbiterElm: ArchElementPipeline,
                                   ioPort: HwIO,
                                   ioNodes: List[Union[HlsNetNodeRead, HlsNetNodeWrite]],
                                   userSyncNodes: OrderedDict[Union[ArchElement, Tuple[ArchElement, int]], List[HlsNetNodeExplicitSync]],
                                   portOwner: Dict[HwIO, Union[ArchElement, Tuple[ArchElement, int]]]):

        # 1 port n users
        # * the ioNode must occupy only a single clock window
        # * arbiter will have 1 clock window occupied with a logic which will perform arbitration and multiplexing
        # * if io does not have ready or valid signal it must be added, it is required to notify request and availability of the io port
        netlist = arbiterElm.netlist
        nodesForArbitration = []
        firstN = next(iter(userSyncNodes.items()))[1][0]
        isRead = isinstance(firstN, HlsNetNodeRead)
        if not isRead:
            assert isinstance(firstN, HlsNetNodeWrite), firstN

        for _, ioNodesInUser in userSyncNodes.items():
            # for all user nodes reroute all io ports of io nodes to a new virtual IO which will connect arbiter and
            # user node, potentially ready/valid rtl sync must be added to the io
            for n in ioNodesInUser:
                if isRead:
                    assert isinstance(n, HlsNetNodeRead), (n, "Ports should be divided to reads/writes in advance")
                    if n._rtlUseReady and n._rtlUseValid:
                        n: HlsNetNodeRead
                        n.src = None
                        assert n.associatedWrite is None
                        inArbiterW = HlsNetNodeWrite(netlist, None, mayBecomeFlushable=False)
                        inArbiterW.associateRead(n)
                        inArbiterW.allocationType = CHANNEL_ALLOCATION_TYPE.IMMEDIATE
                        inArbiterW.setNonBlocking()
                    else:
                        raise NotImplementedError(n)

                    nodesForArbitration.append(inArbiterW)

                else:
                    assert isinstance(n, HlsNetNodeWrite)
                    t = n.dependsOn[n._portSrc.in_i]._dtype
                    if n._rtlUseReady and n._rtlUseValid:
                        n: HlsNetNodeRead
                        n.dst = None
                        assert n.associatedRead is None
                        inArbiterR = HlsNetNodeRead(netlist, None, t)
                        n.associateRead(inArbiterR)
                        n.allocationType = CHANNEL_ALLOCATION_TYPE.IMMEDIATE
                        n._mayBecomeFlushable = False
                        inArbiterR.setNonBlocking()
                    else:
                        # IO does not have control signals necessary for stalling of producer
                        # ArchElements 
                        raise NotImplementedError(n)

                    nodesForArbitration.append(inArbiterR)

        assert len(nodesForArbitration) > 1, nodesForArbitration
        if isRead:
            rDataType = firstN._portDataOut._dtype
            wDataType = None
        else:
            rDataType = None
            wDataType = firstN.dependsOn[firstN._portSrc.in_i]._dtype

        anyPrevEnabled = None
        wDataMuxCases = []
        builder: HlsNetlistBuilder = arbiterElm.builder
        hasWData = wDataType is not None and not HdlType_isNonData(wDataType)
        hasRData = rDataType is not None and not HdlType_isNonData(rDataType)
        for isLast, n in iter_with_last(nodesForArbitration):
            if isRead:
                # :note the original port was read
                assert isinstance(n, HlsNetNodeWrite), n
                req = n.getReadyNB()  # user signalizes the request for read
            else:
                # :note: the original port was write, now we are arbitrating read from io to individual
                # reads in
                req = n.getValidNB()  # user signalizes the request for write

            if hasWData:
                wDataMuxCases.append(n._portDataOut)
                if not isLast:
                    wDataMuxCases.append(req)
            
            n.assignRealization(OpRealizationMeta(mayBeInFFStoreTime=True))
            n._setScheduleZeroTimeSingleClock(0)
            arbiterElm._addNodeIntoScheduled(0, n, allowNewClockWindow=True)
                
            if anyPrevEnabled is None:
                assert not isLast
                anyPrevEnabled = req
            else:
                n.addControlSerialExtraCond(builder.buildNot(anyPrevEnabled), addDefaultScheduling=True)
                n.addControlSerialSkipWhen(anyPrevEnabled, addDefaultScheduling=True)
                anyPrevEnabled = builder.buildOr(anyPrevEnabled, req)

        if isRead:
            newIoNode = HlsNetNodeRead(netlist, ioPort)
        else:
            newIoNode = HlsNetNodeWrite(netlist, ioPort, mayBecomeFlushable=False)

        newIoNode.assignRealization(OpRealizationMeta(mayBeInFFStoreTime=True))
        newIoNode._setScheduleZeroTimeSingleClock(0)
        arbiterElm._addNodeIntoScheduled(0, newIoNode)
        newIoNode.addControlSerialExtraCond(anyPrevEnabled, addDefaultScheduling=True)
        if hasWData:
            wData: HlsNetNodeOut = builder.buildMux(wDataType, tuple(wDataMuxCases))
            wData.connectHlsIn(newIoNode._portSrc)
        else:
            assert not wDataMuxCases, wDataMuxCases

        if hasRData:
            rData = newIoNode._portDataOut
            for n in nodesForArbitration:
                rData.connectHlsIn(n._portSrc)
        
        for n in arbiterElm.subNodes:
            if n.scheduledZero is None:
                n.assignRealization(OpRealizationMeta(mayBeInFFStoreTime=True))
                n._setScheduleZeroTimeSingleClock(0)
                arbiterElm._addNodeIntoScheduled(0, n)

        portOwner[ioPort] = arbiterElm
        ioNodes.append(newIoNode)
       
        
    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        ioDiscovery: HlsNetlistAnalysisPassIoDiscover = netlist.getAnalysis(HlsNetlistAnalysisPassIoDiscover)
        ioByInterface = ioDiscovery.ioByInterface
        # clkPeriod: SchedTime = allocator.netlist.normalizedClkPeriod
        portOwner: Dict[HwIO, Union[ArchElement, Tuple[ArchElement, int]]] = {}
        # :note: for each FSM we need to keep pool of assigned ports so we can reuse it in next clock cycle
        # because the ports can be shared between clock cycles.
        # fsmPortPool: Dict[Tuple[ArchElementFsm, Tuple[HwIO]], List[HwIO]] = {}
        # :note: for ports used by multiple ArchElements or ArchElementPipeline stages
        #   the arbiter must be generated

        for io in ioDiscovery.interfaceList:
            userSyncNodes: OrderedDict[Union[ArchElement, Tuple[ArchElement, int]], List[HlsNetNodeExplicitSync]] = OrderedDict()
            ioNodes = ioByInterface[io]
            if len(ioNodes) == 2:
                n0, n1 = ioNodes
                # check for case of channels between 2 elements
                if isinstance(n0, HlsNetNodeRead) and isinstance(n1, HlsNetNodeWrite):
                    continue
                if isinstance(n1, HlsNetNodeRead) and isinstance(n1, HlsNetNodeWrite):
                    continue
                
            for n in ioNodes:
                syncNode = n.getParentSyncNode()
                if isinstance(syncNode[0], ArchElementFsm):
                    syncNode = syncNode[0]

                siblings = userSyncNodes.get(syncNode, None)
                if siblings is None:
                    siblings = userSyncNodes[syncNode] = []
                siblings.append(n)

            if isinstance(io, (MultiPortGroup, BankedPortGroup)):
                freePorts = list(reversed(io))  # reversed so we allocate ports with lower index fist
                ioNodes = ioByInterface.pop(io)  # operations which are using this port group
                if len(userSyncNodes) > len(io):
                    raise NotImplementedError("Need to handle arbitration", io)

                for ioNode in sorted(ioNodes, key=lambda n: n.scheduledZero):
                    ioNode: Union[HlsNetNodeRead, HlsNetNodeWrite]
                    # clkIndex = indexOfClkPeriod(ioNode, ioNode.scheduledZero)
                    isRead = isinstance(ioNode, HlsNetNodeRead)
                    if not isRead:
                        assert isinstance(ioNode, HlsNetNodeWrite), ioNode
                    # [todo] update after ArchElement update
                    elm = ioNode.parent
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
            else:
                if len(userSyncNodes) != 1:
                    arbiterElm = ArchElementPipeline(netlist, f"arbiter_{io._name}", netlist.namePrefix)
                    arbiterElm.resolveRealization()
                    arbiterElm._setScheduleZeroTimeSingleClock(0)
                    netlist.addNode(arbiterElm)
                    self._constructArbitrationLogic(arbiterElm, io, ioNodes, userSyncNodes, portOwner)

        ioDiscovery.interfaceList[:] = (io for io in ioDiscovery.interfaceList if not isinstance(io, tuple))
        pa = PreservedAnalysisSet.preserveScheduling()
        pa.add(HlsNetlistAnalysisPassIoDiscover)
        return pa
