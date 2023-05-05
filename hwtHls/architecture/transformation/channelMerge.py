from itertools import islice
import re
from typing import List, Union, Dict, Tuple, Set, Optional

from hwt.code import Concat
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_nodes, \
    link_hls_nodes, unlink_hls_node_input_if_exists, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtils import hasInputSameDriver
from hwt.hdl.types.hdlType import HdlType
from hwtHls.netlist.nodes.orderable import HdlType_isVoid
from hwt.pyUtils.uniqList import UniqList

AnyChannelIo = Union[HlsNetNodeRead, HlsNetNodeWrite]


def archElmEdgeSortKey(archElmChannelKeyValue: Tuple[Tuple[ArchElement, int, ArchElement, int], List[AnyChannelIo]], elmIndex: Dict[ArchElement, int]) -> Tuple[int, int, int, int]:
    ((srcElm, srcClkI, dstElm, dstClkI), _) = archElmChannelKeyValue
    return (elmIndex[srcElm], srcClkI, elmIndex[dstElm], dstClkI)


RE_MATCH_REG_TO_BB = re.compile("^bb(\d+)_to_bb(\d+)(_r\d+)((_src)|(_in)|(_out)|(_dst))?$")
RE_MATCH_REG = re.compile("^_r(\d+)$")


class RtlArchPassChannelMerge(RtlArchPass):
    """
    Merge forward and backward channels if they are between same source and destination (ArchElement, clockIndex) and do have same skipWhen and extraCond conditions.

    :note: It is important to reduce number of channels as much as possible to reduce synchronisation complexity and to remove combinational loops
        in handshake control logic.
    """

    def scheduleConcats(self, o: HlsNetNodeOut):
        """
        Run scheduling on
        """
        newlyScheduledNodes: List[HlsNetNode] = []
        n = o.obj
        if n.scheduledZero is None:
            assert isinstance(n, HlsNetNodeOperator) and n.operator == AllOps.CONCAT, n

            # add all not scheduled nodes to elmTimeSlot
            toSearch = [n]
            seen = set()
            while toSearch:
                n1 = toSearch.pop()
                if n1 not in seen and n1.scheduledZero is None:
                    newlyScheduledNodes.append(n1)
                    seen.add(n1)
                    for dep in n1.dependsOn:
                        toSearch.append(dep.obj)
            n.scheduleAsap(None, 0, None)
        return newlyScheduledNodes

    def _generatePrettyBufferName(self, writes: List[HlsNetNodeWrite]) -> Optional[str]:
        """
        Try to parse names of writes and create nice sorted name out of it for a channel which will contain all writes.
        """
        # srcbb, dstbb, regNo
        regs: List[Tuple[int, int, int]] = []
        nonstdNames = []
        for w in writes:
            if w.name is not None:
                m = RE_MATCH_REG_TO_BB.match(w.name)
                if m is None:
                    nonstdNames.append(w.name)
                else:
                    srcBb = int(m.group(1))
                    dstBb = int(m.group(2))
                    for r in RE_MATCH_REG.findall(m.group(3)):
                        reg = int(r)
                        regs.append((srcBb, dstBb, reg))

        regs.sort()
        prevEdge = None
        nameBuff = []
        for (srcBb, dstBb, r) in regs:
            e = (srcBb, dstBb)
            if prevEdge != e:
                nameBuff.append(f"bb{e[0]:d}_to_bb{e[1]:d}")
                prevEdge = e
            nameBuff.append(f"r{r:d}")

        nameBuff.extend(nonstdNames)
        if not nameBuff:
            return None
        else:
            return "_".join(nameBuff)

    def _resolveMergedChannelInitValuesOfWrites(self, writes: List[Union[HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge]]):
        """
        Resolve concatenation of channel init values from write nodes.
        :note: the values will be concatenated in lsb first manner.
        :note: init value is expected to be in format ((,), ...) or ((v0,), ...) where v0 is int or BitsVal
        """
        curWidth = writes[0].associatedRead._outputs[0]._dtype.bit_length()
        init = list(writes[0].channelInitValues)
        for w in islice(writes, 1, None):
            width = w.associatedRead._outputs[0]._dtype.bit_length()
            if width != 0:
                assert len(init) == len(w.channelInitValues)
                for i, (cur, new) in enumerate(zip(init, w.channelInitValues)):
                    if isinstance(cur, tuple) and len(cur) == 1 and isinstance(new, tuple) and len(new) == 1:
                        cur = cur[0]
                        new = new[0]

                        if isinstance(cur, int):
                            if isinstance(new, int):
                                cur |= new << curWidth
                            elif HdlType_isVoid(new._dtype):
                                continue
                            elif new._is_full_valid():
                                cur |= int(new) << curWidth
                            else:
                                cur = Concat(new, Bits(curWidth).from_py(cur))
                        else:
                            if isinstance(new, int):
                                cur = Concat(Bits(width).from_py(new), cur)
                            elif HdlType_isVoid(new._dtype):
                                continue
                            else:
                                cur = Concat(new, cur)
                        cur = (cur,)
                    else:
                        raise NotImplementedError(new, cur)

                    init[i] = cur

                curWidth += width

        return init

    def _changeDataTypeOfChannel(self,
                                 r0: Union[HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge],
                                 w0: Union[HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge],
                                 newT: HdlType,
                                 newBuffName: str):
        """
        Update type of HsStructIntf instances and node ports for new read and write node.
        """
        r0.name = f"{newBuffName}_dst"
        r0OrigSrc = r0.src
        if r0.src is not None:
            intf = HsStructIntf()
            intf.T = newT
            r0.src = intf

        r0._outputs[0]._dtype = newT
        
        w0.name = f"{newBuffName}_src"
        if w0.dst is not None:
            if w0.dst is r0OrigSrc:
                w0.dst = r0.src
            else:
                intf = HsStructIntf()
                intf.T = newT
                w0.dst = intf
        
    def _removeIoNodesAfterTheyWereMergetToFirstOne(self, r0: Union[HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge],
                                                    w0: Union[HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge],
                                                    r0O0OrigT: HdlType, r0Users: Tuple[HlsNetNodeIn, ...],
                                                    selectedForRewrite: List[Union[HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge]],
                                                    srcElm: ArchElement, srcClkI: int,
                                                    dstElm: ArchElement, dstClkI: int,
                                                    removed: Set[HlsNetNode]):
        builder: HlsNetlistBuilder = r0.netlist.builder
        r0O0 = r0._outputs[0]
        offset = 0
        for w in selectedForRewrite:
            r: Union[HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge] = w.associatedRead
            rO0 = r._outputs[0]
            if r is r0:
                rUsers = r0Users
                rO0T = r0O0OrigT
            else:
                rUsers = tuple(r.usedBy[0])
                rO0T = rO0._dtype

                unlink_hls_nodes(w.dependsOn[0], w._inputs[0])
                unlink_hls_node_input_if_exists(w.extraCond)
                unlink_hls_node_input_if_exists(w.skipWhen)
                if w._dataVoidOut is not None:
                    builder.replaceOutput(w._dataVoidOut, w0.getDataVoidOutPort(), True)

                unlink_hls_node_input_if_exists(r.skipWhen)
                unlink_hls_node_input_if_exists(r.skipWhen)
                if r._dataVoidOut is not None:
                    builder.replaceOutput(r._dataVoidOut, r0.getDataVoidOutPort(), True)
                if r._valid is not None:
                    builder.replaceOutput(r._valid, r0.getValid(), True)
                if r._validNB is not None:
                    builder.replaceOutput(r._validNB, r0.getValidNB(), True)

            if rUsers:
                newV = builder.buildIndexConstSlice(rO0T, r0O0, offset + rO0T.bit_length(), offset)
                newV.obj.scheduleAsap(None, 0, None)
                for u in rUsers:
                    if rO0 is not r0O0:
                        unlink_hls_nodes(rO0, u)
                    link_hls_nodes(newV, u)
            if r is not r0:
                removed.add(w)
                removed.add(r)

            offset += rO0T.bit_length()

        srcElmClkSlot = srcElm.getStageForClock(srcClkI)
        srcElmClkSlot[:] = (n for n in srcElmClkSlot if n not in removed)
        srcElm.allNodes = UniqList(n for n in srcElm.allNodes if n not in removed)
        if srcElm is not dstElm:
            dstElm.allNodes = UniqList(n for n in dstElm.allNodes if n not in removed)
            
        if srcElm is not dstElm or srcClkI != dstClkI:
            dstElmClkSlot = dstElm.getStageForClock(dstClkI)
            dstElmClkSlot[:] = (n for n in dstElmClkSlot if n not in removed)
        
    def _mergeChannels(self, selectedForRewrite: List[Union[HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge]],
                        dbgTracer: DebugTracer,
                        srcElm: ArchElement, srcClkI: int,
                        dstElm: ArchElement, dstClkI: int,
                        removed: Set[HlsNetNode]):
        """
        Merge several channels represented by HlsNetNodeRead-HlsNetNodeWrite pair to a single one of wider width.
        :attention: The channels must have same control flags and must be from same clock period slot in same ArchElement.
        """
        w0 = selectedForRewrite[0]
        builder: HlsNetlistBuilder = w0.netlist.builder
        for io in islice(selectedForRewrite, 1, None):
            assert io.__class__ is w0.__class__, ("Merge of channels of different classes may have unintended consequences", io, w0)

        dbgTracer.log(("merging ", selectedForRewrite), lambda x: f"{x[0]}, {[(io._id, io.associatedRead._id) for io in x[1]]}")
        wValues = [n.dependsOn[0] for n in selectedForRewrite if not HdlType_isVoid(n.dependsOn[0]._dtype)]
        newWVal = builder.buildConcatVariadic(wValues)
        newlyScheduledNodes = self.scheduleConcats(newWVal)
        clkPeriod = w0.netlist.normalizedClkPeriod
        for n in newlyScheduledNodes:
            clkI = indexOfClkPeriod(n.scheduledZero, clkPeriod)
            assert clkI <= srcClkI, (clkI, srcClkI, [io._id for io in selectedForRewrite])
            srcElm.getStageForClock(clkI).append(n)

        for n in islice(selectedForRewrite, 1, None):
            for n0 in (n, n.associatedRead):
                for i in (n0._inputOfCluster, n0._outputOfCluster):
                    dep = n0.dependsOn[i.in_i]
                    unlink_hls_nodes(dep, i)
                    n0._removeInput(i.in_i)
                    if not any(dep.obj.usedBy):
                        removed.add(dep.obj)

                netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n0, None)

        newBuffName = self._generatePrettyBufferName(selectedForRewrite)
        newInit = self._resolveMergedChannelInitValuesOfWrites(selectedForRewrite)  # important to do before type of w0 is altered
        r0: Union[HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge] = w0.associatedRead
        unlink_hls_nodes(w0.dependsOn[0], w0._inputs[0])
        newT = Bits(sum(wv._dtype.bit_length() for wv in wValues))
        
        r0Users = tuple(r0.usedBy[0])
        r0O0 = r0._outputs[0]
        r0O0OrigT = r0O0._dtype
        for u in r0Users:
            unlink_hls_nodes(r0O0, u)
        
        self._changeDataTypeOfChannel(r0, w0, newT, newBuffName)
       
        w0.channelInitValues = newInit
        link_hls_nodes(newWVal, w0._inputs[0])
        self._removeIoNodesAfterTheyWereMergetToFirstOne(r0, w0, r0O0OrigT, r0Users, selectedForRewrite,
                                                         srcElm, srcClkI, dstElm, dstClkI, removed)

    def _detectChannes(self, allocator: HlsAllocator):
        """
        Find all HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge, HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge
        and associate them to clock period index and ArchElement where it is connected.
        """
        channelToLocation: Dict[AnyChannelIo, Tuple[ArchElement, int, List[HlsNetNode]]] = {}
        channels: Dict[Tuple[ArchElement, int, ArchElement, int], List[AnyChannelIo]] = {}
        allWrites: List[HlsNetNodeWrite] = []
        for elm in allocator._archElements:
            elm: ArchElement
            for clkI, nodes in elm.iterStages():
                for n in nodes:
                    if isinstance(n, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)):
                        channelToLocation[n] = (elm, clkI, nodes)
                    elif isinstance(n, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)):
                        channelToLocation[n] = (elm, clkI, nodes)
                        allWrites.append(n)

        for w in allWrites:
            wLoc = channelToLocation[w]
            r = w.associatedRead
            rLoc = channelToLocation[r]
            k = (wLoc[0], wLoc[1], rLoc[0], rLoc[1])
            channelList = channels.get(k, None)
            if channelList is None:
                channels[k] = channelList = [w, ]
            else:
                channelList.append(w)
        return channels

    def apply(self, hls:"HlsScope", allocator: HlsAllocator):
        channels = self._detectChannes(allocator)
        reachDb: HlsNetlistAnalysisPassReachabilility = None
        elmIndex = {elm: i for i, elm in enumerate(allocator._archElements)}
        removed: Set[HlsNetNode] = allocator.netlist.builder._removedNodes
        MergeCandidateList = Union[List[HlsNetNodeWriteBackedge], List[HlsNetNodeWriteForwardedge]]
        dbgTracer = DebugTracer(None)
        with dbgTracer.scoped(RtlArchPassChannelMerge, None):
            for (srcElm, srcClkI, dstElm, dstClkI), ioList in sorted(
                    channels.items(),
                    key=lambda kv: archElmEdgeSortKey(kv, elmIndex)):
                srcElm: ArchElement
                if len(ioList) > 1:
                    for i, io0 in enumerate(ioList):
                        if io0 in removed:
                            continue
                        # find io nodes which have same skipWhen and extraCond flags
                        ioWithSameSyncFlags: MergeCandidateList = []
                        isForwrard = isinstance(io0, HlsNetNodeWriteForwardedge)
                        if not isForwrard:
                            assert isinstance(io0, HlsNetNodeWriteBackedge), io0

                        for io1 in islice(ioList, i + 1, None):
                            if io1 in removed:
                                continue
                            
                            elif isForwrard and not isinstance(io1, HlsNetNodeWriteForwardedge):
                                continue
                            elif not isForwrard and not isinstance(io1, HlsNetNodeWriteBackedge):
                                continue
                                
                            elif hasInputSameDriver(io0.extraCond, io1.extraCond) \
                                    and hasInputSameDriver(io0.skipWhen, io1.skipWhen):
                                ioWithSameSyncFlags.append(io1)

                        if len(ioWithSameSyncFlags) > 1:
                            # dbgTracer.log(("found potentially mergable ports", ioWithSameSyncFlags), lambda x: f"{x[0]} {[n._id for n in x[1]]}")
                            if reachDb is None:
                                # lazy load reachDb from performance reasons
                                reachDb = allocator.netlist.getAnalysis(HlsNetlistAnalysisPassReachabilility(allocator.netlist))

                            # discard those which data inputs are driven from io0
                            selectedForRewrite: MergeCandidateList = [io0]
                            for io1 in ioWithSameSyncFlags:
                                if len(io0.channelInitValues) == len(io1.channelInitValues):
                                    compatible = True
                                    for io0 in selectedForRewrite:
                                        if reachDb.doesReachToData(io0, io1.dependsOn[0]):
                                            compatible = False
                                            break
                                        if reachDb.doesReachToData(io1, io0.dependsOn[0]):
                                            compatible = False
                                            break
                                    if compatible:
                                        selectedForRewrite.append(io1)

                            if len(selectedForRewrite) > 1:
                                self._mergeChannels(selectedForRewrite, dbgTracer,
                                                    srcElm, srcClkI, dstElm, dstClkI, removed)

            allocator.netlist.filterNodesUsingSet(removed)