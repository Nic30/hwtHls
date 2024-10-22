from collections import OrderedDict
import html
from pydot import Dot, Node, Edge
from typing import Optional, Dict, List, Tuple, Union

from hwt.hwIO import HwIO
from hwt.hwModule import HwModule
from hwt.mainBases import HwIOBase
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_getName
from hwtHls.architecture.analysis.handshakeSCCs import ArchSyncNodeTy
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage  # , IORecord
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.translation.dumpNodesDot import COLOR_INPUT_READ, \
    COLOR_OUTPUT_WRITE, COLOR_SPECIAL_PURPOSE
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtLib.handshaked.streamNode import ValidReadyTuple
from ipCorePackager.constants import DIRECTION
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.syncUtils import HwIO_getSyncTuple

ArchElementEdge = Tuple[ArchElement, int, ArchElement, int]


def isSelfEdge(e: ArchElementEdge):
    return e[0:2] == e[2:4]


ListOfConnections = List[Tuple[DIRECTION, Union[Tuple[HlsNetNodeWrite,
                                                      Optional[ValidReadyTuple],
                                                      Optional[ValidReadyTuple]], HlsNetNodeOut]]]


class InterElementConections(OrderedDict[Tuple[ArchElement, int],
                                         OrderedDict[Tuple[ArchElement, int], ListOfConnections]]):

    def __setitem__(self, *args) -> None:
        raise AssertionError("Use insert method instead")

    def insert(self,
               src: Tuple[ArchElement, int],
               dst: Tuple[ArchElement, int],
               v: Union[HlsNetNodeWriteAnyChannel,
                        HlsNetNodeOut],
               isReversed:bool=False):
        # out means that it is in the direction of arrow to node with table of connections
        # :note: we must order src, dst because we need to keep unique record for every inter element connections
        if (dst[0]._id, dst[1]) < (src[0]._id, src[1]):
            dir_ = DIRECTION.IN
            src, dst = dst, src
        else:
            dir_ = DIRECTION.OUT
        if isReversed:
            dir_ = DIRECTION.opposite(dir_)

        _interElementCon = self.get(src, None)
        if _interElementCon is None:
            _interElementCon = OrderedDict()
            OrderedDict.__setitem__(self, src, _interElementCon)

        vals = _interElementCon.get(dst, None)
        if vals is None:
            vals = _interElementCon[dst] = []

        if isinstance(v, tuple):
            w = v[0]
            for i, item in enumerate(vals):
                if isinstance(item, tuple) and item[1][0] is w:
                    # merge records
                    assert item[0] != dir_, ("There should not be any duplicated items, just records for an opposite directions")
                    _, writeRV, readRV = item[1]
                    _, newWriteRV, newReadRV = v
                    if newWriteRV is None:
                        newWriteRV = writeRV
                    else:
                        assert writeRV is None, (v, item)
                    if newReadRV is None:
                        newReadRV = readRV
                    else:
                        assert readRV is None, (v, item)
                    vals[i] = (item[0], (w, newWriteRV, newReadRV))
                    return

        vals.append((dir_, v))


