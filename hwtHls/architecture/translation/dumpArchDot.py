import html
from pydot import Dot, Node, Edge
from typing import Optional, Dict, List, Tuple

from hwt.hdl.types.hdlType import HdlType
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getInterfaceName
from hwt.synthesizer.unit import Unit
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.platform.fileUtils import OutputStreamGetter
#from ipCorePackager.constants import DIRECTION
#from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
#from hwt.hdl.portItem import HdlPortItem
#from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
#from math import ceil


class RtlArchToGraphwiz():
    """
    Class which translates RTL architecutre from HlsAllocator instance to a Graphwiz dot graph for visualization purposes.
    """
    def __init__(self, name:str, allocator: HlsAllocator, parentUnit: Unit):
        self.graph = Dot(name)
        self.allocator = allocator
        self.parentUnit = parentUnit
        self.interfaceToNodes: Dict[InterfaceBase, Node] = {}
        self.archElementToNode: Dict[ArchElement, Node] = {}
    
    # def _tryToFindComponentConnectedToInterface(self, i: InterfaceBase, direction: DIRECTION):
    #    if direction == DIRECTION.IN:
    #        mainSig = i.vld
    #    else:
    #        assert direction == DIRECTION.OUT, i
    #        mainSig = i.rd
    #
    #    mainSigDriver = mainSig._sig.drivers[0]
    #    if isinstance(mainSigDriver, HdlAssignmentContainer):
    #        tmpIoSig = mainSigDriver.src
    #        ioSigPort = tmpIoSig.drivers[0]
    #        if isinstance(ioSigPort, HdlPortItem):
    #            return ioSigPort.unit
    #    return None
    #
    def _getInterfaceNode(self, i: InterfaceBase, edgeInfo: Optional[Tuple[int, bool]]):
        try:
            return self.interfaceToNodes[i]
        except KeyError:
            pass

        nodeId = len(self.graph.obj_dict['nodes'])
        n = Node(f"n{nodeId:d}", shape="plaintext")
        name = html.escape(getInterfaceName(self.parentUnit, i)) if i is not None else "None"
        bodyRows = []
        if isinstance(i, InterArchElementHandshakeSync):
            bodyRows.append(f'<tr port="0"><td colspan="2">{name:s}</td><td>{html.escape(i.__class__.__name__)}</td></tr>')
            for _, dst in i.data:
                bodyRows.append(f"<tr><td></td><td>{html.escape(dst.data.name):s}</td><td>{html.escape(repr(dst.data._dtype))}</td></tr>")
        else:
            bodyRows.append(f'<tr port="0"><td>{name:s}</td><td>{html.escape(i.__class__.__name__)}</td></tr>')
        
        # connectedComponent = self._tryToFindComponentConnectedToInterface(i, direction)
        if edgeInfo is not None:
            capacity, breaksReadyChain = edgeInfo
            bodyRows.append(f'<tr><td>capacity</td><td>{capacity}</td></tr>')
            if breaksReadyChain:
                bodyRows.append(f'<tr><td>breaksReadyChain</td><td></td></tr>')
            
        bodyStr = "\n".join(bodyRows)
        label = f'<<table border="0" cellborder="1" cellspacing="0">{bodyStr:s}</table>>'
        n.set("label", label)
        self.graph.add_node(n)
        self.interfaceToNodes[i] = n
        return n

    def _getElementIndexOfTime(self, elm: ArchElement, t: int):
        clkPeriod = self.allocator.netlist.normalizedClkPeriod
        return t // clkPeriod

    @staticmethod
    def _collectBufferInfo(allocator: HlsAllocator):
        bufferInfo: Dict[InterfaceBase, Tuple[int, InterfaceBase]] = {}
        clkPeriod = allocator.netlist.normalizedClkPeriod
        
        for elm in allocator._archElements:
            elm: ArchElement
            for n in elm.allNodes:
                if isinstance(n, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)):
                    n: HlsNetNodeWriteBackedge
                    if n.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
                        breaksReadyChain = isinstance(n, HlsNetNodeWriteBackedge)
                        bufferInfo[n.dst] = (n._getSizeOfBuffer(clkPeriod), breaksReadyChain)
        return bufferInfo

    def construct(self):
        g = self.graph
        allocator: HlsAllocator = self.allocator

        interElementConnections: Dict[Tuple[ArchElement, int, ArchElement, int], List[str, HdlType]] = {}
        interElementConnectionsOrder = []
        bufferInfo = self._collectBufferInfo(allocator)
        for elm in allocator._archElements:
            elm: ArchElement
            nodeId = len(g.obj_dict['nodes'])
            elmNode = Node(f"n{nodeId:d}", shape="plaintext")
            g.add_node(elmNode)
            self.archElementToNode[elm] = elmNode

            isFsm = isinstance(elm, ArchElementFsm)
            isPipeline = isinstance(elm, ArchElementPipeline)
            if isFsm:
                color = "plum"
            elif isPipeline:
                color = "lime"
            else:
                color = "white"
            nodeRows = [f'<<table bgcolor="{color:s}" border="0" cellborder="1" cellspacing="0">\n']
            name = html.escape(f"{elm.namePrefix:s}: {elm.__class__.__name__:s}")
            nodeRows.append(f"    <tr><td colspan='3'>{name:s}</td></tr>\n")
            for clkI, st in elm.iterStages():
                con: ConnectionsOfStage = elm.connections[clkI]

                if not st or (elm._beginClkI is not None and clkI < elm._beginClkI):
                    assert not con.inputs, ("Must not have IO before begin of pipeline", elm, elm._beginClkI, clkI, con.inputs)
                    assert not con.outputs, ("Must not have IO before begin of pipeline", elm, elm._beginClkI, clkI, con.outputs)
                    assert not con.io_extraCond, ("Must not have IO before begin of pipeline", elm, elm._beginClkI, clkI)
                    assert not con.io_skipWhen, ("Must not have IO before begin of pipeline", elm, elm._beginClkI, clkI)
                    assert not con.signals, ("Must not have IO before begin of pipeline", elm, elm._beginClkI, clkI)
                    # skip unused stages
                    continue

                if isFsm:
                    stVal = elm.stateEncoding[clkI]
                elif isPipeline:
                    stVal = clkI
                else:
                    raise NotImplementedError(elm)
                nodeRows.append(f"    <tr><td port='i{clkI:d}'>i{clkI:d}</td><td>st{stVal:d}-clk{clkI}</td><td port='o{clkI:d}'>o{clkI:d}</td></tr>\n")
                # [todo] global inputs with bgcolor ligtred global outputs with lightblue color

                for intf, isBlocking in con.inputs:
                    iN = self._getInterfaceNode(intf, bufferInfo.get(intf))
                    e = Edge(f"{iN.get_name():s}:0", f"n{nodeId:d}:i{clkI:d}", label='' if isBlocking else ' non-blocking')
                    g.add_edge(e)

                for intf, isBlocking  in con.outputs:
                    oN = self._getInterfaceNode(intf, bufferInfo.get(intf))
                    e = Edge(f"n{nodeId:d}:o{clkI:d}", f"{oN.get_name():s}:0", label='' if isBlocking else ' non-blocking')
                    g.add_edge(e)

            nodeRows.append('</table>>')

            elmNode.set("label", "".join(nodeRows))
            for n in elm.allNodes:
                if isinstance(n, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)):
                    n: HlsNetNodeWriteBackedge
                    if n.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
                        wN = self._getInterfaceNode(n.dst, bufferInfo.get(n.dst))
                        rN = self._getInterfaceNode(n.associatedRead.src, bufferInfo.get(n.associatedRead.src))
                        
                        e = Edge(f"{wN.get_name():s}:0", f"{rN.get_name():s}:0", style="dashed", color="gray")
                        g.add_edge(e)
                    else:
                        t0 = self._getElementIndexOfTime(elm, n.scheduledIn[0])
                        if n.associatedRead:
                            t1 = self._getElementIndexOfTime(elm, n.associatedRead.scheduledOut[0])
                        else:
                            t1 = t0 + 1
                        key = (elm, t0, elm, t1)
                        vals = interElementConnections.get(key, None)
                        if vals is None:
                            vals = interElementConnections[key] = []
                            interElementConnectionsOrder.append(key)
                        vals.append((n.buffName, n._outputs[0]._dtype))

        # iea: InterArchElementNodeSharingAnalysis = allocator._iea
        # for o, i in iea.interElemConnections:
        #    o: HlsNetNodeOut
        #    srcElm = iea.getSrcElm(o)
        #    for dstElm in iea.ownerOfInput[i]:
        #        if srcElm is dstElm:
        #            continue
        #        path = iea.explicitPathSpec.get((o, i, dstElm), None)
        #        if path is None:
        #            realSrcElm: ArchElement = iea.ownerOfOutput[o]
        #            assert srcElm is realSrcElm, (srcElm, realSrcElm)
        #            srcT = o.obj.scheduledOut[o.out_i]
        #            dstT = iea.firstUseTimeOfOutInElem[(dstElm, o)]
        #
        #            key = (srcElm, self._getElementIndexOfTime(srcElm, srcT), dstElm, self._getElementIndexOfTime(dstElm, dstT))
        #            vals = interElementConnections.get(key, None)
        #            if vals is None:
        #                vals = interElementConnections[key] = []
        #                interElementConnectionsOrder.append(key)
        #
        #            vals.append((f"{o.obj._id}:{o.out_i}", o._dtype))
        #
        #        else:
        #            raise NotImplementedError()
        #
        # for key in interElementConnectionsOrder:
        #    srcElm, srcStI, dstElm, dstStI = key
        #    srcNode = self.archElementToNode[srcElm]
        #    dstNode = self.archElementToNode[dstElm]
        #    variableNodeRows = ['<<table border="0" cellborder="1" cellspacing="0">\n']
        #    for name, dtype in interElementConnections[key]:
        #        dtypeStr = html.escape(repr(dtype))
        #        name = html.escape(name)
        #        variableNodeRows.append(f'    <tr><td>{name:s}</td><td>{dtypeStr}</td></tr>\n')
        #
        #    variableNodeRows.append('</table>>')
        #    nodeId = len(g.obj_dict['nodes'])
        #    variableTableNode = Node(f"n{nodeId:d}", shape="plaintext", label="".join(variableNodeRows))
        #    g.add_node(variableTableNode)
        #
        #    tn = variableTableNode.get_name()
        #    e0 = Edge(f"{srcNode.get_name():s}:o{srcStI:d}", tn)
        #    g.add_edge(e0)
        #    e1 = Edge(tn, f"{dstNode.get_name():s}:i{dstStI:d}")
        #    g.add_edge(e1)

    def dumps(self):
        return self.graph.to_string()


class RtlArchPassDumpArchDot(RtlArchPass):

    def __init__(self, outStreamGetter:Optional[OutputStreamGetter]=None, auto_open=False):
        self.outStreamGetter = outStreamGetter
        self.auto_open = auto_open

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        name = netlist.label
        toGraphwiz = RtlArchToGraphwiz(name, netlist.allocator, netlist.parentUnit)
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphwiz.construct()
            out.write(toGraphwiz.dumps())
        finally:
            if doClose:
                out.close()
