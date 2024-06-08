from itertools import islice
import re
from typing import List, Union, Dict, Tuple, Set, Optional

from hwt.code import Concat
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIORdVldSync
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel, LoopChanelGroup
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_nodes, \
    link_hls_nodes, unlink_hls_node_input_if_exists, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.scheduler.scheduler import asapSchedulePartlyScheduled
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtils import hasInputSameDriver
from hwt.pyUtils.typingFuture import override


AnyChannelIo = Union[HlsNetNodeRead, HlsNetNodeWrite]


def archElmEdgeSortKey(archElmChannelKeyValue: Tuple[Tuple[ArchElement, int, ArchElement, int], List[AnyChannelIo]], elmIndex: Dict[ArchElement, int]) -> Tuple[int, int, int, int]:
    ((srcElm, srcClkI, dstElm, dstClkI), _) = archElmChannelKeyValue
    return (elmIndex[srcElm], srcClkI, elmIndex[dstElm], dstClkI)


RE_MATCH_REG_TO_BB = re.compile(r"^bb(\d+)_to_bb(\d+)(_r\d+)((_src)|(_in)|(_out)|(_dst))?$")
RE_MATCH_REG = re.compile(r"^_r(\d+)$")


class RtlArchPassChannelMerge(RtlArchPass):
    """
    Merge forward and backward channels if they are between the same source and destination (ArchElement, clockIndex)
    and do have same skipWhen and extraCond conditions.
    
    [todo] Cover the case where r0 channel read is non blocking and others reads have
        rN.extraCond=r0.validNB & r0.extraCond,
        rN.skipWhen=~r0.validNB | r0.skipWhen
        Such reads are usually on the entry of the loops. The r0 is usually a control flag which enables read of liveins.

    :note: It is important to reduce number of channels as much as possible
        to reduce synchronization complexity and to remove combinational loops
        in handshake control logic.
    """

    def __init__(self, dbgTracer: DebugTracer):
        super(RtlArchPassChannelMerge, self).__init__()
        self._dbgTracer = dbgTracer

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
                                cur = Concat(new, HBits(curWidth).from_py(cur))
                        else:
                            if isinstance(new, int):
                                cur = Concat(HBits(width).from_py(new), cur)
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
                                 r0: HlsNetNodeReadAnyChannel,
                                 w0: HlsNetNodeWriteAnyChannel,
                                 newT: HdlType,
                                 newBuffName: str):
        """
        Update type of HwIOStructRdVld instances and node ports for new read and write node.
        """
        r0.name = f"{newBuffName}_dst"
        r0OrigSrc = r0.src
        if r0.src is not None:
            if HdlType_isVoid(newT):
                hwIO = HwIORdVldSync()
            else:
                hwIO = HwIOStructRdVld()
                hwIO.T = newT
            r0.src = hwIO

        r0._outputs[0]._dtype = newT

        w0.name = f"{newBuffName}_src"
        if w0.dst is not None:
            if w0.dst is r0OrigSrc:
                w0.dst = r0.src
            else:
                if HdlType_isVoid(newT):
                    hwIO = HwIORdVldSync()
                else:
                    hwIO = HwIOStructRdVld()
                    hwIO.T = newT
                w0.dst = hwIO

    def _removeIoNodesAfterTheyWereMergedToFirstOne(self, r0: HlsNetNodeReadAnyChannel,
                                                    w0: HlsNetNodeWriteAnyChannel,
                                                    r0O0OrigT: HdlType, r0Users: Tuple[HlsNetNodeIn, ...],
                                                    selectedForRewrite: List[HlsNetNodeWriteAnyChannel],
                                                    srcElm: ArchElement, srcClkI: int,
                                                    dstElm: ArchElement, dstClkI: int,
                                                    removed: Set[HlsNetNode]):
        builder: HlsNetlistBuilder = r0.netlist.builder
        if r0 in srcElm._subNodes:
            builder = builder.scoped(srcElm)
        else:
            assert r0 in dstElm._subNodes, r0
            builder = builder.scoped(dstElm)

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

                unlink_hls_node_input_if_exists(r.extraCond)
                unlink_hls_node_input_if_exists(r.skipWhen)
                if r._dataVoidOut is not None:
                    builder.replaceOutput(r._dataVoidOut, r0.getDataVoidOutPort(), True)
                if r._valid is not None:
                    builder.replaceOutput(r._valid, r0.getValid(), True)
                if r._validNB is not None:
                    builder.replaceOutput(r._validNB, r0.getValidNB(), True)

            if rUsers:
                newV = builder.buildIndexConstSlice(rO0T, r0O0, offset + rO0T.bit_length(), offset, [])
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
        srcElm._subNodes = SetList(n for n in srcElm._subNodes if n not in removed)
        if srcElm is not dstElm:
            dstElm._subNodes = SetList(n for n in dstElm._subNodes if n not in removed)

        if srcElm is not dstElm or srcClkI != dstClkI:
            dstElmClkSlot = dstElm.getStageForClock(dstClkI)
            dstElmClkSlot[:] = (n for n in dstElmClkSlot if n not in removed)

        for w in selectedForRewrite:
            w: HlsNetNodeWriteAnyChannel
            if w is w0:
                continue  # this write is not removed but all other writes are merged into this
            lcg = w._loopChannelGroup
            if lcg is None:
                continue
            lcg: LoopChanelGroup
            assert lcg.getChannelWhichIsUsedToImplementControl() is not w, w
            lcg.members.remove(w)

    @staticmethod
    def _assertIsConcat(n: HlsNetNode):
        assert isinstance(n, HlsNetNodeOperator) and n.operator == HwtOps.CONCAT, n
        return True

    def _mergeChannels(self, selectedForRewrite: List[Union[HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge]],
                       dbgTracer: DebugTracer,
                       srcElm: ArchElement, srcClkI: int,
                       dstElm: ArchElement, dstClkI: int,
                       removed: Set[HlsNetNode]):
        """
        Merge several channels represented by HlsNetNodeRead-HlsNetNodeWrite pair to a single one of wider width.
        :attention: The channels must have same control flags and must be from same clock period slot in same ArchElement.
        """
        w0 = None
        for w in selectedForRewrite:
            if w._loopChannelGroup is not None and w._loopChannelGroup.getChannelWhichIsUsedToImplementControl() is w:
                w0 = w
                break
        if w0 is None:
            w0 = selectedForRewrite[0]

        for io in selectedForRewrite:
            assert io.__class__ is w0.__class__, ("Merge of channels of different classes may have unintended consequences", io, w0)

        dbgTracer.log(("merging ", selectedForRewrite), lambda x: f"{x[0]}, {[(io._id, io.associatedRead._id) for io in x[1]]}")
        wValues = [n.dependsOn[0] for n in selectedForRewrite if not HdlType_isVoid(n.dependsOn[0]._dtype)]
        builder: HlsNetlistBuilder = w0.netlist.builder.scoped(srcElm)
        firstDep: HlsNetNodeOut = selectedForRewrite[0].dependsOn[0]

        if wValues:
            newWVal = builder.buildConcat(*wValues)
            # Run scheduling on Concat (HlsNetNodeOperator) nodes which were just generated.
            newlyScheduledNodes = asapSchedulePartlyScheduled(newWVal, self._assertIsConcat)
        else:
            newWVal = builder.buildConstPy(firstDep._dtype, None)
            newWVal.obj.resolveRealization()
            t = firstDep.obj.scheduledOut[firstDep.out_i]
            newWVal.obj.scheduledZero = t
            newWVal.obj.scheduledOut = (t,)
            newlyScheduledNodes = [newWVal.obj, ]

        clkPeriod = w0.netlist.normalizedClkPeriod
        for n in newlyScheduledNodes:
            clkI = indexOfClkPeriod(n.scheduledZero, clkPeriod)
            assert clkI <= srcClkI, (clkI, srcClkI, [io._id for io in selectedForRewrite])
            srcElm.getStageForClock(clkI).append(n)

        for n in selectedForRewrite:
            if n is w0:
                continue
            for n0 in (n, n.associatedRead):
                for i in (n0._inputOfCluster, n0._outputOfCluster):
                    if i is None:
                        continue
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
        newDataWidth = sum(wv._dtype.bit_length() for wv in wValues)
        if newDataWidth > 0:
            newT = HBits(newDataWidth)
        else:
            newT = firstDep._dtype

        r0Users = tuple(r0.usedBy[0])
        r0O0 = r0._outputs[0]
        r0O0OrigT = r0O0._dtype
        for u in r0Users:
            unlink_hls_nodes(r0O0, u)

        self._changeDataTypeOfChannel(r0, w0, newT, newBuffName)

        w0.channelInitValues = newInit
        curTime = w0.scheduledOut[0]
        timeAdded = newWVal.obj.scheduledOut[newWVal.out_i] - curTime
        link_hls_nodes(newWVal, w0._inputs[0])
        if timeAdded > 0:
            assert curTime // clkPeriod == (curTime + timeAdded) // clkPeriod, ("Merging of the channels is not supposed to move write to other cycle", w0, curTime, timeAdded, clkPeriod)
            w0.moveSchedulingTime(timeAdded)

        self._removeIoNodesAfterTheyWereMergedToFirstOne(r0, w0, r0O0OrigT, r0Users, selectedForRewrite,
                                                         srcElm, srcClkI, dstElm, dstClkI, removed)

    def _detectChannes(self, archELements: List[ArchElement]):
        """
        Find all HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge, HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge
        and associate them to clock period index and ArchElement where it is connected.
        """
        channelToLocation: Dict[AnyChannelIo, Tuple[ArchElement, int, List[HlsNetNode]]] = {}
        channels: Dict[Tuple[ArchElement, int, ArchElement, int], List[AnyChannelIo]] = {}
        allWrites: List[HlsNetNodeWrite] = []
        for elm in archELements:
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
    
    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        channels = self._detectChannes(netlist.nodes)
        reachDb: HlsNetlistAnalysisPassReachability = None
        elmIndex = {elm: i for i, elm in enumerate(netlist.nodes)}
        removed: Set[HlsNetNode] = netlist.builder._removedNodes
        MergeCandidateList = Union[List[HlsNetNodeWriteBackedge], List[HlsNetNodeWriteForwardedge]]
        dbgTracer = self._dbgTracer
        with dbgTracer.scoped(self.__class__, None):
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
                            assert isinstance(io0, HlsNetNodeWriteBackedge), (io0, "Must be HlsNetNodeWriteForwardedge or HlsNetNodeWriteBackedge")

                        for io1 in islice(ioList, i + 1, None):
                            io0r = io0.associatedRead
                            io1r = io1.associatedRead
                            if io1 in removed:
                                continue

                            elif isForwrard and not isinstance(io1, HlsNetNodeWriteForwardedge):
                                continue
                            elif not isForwrard and not isinstance(io1, HlsNetNodeWriteBackedge):
                                continue

                            elif io0._loopChannelGroup is io1._loopChannelGroup and \
                                    io0.allocationType == io1.allocationType and \
                                    len(io0.channelInitValues) == len(io1.channelInitValues) and \
                                    hasInputSameDriver(io0.extraCond, io1.extraCond) and\
                                    hasInputSameDriver(io0.skipWhen, io1.skipWhen) and \
                                    hasInputSameDriver(io0r.extraCond, io1r.extraCond) and\
                                    hasInputSameDriver(io0r.skipWhen, io1r.skipWhen):
                                ioWithSameSyncFlags.append(io1)

                        if len(ioWithSameSyncFlags) > 1:
                            # dbgTracer.log(("found potentially mergable ports", ioWithSameSyncFlags), lambda x: f"{x[0]} {[n._id for n in x[1]]}")
                            if reachDb is None:
                                # lazy load reachDb from performance reasons
                                reachDb = netlist.getAnalysis(HlsNetlistAnalysisPassReachability)

                            # discard those which data inputs are driven from io0
                            selectedForRewrite: MergeCandidateList = [io0]
                            for io1 in ioWithSameSyncFlags:
                                compatible = True
                                for _io0 in selectedForRewrite:
                                    if reachDb.doesReachToData(_io0, io1.dependsOn[0]):
                                        compatible = False
                                        break
                                    if reachDb.doesReachToData(io1, _io0.dependsOn[0]):
                                        compatible = False
                                        break
                                    
                                    if isForwrard:
                                        if _io0.scheduledZero > io1.associatedRead.scheduledZero:
                                            # can not move read before write
                                            compatible = False
                                            break
                                        if io1.scheduledZero > _io0.associatedRead.scheduledZero:
                                            # can not move write after read
                                            compatible = False
                                            break
                                if compatible:
                                    selectedForRewrite.append(io1)

                            if len(selectedForRewrite) > 1:
                                self._mergeChannels(selectedForRewrite, dbgTracer,
                                                    srcElm, srcClkI, dstElm, dstClkI, removed)

            netlist.filterNodesUsingSet(removed)
