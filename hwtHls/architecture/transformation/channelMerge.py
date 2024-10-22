from collections import OrderedDict
from itertools import islice
import re
from typing import List, Union, Dict, Tuple, Optional

from hwt.code import Concat
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIORdVldSync
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.architecture.transformation.simplify import ArchElementValuePropagation
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilityDataOnlySingleClock
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel, LoopChanelGroup
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, \
    unlink_hls_node_input_if_exists, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.scheduler.scheduler import asapSchedulePartlyScheduled
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtils import hasInputSameDriverOrAndOfIt, \
    addAllUsersToWorklist, addAllDepsToWorklist
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


AnyChannelIo = Union[HlsNetNodeRead, HlsNetNodeWrite]


def archElmEdgeSortKey(archElmChannelKeyValue: Tuple[Tuple[ArchElement, int, ArchElement, int], List[AnyChannelIo]], elmIndex: Dict[ArchElement, int]) -> Tuple[int, int, int, int]:
    ((srcElm, srcClkI, dstElm, dstClkI), _) = archElmChannelKeyValue
    return (elmIndex[srcElm], srcClkI, elmIndex[dstElm], dstClkI)


def controlChannelsFirstSortKey(w: HlsNetNodeWrite):
    lcg: LoopChanelGroup = w._loopChannelGroup
    isControl = lcg is not None and lcg.getChannelUsedAsControl() is w
    return int(not isControl)


RE_MATCH_REG_TO_BB = re.compile(r"^bb(\d+)_to_bb(\d+)(_r\d+)((_src)|(_in)|(_out)|(_dst))?$")
RE_MATCH_REG = re.compile(r"^_r(\d+)$")


