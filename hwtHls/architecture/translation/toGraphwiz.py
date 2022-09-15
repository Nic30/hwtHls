import html
from pydot import Dot, Node, Edge
from typing import Optional, Dict, List, Tuple

from hwt.hdl.types.hdlType import HdlType
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getInterfaceName
from hwt.synthesizer.unit import Unit


class RtlArchToGraphwiz():

    def __init__(self, name:str, allocator: HlsAllocator, parentUnit: Unit):
        self.graph = Dot(name)
        self.allocator = allocator
        self.parentUnit = parentUnit
        self.interfaceToNodes: Dict[InterfaceBase, Node] = {}
        self.archElementToNode: Dict[ArchElement, Node] = {}

    def _getInterfaceNode(self, i: InterfaceBase):
        try:
            return self.interfaceToNodes[i]
        except KeyError:
            pass
        
        nodeId = len(self.graph.obj_dict['nodes'])
        n = Node(f"n{nodeId:d}", shape="plaintext")
        name = html.escape(getInterfaceName(self.parentUnit, i))
        bodyRows = []
        if isinstance(i, InterArchElementHandshakeSync):
            bodyRows.append(f'<tr port="0"><td colspan="2">{name:s}</td><td>{html.escape(i.__class__.__name__)}</td></tr>')
            for _, dst in i.data:
                bodyRows.append(f"<tr><td></td><td>{html.escape(dst.data.name):s}</td><td>{html.escape(repr(dst.data._dtype))}</td></tr>")
        else:
            bodyRows.append(f'<tr port="0"><td>{name:s}</td><td>{html.escape(i.__class__.__name__)}</td></tr>')

        bodyStr = "\n".join(bodyRows)
        label = f'<<table border="0" cellborder="1" cellspacing="0">{bodyStr:s}</table>>'
        n.set("label", label)
        self.graph.add_node(n)
        self.interfaceToNodes[i] = n
        return n

    def _getElementIndexOfTime(self, elm: ArchElement, t: int):
        clkPeriod = self.allocator.netlist.normalizedClkPeriod
        if isinstance(elm, ArchElementFsm):
            elm: ArchElementFsm
            return elm.fsm.clkIToStateI[start_clk(t, clkPeriod)]

        elif isinstance(elm, ArchElementPipeline):
            elm: ArchElementPipeline
            return t // clkPeriod

        else:
            raise NotImplementedError()
        
    def construct(self):
        g = self.graph
        allocator: HlsAllocator = self.allocator
        
        interElementConnections: Dict[Tuple[ArchElement, int, ArchElement, int], List[str, HdlType]] = {}
        interElementConnectionsOrder = []
        for elm in allocator._archElements:
            elm: ArchElement
            nodeId = len(g.obj_dict['nodes'])
            elmNode = Node(f"n{nodeId:d}", shape="plaintext")
            g.add_node(elmNode)
            self.archElementToNode[elm] = elmNode

            nodeRows = ['<<table border="0" cellborder="1" cellspacing="0">\n']
            name = html.escape(f"{elm.namePrefix:s}: {elm.__class__.__name__:s}")
            nodeRows.append(f"    <tr><td colspan='3'>{name:s}</td></tr>\n")
            for i, con in enumerate(elm.connections):
                nodeRows.append(f"    <tr><td port='i{i:d}'>i{i:d}</td><td>st{i:d}</td><td port='o{i:d}'>o{i:d}</td></tr>\n")
                con: ConnectionsOfStage
                # [todo] global inputs with bgcolor ligtred global outputs with lightblue color
                
                for intf in con.inputs:
                    iN = self._getInterfaceNode(intf)
                    e = Edge(f"{iN.get_name():s}:0", f"n{nodeId:d}:i{i:d}")
                    g.add_edge(e)
                
                for intf in con.outputs:
                    oN = self._getInterfaceNode(intf)
                    e = Edge(f"n{nodeId:d}:o{i:d}", f"{oN.get_name():s}:0")
                    g.add_edge(e)
                
            nodeRows.append('</table>>')
        
            elmNode.set("label", "".join(nodeRows))
            for n in elm.allNodes:
                if isinstance(n, HlsNetNodeWriteBackwardEdge):
                    n: HlsNetNodeWriteBackwardEdge
                    if n.allocateAsBuffer:
                        wN = self._getInterfaceNode(n.dst)
                        rN = self._getInterfaceNode(n.associated_read.src)
                        e = Edge(f"{wN.get_name():s}:0", f"{rN.get_name():s}:0", style="dashed", color="gray")
                        g.add_edge(e)
                    else:
                        t0 = self._getElementIndexOfTime(elm, n.scheduledIn[0])
                        t1 = self._getElementIndexOfTime(elm, n.associated_read.scheduledOut[0])
                        key = (elm, t0, elm, t1)
                        vals = interElementConnections.get(key, None)
                        if vals is None:
                            vals = interElementConnections[key] = []
                            interElementConnectionsOrder.append(key)
                        vals.append((n.buff_name, n._outputs[0]._dtype))

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


class RtlArchPassToGraphwiz(RtlArchPass):

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