class RtlArchToGraphviz():
    """
    Class which translates RTL architecture from HlsNetlistCtx instance to a Graphviz dot graph for visualization purposes.
    """

    def __init__(self, name:str, netlist: HlsNetlistCtx, parentHwModule: HwModule,
                 fsmStateEncoding:Optional[HlsAndRtlNetlistAnalysisPassFsmStateEncoding]):
        self.graph = Dot(name)
        self.netlist = netlist
        self.parentHwModule = parentHwModule
        self.fsmStateEncoding = fsmStateEncoding
        self.interfaceToNodes: Dict[Union[HwIOBase, Tuple[ArchSyncNodeTy, ArchSyncNodeTy]], Node] = {}
        self.archElementToNode: Dict[ArchElement, Node] = {}
        self._hsSccsNodes: Dict[int, Node] = {}

    def _getInterfaceNode(self, i: HwIOBase, bgcolor:str):
        try:
            return self.interfaceToNodes[i]
        except KeyError:
            pass

        nodeId = len(self.graph.obj_dict['nodes'])
        n = Node(f"n{nodeId:d}", shape="plaintext")
        name = "None" if i is None else\
            html.escape(HwIO_getName(self.parentHwModule, i)) if isinstance(i, (HwIOBase, RtlSignalBase)) else\
            html.escape(repr(i))
        bodyRows = []
        bodyRows.append(f'<tr port="0"><td>{name:s}</td><td>{html.escape(i.__class__.__name__)}</td></tr>')

        bodyStr = "\n".join(bodyRows)
        label = f'<<table  bgcolor="{bgcolor:s}" border="0" cellborder="1" cellspacing="0">{bodyStr:s}</table>>'
        n.set("label", label)
        self.graph.add_node(n)
        self.interfaceToNodes[i] = n
        return n

    def _getNodeForInterElementConnections(self, srcElm: ArchElement, srcClkI: int, dstElm: ArchElement, dstClkI: int,
                                           members: ListOfConnections,
                                           tableStyle:str=""):
        """
        :param members: list of tuple(direction, driving output), direction is used
            because we may look at output from side of element with output or from side of element with
            connected input
        """

        nodeId = len(self.graph.obj_dict['nodes'])
        n = Node(f"n{nodeId:d}", shape="plaintext")
        name = (f"{srcElm._id:d} {html.escape(srcElm.name):s} {srcClkI}clk {html.escape('->'):s}"
                f" {dstElm._id:d} {html.escape(dstElm.name):s} {dstClkI:d}clk")
        bodyRows = []
        bodyRows.append(f'<tr port="0"><td colspan="4">{name:s}</td></tr>')
        for direction, out in members:
            if isinstance(out, HlsNetNodeOut):
                name = f"o{out.out_i} {out.name}" if out.name else f"o{out.out_i}"
                internNode = out.obj._outputsInside[out.out_i]
                if internNode.dependsOn:
                    internName = internNode.dependsOn[0].getPrettyName()
                else:
                    internName = "None"
                bodyRows.append(f"<tr><td>{direction.name}</td>"
                                f"<td>{html.escape(name):s}</td>"
                                f"<td>{html.escape(internName):s}</td>"
                                f"<td>{html.escape(repr(out._dtype))}</td></tr>")
            else:
                outNode = out
                writeVldRdyTuple = HwIO_getSyncTuple(outNode.dst) if outNode.dst is not None else None
                readVldRdyTuple = HwIO_getSyncTuple(outNode.associatedRead.src) if outNode.associatedRead.src is not None else None

                name = outNode.name
                if not name:
                    name = f"n{outNode._id}"
                elif name.endswith("_src") and outNode.associatedRead.name.endswith("_dst"):
                    name = name[:-4]  # cur of common suffix

                if outNode.isBackedge():
                    FOrB = 'B'
                else:
                    FOrB = 'F'

                capacity = outNode._getBufferCapacity()

                if writeVldRdyTuple is not None:
                    wVR = html.escape(self._stringFormatValidReadTupleType(writeVldRdyTuple))
                else:
                    wVR = ""

                if readVldRdyTuple is not None:
                    rVR = html.escape(self._stringFormatValidReadTupleType(readVldRdyTuple))
                else:
                    rVR = ""

                bodyRows.append(f"<tr><td>{direction.name} {FOrB:s} {f'{capacity:d} item(s)' if capacity else ''}</td>"
                                f"<td>{outNode._id:d}{wVR:s}{html.escape('->'):s}{outNode.associatedRead._id:d}{rVR}</td>"
                                f"<td>{html.escape(name)}</td>"
                                f"<td>{html.escape(repr(outNode.associatedRead._portDataOut._dtype))}</td></tr>")
                # connectedComponent = self._tryToFindComponentConnectedToInterface(i, direction)
                # if edgeInfo is not None:
                #    capacity, breaksReadyChain = edgeInfo
                #    assert capacity >= 0, (edgeInfo, capacity)
                #    if capacity > 0:
                #        bodyRows.append(f'<tr><td>capacity</td><td>{capacity}</td></tr>')
                #    if breaksReadyChain:
                #        bodyRows.append(f'<tr><td>breaksReadyChain</td><td></td></tr>')

        bodyStr = "\n".join(bodyRows)
        label = f'<<table {tableStyle:s} border="0" cellborder="1" cellspacing="0">{bodyStr:s}</table>>'
        n.set("label", label)
        self.graph.add_node(n)
        return n

    # @staticmethod
    # def _collectBufferInfo(netlist: HlsNetlistCtx):
    #    bufferInfo: Dict[HwIOBase, Tuple[int, HwIOBase]] = {}
    #
    #    for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
    #        if isinstance(n, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)):
    #            n: HlsNetNodeWriteBackedge
    #            if n.dst is None:
    #                continue
    #            if n.allocationType == CHANNEL_ALLOCATION_TYPE.BUFFER:
    #                breaksReadyChain = isinstance(n, HlsNetNodeWriteBackedge)
    #                bufferInfo[n.dst] = (n._getBufferCapacity(), breaksReadyChain)
    #            elif n.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
    #                bufferInfo[n.dst] = (1, True)
    #
    #    return bufferInfo

    @staticmethod
    def _stringFormatValidReadTupleType(validReady: ValidReadyTuple):
        valid, ready = validReady
        hasValid = not isinstance(valid, int)
        hasReady = not isinstance(ready, int)
        if hasValid and hasReady:
            return "<v,r>"
        elif hasValid:
            return "<v>"
        elif hasReady:
            return "<r>"
        else:
            return "<>"

    @staticmethod
    def _getReadHwIO(hwIO: Optional[HwIO], rNode: HlsNetNodeRead):
        if hwIO is not None:
            return hwIO
        hwIO = rNode.src
        if hwIO is None:
            if isinstance(rNode, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)):
                hwIO = rNode.associatedWrite
            else:
                hwIO = rNode
        return hwIO

    @staticmethod
    def _getWriteHwIO(hwIO: Optional[HwIO], wNode: HlsNetNodeWrite):
        if hwIO is None:
            hwIO = wNode
        return hwIO

    def constructArchElementNodeRows(self, elm: ArchElement, isFsm:bool, isPipeline:bool, nodeRows: List[str]):
        """
        Construct rows for table inside of body of node representing ArchElement
        """
        _fsmStateEncoding = self.fsmStateEncoding
        if isFsm and _fsmStateEncoding is not None:
            stateEncoding = _fsmStateEncoding.stateEncoding[elm]
        else:
            stateEncoding = None

        for clkI, st in elm.iterStages():
            try:
                con: ConnectionsOfStage = elm.connections[clkI]
            except IndexError:
                raise AssertionError("Defect connections in", elm, clkI)
            if con is None:
                continue
            #  or (elm._beginClkI is not None and
            #              clkI < elm._beginClkI)
            if not st:
                # assert not con.isUnused(), con
                # skip unused stages
                continue

            if stateEncoding is not None:
                stVal = stateEncoding[clkI]
                label = f"st{stVal:d}-clk{clkI}"
            else:
                label = f"clk{clkI}"

            nodeRows.append(f"    <tr><td port='i{clkI:d}'>i{clkI:d}</td><td>{label:s}</td><td port='o{clkI:d}'>o{clkI:d}</td></tr>\n")

    def collectConnectedChannelsAndConstructIO(self, elm: ArchElement, iec: InterElementConections, nodeId:int, g: Dot):
        for clkI, st in elm.iterStages():
            con: ConnectionsOfStage = elm.connections[clkI]
            if con is None:
                continue
            if not st or (elm._beginClkI is not None and clkI < elm._beginClkI):
                # assert not con.isUnused(), con
                # skip unused stages
                continue

            # seen = set()
            for node in st:

            # for ioRecord in con.inputs:
            #    ioRecord: IORecord
            #    node = ioRecord.node
                if isinstance(node, HlsNetNodeRead):
                    #  add to iec for later construction
                    w = node.associatedWrite
                    if w is None or w.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                        # this is local only channel
                        continue

                    dstElm = elm
                    dstClkI = clkI
                    srcElm = w.parent
                    assert srcElm is not None, w
                    srcClkI = self._getIndexOfTime(w.scheduledIn[0])
                    iec.insert((srcElm, srcClkI), (dstElm, dstClkI), w, isReversed=True)
                # else:
                #    # construct and connect node for input read
                #    hwIO = ioRecord.io
                #    hwIO = self._getReadHwIO(hwIO, node)
                #    if hwIO in seen:
                #        continue
                #    seen.add(hwIO)
                #    iN = self._getInterfaceNode(hwIO, COLOR_INPUT_READ)
                #    label = self._stringFormatValidReadTupleType(ioRecord.validReady)
                #    # link connecting element node slot with node for interface
                #    e = Edge(f"{iN.get_name():s}:0", f"n{nodeId:d}:i{clkI:d}",
                #             label=f"{node._id} {html.escape(label)}",
                #             color=COLOR_INPUT_READ)
                #    g.add_edge(e)
                #
            # seen.clear()
            # for ioRecord in con.outputs:
            #    ioRecord: IORecord
            #    node = ioRecord.node
            #    assert node, node
                elif isinstance(node, HlsNetNodeWrite):
                    #  add to iec for later construction
                    if node.associatedRead is None or node.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                        # this is local only channel
                        continue
                    srcElm = elm
                    srcClkI = clkI
                    r = node.associatedRead
                    dstElm = r.parent
                    dstClkI = self._getIndexOfTime(r.scheduledZero)
                    iec.insert((srcElm, srcClkI), (dstElm, dstClkI), node)

                # else:
                #    # construct and connect node for output write
                #    hwIO = self._getWriteHwIO(ioRecord.io, node)
                #    if hwIO in seen:
                #        continue
                #    seen.add(hwIO)
                #    oN = self._getInterfaceNode(hwIO, COLOR_OUTPUT_WRITE)
                #    label = self._stringFormatValidReadTupleType(ioRecord.validReady)
                #    # link connecting element node slot with node for interface
                #    e = Edge(f"n{nodeId:d}:o{clkI:d}", f"{oN.get_name():s}:0",
                #             label=f"{node._id:d} {html.escape(label)}",
                #             color=COLOR_OUTPUT_WRITE)
                #    g.add_edge(e)

    def construct(self):
        g = self.graph
        netlist = self.netlist
        # bufferInfo = self._collectBufferInfo(netlist)
        interElementCon: InterElementConections = InterElementConections()
        for elm in netlist.iterAllNodes():
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
            elif isinstance(elm, ArchElementNoImplicitSync):
                color = COLOR_SPECIAL_PURPOSE
            else:
                color = "white"

            nodeRows = [f'<<table bgcolor="{color:s}" border="0" cellborder="1" cellspacing="0">\n']
            name = html.escape(f"{elm._id:d}: {elm.name:s}: {elm.__class__.__name__:s}")
            nodeRows.append(f"    <tr><td colspan='3'>{name:s}</td></tr>\n")
            self.constructArchElementNodeRows(elm, isFsm, isPipeline, nodeRows)
            nodeRows.append('</table>>')
            elmNode.set("label", "".join(nodeRows))

            self.collectConnectedChannelsAndConstructIO(elm, interElementCon, nodeId, g)
            # collect meta for data passed by element _outputs
            for out, users, tSrc in zip(elm._outputs, elm.usedBy, elm.scheduledOut):
                for dstInput in users:
                    dstElm = dstInput.obj
                    assert dstElm.scheduledIn is not None, ("All nodes must be already scheduled", dstElm)
                    try:
                        t1 = dstElm.scheduledIn[dstInput.in_i]
                    except IndexError:
                        raise AssertionError("Input port object is broken", dstElm, dstInput)
                    srcClkI = self._getIndexOfTime(tSrc)
                    dstClkI = self._getIndexOfTime(t1)
                    src = (elm, srcClkI)
                    dst = (dstElm, dstClkI)

                    # self._addOutToInterElementConnections(dst, out, DIRECTION.OUT, interElementOutputs)
                    interElementCon.insert(src, dst, out)

            # for edge in interElementOutputs:
            #    edge: ArchElementEdge
            #    srcElm, srcClkI, dstElm, _ = edge
            #    connectionNode = self._getNodeForPorts(edge, interElementOutputs[edge])
            #    # edge from self to connectionNode
            #    attrs = {}
            #    if isSelfEdge(edge):
            #        attrs["dir"] = "both"
            #
            #    e = Edge(f"{elmNode.get_name():s}:o{srcClkI:d}", f"{connectionNode.get_name():s}:0", **attrs)
            #    g.add_edge(e)

            # for dep, tDst in zip(elm.dependsOn, elm.scheduledIn):
            #    srcElm = dep.obj
            #    tSrc = srcElm.scheduledOut[dep.out_i]
            #    edge = (srcElm, self._getIndexOfTime(tSrc), elm, self._getIndexOfTime(tDst))
            #    self._addOutToInterElementConnections(edge, dep, DIRECTION.OUT,
            #                                          interElementInputs)
            #
            # for edge in interElementInputs:
            #    edge: ArchElementEdge
            #    if isSelfEdge(edge):
            #        continue  # has <-> style arrow which is already constructed
            #    srcElm, _, dstElm, dstClkI = edge
            #    connectionNode = self._getNodeForPorts(edge, interElementInputs[edge])
            #    # edge from connection node to dst
            #    # :note: if srcElm == dstElm keep all edges on right side to improve readability
            #    e = Edge(f"{connectionNode.get_name():s}:0", f"{elmNode.get_name():s}:{'o' if srcElm == dstElm else 'i'}{dstClkI:d}")
            #    g.add_edge(e)

        # [todo] remove
        # self._connectWriteToReadForChannels(g)

        # construct connections aggregated in interElementCon
        archElmToNode = self.archElementToNode
        attrsEmpty = {}
        attrsEmptyBack = {"constraint": False}
        attrsSpecialColor = {"color": COLOR_SPECIAL_PURPOSE}
        attrsSpecialColorBack = {**attrsSpecialColor, **attrsEmptyBack}

        for (srcElm, srcClkI), dsts in interElementCon.items():
            for (dstElm, dstClkI), members in dsts.items():
                hasSpecialSyncMeaning = isinstance(srcElm, ArchElementNoImplicitSync) or isinstance(dstElm, ArchElementNoImplicitSync)
                if hasSpecialSyncMeaning:
                    # tableStyle = f'bgcolor="{COLOR_SPECIAL_PURPOSE:s}"'
                    if srcClkI > dstClkI:
                        edgeAtts = attrsSpecialColorBack
                    else:
                        edgeAtts = attrsSpecialColor
                else:
                    if srcClkI > dstClkI:
                        edgeAtts = attrsEmptyBack
                    else:
                        edgeAtts = attrsEmpty
                n = self._getNodeForInterElementConnections(srcElm, srcClkI, dstElm, dstClkI, members)
                src = archElmToNode[srcElm]
                dst = archElmToNode[dstElm]
                e = Edge(f"{src.get_name():s}:o{srcClkI:d}", n.get_name(), **edgeAtts)
                g.add_edge(e)
                io = 'i'
                if srcElm is dstElm:
                    io = 'o'  # keep bout edges on same side of the same element to improve readability
                e = Edge(n.get_name(), f"{dst.get_name():s}:{io:s}{dstClkI:d}", **edgeAtts)
                g.add_edge(e)

    # @staticmethod
    # def _addOutToInterElementConnections(
    #        edge: ArchElementEdge, out: HlsNetNodeOut,
    #        direction: DIRECTION,
    #        interElementConnections: Dict[ArchElementEdge, List[Tuple[DIRECTION, HlsNetNodeOut]]]):
    #    vals = interElementConnections.get(edge, None)
    #    if vals is None:
    #        vals = interElementConnections[edge] = []
    #    vals.append((direction, out))

    # def _connectWriteToReadForChannels(self, g: Dot):
    #    for n in self.netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
    #        if isinstance(n, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)):
    #            n: HlsNetNodeWriteBackedge
    #            wHwIO = self._getWriteHwIO(n.dst, n)
    #            wN = self.interfaceToNodes.get(wHwIO)
    #            if wN is None:
    #                continue
    #            rHwIO = self._getReadHwIO(n.associatedRead.src if n.associatedRead else None, n.associatedRead)
    #            rN = self.interfaceToNodes.get(rHwIO)
    #            if rN is None:
    #                continue
    #            init = n.associatedRead.channelInitValues
    #            if init:
    #                initStr = f" init:{html.escape(repr(init))}"
    #            else:
    #                initStr = ""
    #            # link connecting read and write node
    #            e = Edge(f"{wN.get_name():s}:0", f"{rN.get_name():s}:0",
    #                     style="dashed", color="gray",
    #                     label=f"{n._id:d}->{n.associatedRead._id:d}{initStr}")
    #            g.add_edge(e)
    #
    def _getIndexOfTime(self, t: int):
        clkPeriod = self.netlist.normalizedClkPeriod
        return t // clkPeriod

    def dumps(self):
        return self.graph.to_string()


class RtlArchAnalysisPassDumpArchDot(HlsArchAnalysisPass):

    def __init__(self, outStreamGetter:Optional[OutputStreamGetter]=None, auto_open=False):
        self.outStreamGetter = outStreamGetter
        self.auto_open = auto_open

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        name = netlist.label
        fsmStateEncoding = netlist.getAnalysisIfAvailable(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        toGraphviz = RtlArchToGraphviz(name, netlist, netlist.parentHwModule, fsmStateEncoding)
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphviz.construct()
            out.write(toGraphviz.dumps())
        finally:
            if doClose:
                out.close()