class RtlArchPassChannelMerge(HlsArchPass):
    """
    Merge forward and backward channels if they are between the same source and destination (ArchElement, clockIndex)
    and do have same skipWhen and extraCond conditions.

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

    def _resolveMergedChannelInitValuesOfWrites(self, writes: List[HlsNetNodeWrite]):
        """
        Resolve concatenation of channel init values from write nodes.

        :note: the values will be concatenated in lsb first manner.
        :note: init value is expected to be in format ((,), ...) or ((v0,), ...) where v0 is int or BitsVal
        """
        curWidth = writes[0].associatedRead._portDataOut._dtype.bit_length()
        init = list(writes[0].associatedRead.channelInitValues)
        for w in islice(writes, 1, None):
            width = w.associatedRead._portDataOut._dtype.bit_length()
            if width != 0:
                assert len(init) == len(w.associatedRead.channelInitValues)
                for i, (cur, new) in enumerate(zip(init, w.associatedRead.channelInitValues)):
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

        r0._portDataOut._dtype = newT

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

    @staticmethod
    def _assertNodeIsDisconnected(n: HlsNetNode):
        for dep, i in zip(n.dependsOn, n._inputs):
            assert dep is None, ("Expected disconnected input", i, dep)
        for uses, o in zip(n.usedBy, n._outputs):
            assert not uses, ("Expected unused output", o, uses)

    @staticmethod
    def _optionallyScheduleSliceNodes(newV: HlsNetNodeOut, elm: ArchElement):
        sliceNode: HlsNetNode = newV.obj
        if sliceNode.scheduledZero is None:
            subscript: HlsNetNode = sliceNode.dependsOn[1].obj
            subscriptIsNewNode = subscript.scheduledZero is None
            sliceNode.scheduleAsap(None, 0, None)
            _clkI = indexOfClkPeriod(sliceNode.scheduledZero, sliceNode.netlist.normalizedClkPeriod)
            elm.getStageForClock(_clkI).append(sliceNode)
            if subscriptIsNewNode:
                subscript._setScheduleZeroTimeSingleClock(sliceNode.scheduledZero - 1)
                elm.getStageForClock(_clkI).append(subscript)

    def _removeIoNodesAfterTheyWereMergedToFirstOne(self, r0: HlsNetNodeReadAnyChannel,
                                                    w0: HlsNetNodeWriteAnyChannel,
                                                    r0O0OrigT: HdlType, r0Users: Tuple[HlsNetNodeIn, ...],
                                                    selectedForRewrite: List[HlsNetNodeWriteAnyChannel],
                                                    srcElm: ArchElement, srcClkI: int,
                                                    dstElm: ArchElement, dstClkI: int,
                                                    worklist: SetList[HlsNetNode]):
        """
        Re-wire selectedForRewrite node ports to r0, w0
        
        :param r0: a read node which replaces all selectedForRewrite read nodes
        :param w0: a write node which replaces all selectedForRewrite write nodes
        :param selectedForRewrite: group of nodes which were merged together
        """
        if r0 in srcElm.subNodes:
            elmWhereR0Is = srcElm
        else:
            assert r0 in dstElm.subNodes, r0
            elmWhereR0Is = dstElm
        builder: HlsNetlistBuilder = elmWhereR0Is.builder

        r0O0 = r0._portDataOut
        offset = 0
        assert selectedForRewrite[0] is w0, ("This is required because when replacing read data we first need to"
                                             " update use of original r0 data, before adding slices for other read nodes"
                                             )
        for w in selectedForRewrite:
            w: HlsNetNodeWrite
            r: HlsNetNodeRead = w.associatedRead
            rO0 = r._portDataOut
            if r is r0:
                rUsers = r0Users
                rO0T = r0O0OrigT
            else:
                rUsers = r.usedBy[rO0.out_i]
                rO0T = rO0._dtype

            if rUsers:
                worklist.extend((u.obj for u in rUsers))
                # slice out data value from merged replacement value
                newV = builder.buildIndexConstSlice(rO0T, r0O0, offset + rO0T.bit_length(), offset, [])
                self._optionallyScheduleSliceNodes(newV, elmWhereR0Is)
                if r is r0:
                    # :note: uses were previously disconnected because port type changed
                    for u in tuple(rUsers):
                        newV.connectHlsIn(u)
                else:
                    builder.replaceOutput(rO0, newV, True)

            if r is not r0:
                # disconnect ports of r, w nodes
                addAllDepsToWorklist(worklist, w)
                addAllUsersToWorklist(worklist, w)
                w._portSrc.disconnectFromHlsOut()
                unlink_hls_node_input_if_exists(w.extraCond)
                unlink_hls_node_input_if_exists(w.skipWhen)
                if w._dataVoidOut is not None:
                    builder.replaceOutput(w._dataVoidOut, w0.getDataVoidOutPort(), True)
                if r._valid is not None:
                    builder.replaceOutput(w._ready, w0.getReady(), True)
                if r._validNB is not None:
                    builder.replaceOutput(w._readyNB, w0.getReadyNB(), True)
                self._assertNodeIsDisconnected(w)
                w.markAsRemoved()

                addAllDepsToWorklist(worklist, r)
                addAllUsersToWorklist(worklist, r)
                unlink_hls_node_input_if_exists(r.extraCond)
                unlink_hls_node_input_if_exists(r.skipWhen)
                if r._dataVoidOut is not None:
                    builder.replaceOutput(r._dataVoidOut, r0.getDataVoidOutPort(), True)
                if r._valid is not None:
                    builder.replaceOutput(r._valid, r0.getValid(), True)
                if r._validNB is not None:
                    builder.replaceOutput(r._validNB, r0.getValidNB(), True)
                self._assertNodeIsDisconnected(r)
                r.markAsRemoved()

            offset += rO0T.bit_length()

        # srcElm.filterNodesUsingRemovedSetInSingleStage(srcClkI)

        # if srcElm is not dstElm or srcClkI != dstClkI:
        #    dstElm.filterNodesUsingRemovedSetInSingleStage(dstClkI)

        for w in selectedForRewrite:
            w: HlsNetNodeWriteAnyChannel
            if w is w0:
                continue  # this write is not removed but all other writes are merged into this
            lcg = w._loopChannelGroup
            if lcg is None:
                continue
            lcg: LoopChanelGroup
            assert lcg.getChannelUsedAsControl() is not w, w
            lcg.members.remove(w)

    @staticmethod
    def _assertIsConcat(n: HlsNetNode):
        assert isinstance(n, HlsNetNodeOperator) and n.operator == HwtOps.CONCAT, n
        return True

    def _mergeChannels(self, selectedForRewrite: List[HlsNetNodeWrite],
                       dbgTracer: DebugTracer,
                       srcElm: ArchElement, srcClkI: int,
                       dstElm: ArchElement, dstClkI: int,
                       worklist: SetList[HlsNetNode]):
        """
        Merge several channels represented by HlsNetNodeRead-HlsNetNodeWrite pair to a single one of wider width.
        :attention: The channels must have same control flags and must be from same clock period slot in same ArchElement.
        """
        w0 = None
        for w in selectedForRewrite:
            if w._loopChannelGroup is not None and w._loopChannelGroup.getChannelUsedAsControl() is w:
                w0 = w
                break

        if w0 is None:
            w0 = selectedForRewrite[0]

        for io in selectedForRewrite:
            assert io.__class__ is w0.__class__, ("Merge of channels of a different class may have unintended consequences", io, w0)

        dbgTracer.log(("merging ", selectedForRewrite), lambda x: f"{x[0]}, {[(io._id, io.associatedRead._id) for io in x[1]]}")
        wValues = [n.dependsOn[0] for n in selectedForRewrite if not HdlType_isVoid(n.dependsOn[0]._dtype)]
        builder: HlsNetlistBuilder = srcElm.builder
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

        worklist.append(newWVal.obj)

        clkPeriod = w0.netlist.normalizedClkPeriod
        for n in newlyScheduledNodes:
            clkI = indexOfClkPeriod(n.scheduledZero, clkPeriod)
            assert clkI <= srcClkI, (clkI, srcClkI, [io._id for io in selectedForRewrite])
            srcElm.getStageForClock(clkI).append(n)

        for n in selectedForRewrite:
            if n is w0:
                continue
            for n0 in (n, n.associatedRead):
                netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n0, worklist)

        newBuffName = self._generatePrettyBufferName(selectedForRewrite)
        newInit = self._resolveMergedChannelInitValuesOfWrites(selectedForRewrite)  # important to do before type of w0 is altered
        r0: HlsNetNodeRead = w0.associatedRead

        worklist.append(w0.dependsOn[0].obj)
        w0._inputs[0].disconnectFromHlsOut(w0.dependsOn[0])

        newDataWidth = sum(wv._dtype.bit_length() for wv in wValues)
        if newDataWidth > 0:
            newT = HBits(newDataWidth)
        else:
            newT = firstDep._dtype

        r0Users = tuple(r0.usedBy[0])
        r0O0 = r0._portDataOut
        r0O0OrigT = r0O0._dtype
        for u in r0Users:
            uObj: HlsNetNode = u.obj
            uObj.getHlsNetlistBuilder().unregisterNode(uObj)
            u.disconnectFromHlsOut(r0O0)
            worklist.append(uObj)

        self._changeDataTypeOfChannel(r0, w0, newT, newBuffName)

        r0.channelInitValues = newInit
        curTime = w0.scheduledOut[0]
        timeAdded = newWVal.obj.scheduledOut[newWVal.out_i] - curTime
        newWVal.connectHlsIn(w0._inputs[0])
        if timeAdded > 0:
            assert curTime // clkPeriod == (curTime + timeAdded) // clkPeriod, ("Merging of the channels is not supposed to move write to other cycle", w0, curTime, timeAdded, clkPeriod)
            w0.moveSchedulingTime(timeAdded)

        self._removeIoNodesAfterTheyWereMergedToFirstOne(r0, w0, r0O0OrigT, r0Users, selectedForRewrite,
                                                         srcElm, srcClkI, dstElm, dstClkI,
                                                         worklist)

    def _detectChannes(self, archELements: List[ArchElement]):
        """
        Find all HlsNetNodeRead with associatedWrite, HlsNetNodeWrite with associatedRead
        and associate them to clock period index and ArchElement where it is connected.
        """
        channelToLocation: Dict[AnyChannelIo, Tuple[ArchElement, int, List[HlsNetNode]]] = {}
        channels: OrderedDict[Tuple[ArchElement, int, ArchElement, int], List[AnyChannelIo]] = OrderedDict()
        allWrites: List[HlsNetNodeWrite] = []
        for elm in archELements:
            elm: ArchElement
            for clkI, nodes in elm.iterStages():
                for n in nodes:
                    if isinstance(n, HlsNetNodeRead) and n.associatedWrite is not None:
                        channelToLocation[n] = (elm, clkI, nodes)
                    elif isinstance(n, HlsNetNodeWrite) and n.associatedRead is not None:
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

    @staticmethod
    def _tryToFindNotInSameTime(o: HlsNetNodeOut):
        oNode = o.obj
        vldNBTime = oNode.scheduledOut[o.out_i]
        for u in oNode.usedBy[o.out_i]:
            u: HlsNetNodeIn
            uObj = u.obj
            if isinstance(uObj, HlsNetNodeOperator) and uObj.operator == HwtOps.NOT:
                if uObj.scheduledIn[u.in_i] == vldNBTime:
                    return uObj._outputs[0]
        return None

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        channels = self._detectChannes(netlist.subNodes)
        reachDb: HlsNetlistAnalysisPassReachabilityDataOnlySingleClock = None
        elmIndex = {elm: i for i, elm in enumerate(netlist.subNodes)}
        MergeCandidateList = Union[List[HlsNetNodeWrite], List[HlsNetNodeWrite]]
        dbgTracer = self._dbgTracer
        changed = False
        worklist: SetList[HlsNetNode] = SetList()  # worklist for simplify
        modifiedElements: SetList[Union[HlsNetNodeAggregate, HlsNetlistCtx]] = SetList()
        with dbgTracer.scoped(self.__class__, None):
            for (srcElm, srcClkI, dstElm, dstClkI), ioList in sorted(
                    channels.items(),
                    key=lambda kv: archElmEdgeSortKey(kv, elmIndex)):
                srcElm: ArchElement
                if len(ioList) > 1:
                    ioList.sort(key=controlChannelsFirstSortKey)
                    for i, io0w in enumerate(ioList):
                        if io0w._isMarkedRemoved:
                            continue
                        # find io nodes which have same skipWhen and extraCond flags
                        ioWithSameSyncFlags: MergeCandidateList = []
                        isForwrard = io0w.isForwardedge()
                        if not isForwrard:
                            assert io0w.isBackedge(), (io0w, "Must be HlsNetNodeWriteForwardedge or HlsNetNodeWriteBackedge")

                        io0r = io0w.associatedRead
                        vldNB = io0r._validNB

                        vldNB_n = None
                        if vldNB is not None:
                            vldNB_n = self._tryToFindNotInSameTime(vldNB)

                        for io1w in islice(ioList, i + 1, None):
                            io1r = io1w.associatedRead
                            if io1w._isMarkedRemoved:
                                continue
                            elif isForwrard != io1w.isForwardedge():
                                continue
                            elif io0w._loopChannelGroup is not io1w._loopChannelGroup:
                                continue
                            elif io0w.allocationType != io1w.allocationType or \
                                    len(io0r.channelInitValues) != len(io1r.channelInitValues):
                                continue
                            elif io0w._loopChannelGroup is None:
                                # it is not none and it is the same we know that this channel group leads
                                # between same blocks, thus it must have same control.
                                # The control however can be obfuscated by various things so we want to
                                # skip check if possible.
                                if not hasInputSameDriverOrAndOfIt(io0w.extraCond, None, io1w.extraCond):
                                    continue
                                elif not hasInputSameDriverOrAndOfIt(io0w.skipWhen, None, io1w.skipWhen):
                                    continue
                                elif not hasInputSameDriverOrAndOfIt(io0r.extraCond, vldNB, io1r.extraCond):
                                    continue
                                elif not hasInputSameDriverOrAndOfIt(io0r.skipWhen, vldNB_n, io1r.skipWhen):
                                    continue
                            ioWithSameSyncFlags.append(io1w)

                        if ioWithSameSyncFlags:
                            # dbgTracer.log(("found potentially mergable ports", ioWithSameSyncFlags), lambda x: f"{x[0]} {[n._id for n in x[1]]}")
                            if reachDb is None:
                                # lazy load reachDb from performance reasons
                                reachDb = netlist.getAnalysis(HlsNetlistAnalysisPassReachabilityDataOnlySingleClock)

                            # discard those which data inputs are driven from io0w
                            selectedForRewrite: MergeCandidateList = [io0w]
                            for io1w in ioWithSameSyncFlags:
                                compatible = True
                                for _io0 in selectedForRewrite:
                                    if reachDb.doesReachTo(_io0, io1w.dependsOn[io1w._portSrc.in_i]):
                                        compatible = False
                                        break
                                    if reachDb.doesReachTo(io1w, _io0.dependsOn[_io0._portSrc.in_i]):
                                        compatible = False
                                        break

                                    if isForwrard:
                                        if _io0.scheduledZero > io1w.associatedRead.scheduledZero:
                                            # can not move read before write
                                            compatible = False
                                            break
                                        if io1w.scheduledZero > _io0.associatedRead.scheduledZero:
                                            # can not move write after read
                                            compatible = False
                                            break
                                if compatible:
                                    selectedForRewrite.append(io1w)

                            if len(selectedForRewrite) > 1:
                                self._mergeChannels(selectedForRewrite, dbgTracer,
                                                    srcElm, srcClkI, dstElm, dstClkI, worklist)
                                modifiedElements.append(srcElm)
                                modifiedElements.append(dstElm)

                                changed = True

        if changed:
            ArchElementValuePropagation(dbgTracer, modifiedElements, worklist, None)
            netlist.filterNodesUsingRemovedSet(recursive=True)
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
