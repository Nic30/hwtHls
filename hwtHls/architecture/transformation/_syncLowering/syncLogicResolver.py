from copy import copy
import os
from typing import List, Dict, Tuple, Union, Optional, Set

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeIoDict, ArchSyncNeighborDict
from hwtHls.architecture.analysis.handshakeSCCs import \
    ReadOrWriteType, AllIOsOfSyncNode
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.architecture.analysis.syncNodeGraph import ArchSyncNodeTy_stringFormat_short
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.transformation._syncLowering.syncLogicHlsNetlistToAbc import SyncLogicHlsNetlistToAbc
from hwtHls.architecture.transformation._syncLowering.syncLogicResolverFlushing import SyncLogicResolverFlushing
from hwtHls.architecture.transformation._syncLowering.syncLogicResolverNegationPruning import abcPruneNegatedPrimaryInputs
from hwtHls.architecture.transformation._syncLowering.syncLogicSearcher import SyncLogicSearcher
from hwtHls.architecture.transformation._syncLowering.utils import ioDataIsMixedInControlInThisClk, \
    updateAbcObjRefsForNewNet
from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Aig_t, Abc_Obj_t, Abc_NtkExpandExternalCombLoops, \
    MapAbc_Obj_tToAbc_Obj_t, MapAbc_Obj_tToSetOfAbc_Obj_t, Io_FileType_t
from hwtHls.netlist.abc.hlsNetlistToAbcAig import HlsNetlistToAbcAig
from hwtHls.netlist.abc.optScripts import abcCmd_resyn2, abcCmd_compress2
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeStageAck
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_node_input_if_exists
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


# class ChannelDeadlockError(AssertionError):
#    pass
class SyncLogicResolver(HlsNetlistToAbcAig):
    """
    This class take synchronization SCC
    as an input and builds a handshake synchronization logic in ABC,
    then removes combinational loops, then updates all synchronization flags to be remove cycles.
    
    :note: A synchronization SCC is a set of connected synchronization nodes with combination cycle in sychronization signals.

    All channel IO which are not part of SCC are treated as a regular IO
    Channel IO in SCC will have :code:`_rtlUseReady=_rtlUseValid=False` and all flags updated.

    Input flags (extraCond, skipWhen, mayFlush, forceEn) will have input drive replaced
    with an enriched variant generated from handshake cycle breaking.

    Output flags uses (write.ready, read.valid) will also be replaced with enriched variant.

    Output flags driven from internal state of the buffer (isFlushed, full) will remain
    untouched.

    Ready/valid used in internal signaling is computed as:
    .. code:: Python
        
        write.ready = read.ready | ~write.full
        write.valid = parentNode.ack & write.extraCond & ~write.skipWhen

        read.ready = parentNode.ack & read.extraCond & ~read.skipWhen
        read.valid = write.valid | (~write.empty if write.capacity > 0 else write.mayFlush)

    :note: extraCond is altered to emulate write.ready and read.valid behavior after :code:`_rtlUseReady=_rtlUseValid=False`
        which causes state of the other channel port to be ignored.
    :attention: All skipWhen are removed, and all io nodes (except for write node implementing nodes stall)
        are converted into non-blocking. This is because extra cond is already enriched with
        ack of all other related nodes. And when resolving sync we do not need ready/valid
        of this node, because it is already in extraCond of others.
    :note: When translating from HlsNetlist the clock window must be taken in account because
        same HlsNetNodeOut within different clock window is likely a different register.

    :ivar impliedValues: a dictionary mapping key Abc_Obj_t to set of Abc_Obj_t which are always 1 if key is 1
    :ivar outputsFromAbcNet: a subset of abc primary outputs which are true
        outputs of optimized network and not just some tmp output
    """

    def __init__(self, clkPeriod: SchedTime,
                 scc: SetList[ArchSyncNodeTy],
                 sccIndex: int,
                 nodeIo: ArchSyncNodeIoDict,
                 neighborDict: ArchSyncNeighborDict,
                 allSccIOs: AllIOsOfSyncNode,
                 dbgDumpAbc: bool,
                ):

        self.scc = scc
        self.sccIndex = sccIndex
        self.nodeIo = nodeIo
        self.neighborDict = neighborDict
        self.allSccIOs = allSccIOs

        self.toAbc = SyncLogicHlsNetlistToAbc(clkPeriod, f"hsscc{self.sccIndex}")
        self.syncLogicSearch = SyncLogicSearcher(clkPeriod, scc, self._onAbcAddPrimaryInput)
        self.syncLogicNodes = self.toAbc.syncLogicNodes = self.syncLogicSearch.nodes

        self.syncLogicFlushing = SyncLogicResolverFlushing()
        # :note: we can not store Abc_Obj_t because the object could be discarded after first operation with network
        #        we can not use index because IO may reorder and we can not use Id because it also changes
        self.ioMap: Dict[str, Union[HlsNetNodeStageAck, None, HlsNetNodeExplicitSync, HlsNetNodeOut]] = {}
        self.inToOutConnections = MapAbc_Obj_tToAbc_Obj_t()
        self.impliedValues = MapAbc_Obj_tToSetOfAbc_Obj_t()
        self.outputsFromAbcNet: Set[Abc_Obj_t] = set()
        self._dbgDumpAbc = dbgDumpAbc

    def _onAbcAddPrimaryInput(self, outPort: HlsNetNodeOut, syncNode: ArchSyncNodeTy, name=None):
        clkI = syncNode[1]
        key = (outPort, clkI)
        toAbc = self.toAbc
        abcI = toAbc.net.CreatePi()
        if name is None:
            name = outPort.getPrettyName(useParentName=False)
        abcI.AssignName(f"pi{abcI.Id:d}_{name}_clk{clkI:d}", "")
        self.ioMap[abcI.Name()] = outPort
        toAbc.translationCache[key] = abcI
        return abcI

    def _translateIOAckExpr(self,
                            aig: Abc_Aig_t,
                            clkI: int,
                            ioNode: Union[HlsNetNodeRead, HlsNetNodeWrite],
                            rltAck: Optional[Abc_Obj_t]):
        """
        Generate a logical expression which is 1 if IO node is able to perform its function. 
        """
        toAbc = self.toAbc
        ec = toAbc._translateDriveOfOptionalIn(aig, clkI, ioNode.extraCond)
        sw = toAbc._translateDriveOfOptionalIn(aig, clkI, ioNode.skipWhen)
        ack = aig.AndOptional(rltAck, ec)

        #   If read was blocking the parent syncNode is stalling while not full.
        #   if read was non-blocking the valid/validNB is replaced with validNB & full
        #   this expression is captured in register directly after clock window with read.

        if isinstance(ioNode, HlsNetNodeWrite) and ioNode._isFlushable:
            syncNode = ioNode.getParentSyncNode()
            isNotFlushed = self.syncLogicFlushing.getIsNotFlushedFlag(self, syncNode, ioNode)
            isFlushed = aig.Not(isNotFlushed)
            ack = aig.Or(ack, isFlushed)

        if ack is not None:
            forceEn = ioNode._forceEnPort
            if isinstance(ioNode, HlsNetNodeWrite):
                if ioNode._getBufferCapacity() > 0:
                    if ioNode._shouldUseReadValidNBInsteadOfFullPort():
                        syncNode = ioNode.associatedRead.getParentSyncNode()
                        _full = ioNode.associatedRead.getValidNB()
                    else:
                        syncNode = (ioNode.parent, clkI)
                        _full = ioNode.getFullPort()
                    if self.syncLogicSearch.primaryInputs.append((_full, syncNode)):
                        self.syncLogicSearch._onPrimaryInputFound(_full, syncNode)
                    # ready if (rtl ready and extraCond) or not full
                    full = toAbc._translate(aig, (_full, syncNode[1]))
                    ack = aig.Or(ack, aig.Not(full))

            if forceEn is not None:
                ack = aig.Or(ack, toAbc._translate(aig, (ioNode.dependsOn[forceEn.in_i], clkI)))

        if ack is not None and sw is not None:
            ack = aig.Or(ack, sw)

        return ack

    def _translateIOEnExpr(self, aig: Abc_Aig_t,
                           parentSyncNode: ArchSyncNodeTy,
                           ioNode: Union[HlsNetNodeRead, HlsNetNodeWrite],
                           andWithParentEn=True):
        """
        Generate a logical expression allows IO node to perform its function.
        """
        toAbc = self.toAbc
        clkI = parentSyncNode[1]
        en = None
        ec = ioNode.getExtraCondDriver()
        if ec is not None:
            en = toAbc._translate(aig, (ec, clkI))
            # en = aig.And(en, _ec)

        sw = ioNode.getSkipWhenDriver()
        if sw is not None:
            sw_n = aig.Not(toAbc._translate(aig, (sw, clkI)))
            en = aig.AndOptional(en, sw_n)

        # :note: this is en flag which will be expanded differently for each sync node
        #  the expansion puts en of current syncNode=1 and
        if andWithParentEn:
            parentEn = toAbc.translationCache[parentSyncNode]
            en = aig.AndOptional(en, parentEn)

        if isinstance(ioNode, HlsNetNodeWrite) and ioNode._isFlushable:
            # curMayFlush = ioNode.dependsOn[ioNode._mayFlushPort.in_i]
            # assert curMayFlush is None, "This should be generated here"
            flushing = self.syncLogicFlushing
            if andWithParentEn:
                en = aig.OrOptional(en, flushing.getMayFlushCondition(self, parentSyncNode, ioNode))
            en = aig.AndOptional(en, flushing.getIsNotFlushedFlag(self, parentSyncNode, ioNode))

        if en is not None:
            forceEn = ioNode._forceEnPort
            if forceEn is not None:
                en = aig.Or(en, toAbc._translate(aig, (ioNode.dependsOn[forceEn.in_i], clkI)))

        return en

    def _getRtlAckForReadChannel(self, aig: Abc_Aig_t, w: HlsNetNodeWrite, writeClkIndex: int, readSyncNode: ArchSyncNodeTy):
        """
        Get expression for ready of channel read
        """
        assert isinstance(w, HlsNetNodeWrite), w
        cr = w.associatedRead
        if w._isBlocking and w._rtlUseReady and (w.parent is not cr.parent or
                                                 w.parent.rtlStatesMayHappenConcurrently(writeClkIndex, readSyncNode[1])):
            # check ready only for blocking writes with ready which may happen concurrently
            return self._translateIOEnExpr(aig, readSyncNode, cr)
        else:
            return None

    def _getRtlAckForWriteChannel(self, aig: Abc_Aig_t, r: HlsNetNodeRead, readClkIndex: int, writeSyncNode: ArchSyncNodeTy):
        """
        Get expression which is 1 if channel has some data available ~empty if capacity > 0 else w.valid 
        """
        assert isinstance(r, HlsNetNodeRead), r
        storageCapacity = r.associatedWrite._getBufferCapacity()
        if r._isBlocking and r._rtlUseValid:
            if storageCapacity > 0:
                # ack if there is data in the buffer
                if r._rtlUseValid:
                    return self.toAbc._translate(aig, (r.getValidNB(), readClkIndex))
                else:
                    return None
            else:
                # ack if the write can perform its function
                w = r.associatedWrite
                wAck = self._translateIOEnExpr(aig, writeSyncNode, w)
                return wAck
        else:
            return None

    def _buildArchSyncNodeEn(self,
                             scc: SetList[ArchSyncNodeTy],
                             aig: Abc_Aig_t,
                             nodeIo: ArchSyncNodeIoDict,
                             neighborDict: ArchSyncNeighborDict,
                             syncNode: ArchSyncNodeTy):
        """
        Generate a logical expression which is 1 if sync node can be activated as a whole (all members can be activated or skipped).
        """
        toAbc = self.toAbc
        elm, clkI = syncNode
        # all inputs (ready & extraCond) | skipWhen and all outputs (valid & extraCond) | skipWhen
        if isinstance(elm, ArchElementFsm):
            con: ConnectionsOfStage = elm.connections[clkI]
            ack = toAbc._translate(aig, (con.fsmStateEnNode._outputs[0], clkI))
        else:
            # if this is a pipeline the channel from predecessor stage is not conditional and thus its
            # validity flag is automatically anded to every expression
            ack = toAbc.c1

        reads, writes = nodeIo[syncNode]
        # copy because items are potentially added in loop bellow
        reads = copy(reads)
        writes = copy(writes)

        _neighborDict = neighborDict.get(syncNode, None)
        if _neighborDict:
            for otherNode, sucChannels in _neighborDict.items():
                if otherNode in scc:
                    # otherNodeAck = toAbc._translate(aig, otherNode)
                    for c in sucChannels:
                        # build channel out valid, in ready expressions
                        # build output valid, input ready, expressions
                        if isinstance(c, HlsNetNodeRead):
                            wAck = self._getRtlAckForWriteChannel(aig, c, clkI, otherNode)
                            rAck = self._translateIOAckExpr(aig, clkI, c, wAck)
                            ack = aig.AndOptional(ack, rAck)

                        else:
                            rAck = self._getRtlAckForReadChannel(aig, c, clkI, otherNode)
                            wAck = self._translateIOAckExpr(aig, clkI, c, rAck)
                            ack = aig.AndOptional(ack, wAck)
                else:
                    # successor is not in the same HsSCC this means that
                    # the normal RTL valid/ready signaling could be used
                    for c in sucChannels:
                        if isinstance(c, HlsNetNodeRead):
                            reads.append(c)
                        else:
                            assert isinstance(c, HlsNetNodeWrite), c
                            writes.append(c)

        for r in reads:
            r: HlsNetNodeRead
            if r._rtlUseValid and r._isBlocking:
                rVld = toAbc._translate(aig, (r.getValidNB(), clkI))
            else:
                rVld = None
            rAck = self._translateIOAckExpr(aig, clkI, r, rVld)
            ack = aig.AndOptional(ack, rAck)

        for w in writes:
            if w._rtlUseReady and w._isBlocking:
                wRd = toAbc._translate(aig, (w.getReadyNB(), clkI))
            else:
                wRd = None

            wAck = self._translateIOAckExpr(aig, clkI, w, wRd)
            ack = aig.AndOptional(ack, wAck)

        return ack

    def _containsIORequiringStageAck(self, c: ArchSyncNodeTy):
        _, writes = self.nodeIo[c]
        for w in writes:
            if w._isFlushable or w._getBufferCapacity() > 0:
                return True
        neighbors = self.neighborDict.get(c, False)
        if neighbors:
            for _, channels in neighbors.items():
                for w in channels:
                    if isinstance(w, HlsNetNodeWrite) and (w._isFlushable or w._getBufferCapacity() > 0):
                        return True

        return False

    def _declareArchSyncNodeEnInABC(self, scc: SetList[ArchSyncNodeTy]) -> List[Abc_Obj_t]:
        """
        :param ioInputFlags: input ports of IO nodes which are for flags used in sync logic
        :param ioOutputFlagsToRewriteLater: tuples (HlsNetlistOut, clock index, ABC primary input) of outputs
            in netlist which may be used internally in sync logic and may be output of sync logic
            (if used by something else than nodes of sync logic, which we do not know yet)
        """
        toAbc = self.toAbc
        net = toAbc.net
        ioMap = self.ioMap
        outputsFromAbcNet = self.outputsFromAbcNet
        # forward declaration of all ArchSyncNode flags
        syncNodeEn: List[Abc_Obj_t] = []
        for c in scc:
            c: ArchSyncNodeTy
            elm, clkI = c
            elm: ArchElement
            clkI: int
            abcI = net.CreatePi()
            abcO = net.CreatePo()
            syncNodeEn.append(abcO)
            name = f"hsSccEn_{ArchSyncNodeTy_stringFormat_short(c)}"
            abcI.AssignName(f"pi{abcI.Id:d}_{name:s}", "")
            abcO.AssignName(f"po{abcO.Id:d}_{name:s}", "")

            toAbc.translationCache[c] = abcI
            self.inToOutConnections[abcI] = abcO
            if isinstance(elm, ArchElementPipeline) and elm.isLastStage(clkI) and not self._containsIORequiringStageAck(c):
                # this is just tmp variable
                # for last pipeline stage there are no register which would require this
                ioMap[abcO.Name()] = None
            else:
                stAck, _ = elm.getStageAckNode(clkI)

                ioMap[abcO.Name()] = stAck
                outputsFromAbcNet.add(abcO)

        return syncNodeEn

    def _buildReadyValidExprForLocalChannels(self,
            readyValidComputedBySyncLogic: List[Tuple[HlsNetNodeOut, int]],
            ):
        toAbc = self.toAbc
        ioMap = self.ioMap
        net = toAbc.net
        aig: Abc_Aig_t = net.pManFunc
        primaryOutputs = self.syncLogicSearch.primaryOutputs
        outputsFromAbcNet = self.outputsFromAbcNet

        # build expression for ready/valid of channels
        for (o, clkI) in readyValidComputedBySyncLogic:
            o: HlsNetNodeOut
            # :note: flushing logic is handled by _translateIOEnExpr
            n = o.obj
            if isinstance(n, HlsNetNodeRead):
                # build expr for vld
                assert o == n._validNB, o
                r: HlsNetNodeRead = n
                w: HlsNetNodeWrite = r.associatedWrite
                assert w is not None, ("This was supposed to be local channel", r)
                if w._getBufferCapacity() > 0:
                    # Capacity must be 0, otherwise valid is not causing handshake loop because "valid" comes from register
                    continue

                wSyncNode = w.getParentSyncNode()
                # write.valid = parentNode.ack & write.extraCond & ~write.skipWhen
                # read.valid = write.valid | (~write.empty if write.capacity > 0 else write.mayFlush)
                v = self._translateIOEnExpr(aig, wSyncNode, w)

                rSyncNode = n.getParentSyncNode()
                enIsPo = False
                for vld in (n._valid, n._validNB):
                    if vld is not None:
                        if (vld, rSyncNode) in primaryOutputs:
                            enIsPo = True
                            break

            elif isinstance(n, HlsNetNodeWrite):
                assert isinstance(n, HlsNetNodeWrite), n
                assert o == n._readyNB
                w: HlsNetNodeWrite = n
                r: HlsNetNodeRead = w.associatedRead
                rSyncNode = r.getParentSyncNode()
                # rClkI: int = rSyncNode[1]
                # write.ready = read.ready | ~write.full
                # read.ready = parentNode.ack & read.extraCond & ~read.skipWhen

                rReady = self._translateIOEnExpr(aig, rSyncNode, r)
                if w._getBufferCapacity() > 0:
                    if w._shouldUseReadValidNBInsteadOfFullPort():
                        full = (r.getValidNB(), rSyncNode[1])
                    else:
                        full = (w.getFullPort(), clkI)

                    rReady = aig.Or(rReady, aig.Not(toAbc._translate(aig, full)))
                v = rReady

                wSyncNode = n.getParentSyncNode()
                enIsPo = False
                for rd in (n._ready, n._readyNB):
                    if rd is not None:
                        if (rd, wSyncNode) in primaryOutputs:
                            enIsPo = True
                            break

            else:
                raise ValueError("Unexpected type of node", o.obj)

            # :note: this is tmp primary output
            # we use it for construction of tmp expression which will hold
            # current expression for condition and then we use it during
            # expansion of expressions during combination loop solving
            abcO = net.CreatePo()
            name = o.getPrettyName(useParentName=False)
            abcO.AssignName(f"po{abcO.Id:d}_{name}", "")
            abcO.AddFanin(v)
            if enIsPo:
                ioMap[abcO.Name()] = o
                outputsFromAbcNet.add(abcO)
            else:
                ioMap[abcO.Name()] = None  # because this is tmp variable and it will not be used after opt.

            abcI = toAbc.translationCache[(o, clkI)]
            self.inToOutConnections[abcI] = abcO

    def _buildEnableForEveryIO_requiresEn(self,
            scc: SetList[ArchSyncNodeTy],
            ioNode: HlsNetNodeExplicitSync,
            ioTy: ReadOrWriteType,
            ) -> bool:
        """
        :returns: True if node requires enable because it is required
            for control of connected buffer or other thing connected on other side of IO
        """
        if ioTy.isChannel():
            if ioTy.isRead():
                r: HlsNetNodeRead = ioNode
                w: HlsNetNodeWrite = ioNode.associatedWrite
                assert w.getParentSyncNode() in scc, (
                    r, "other channel port must be in the same HsSCC otherwise this should not be marked as channel")
                if r.hasAnyUsedValidPort():
                    return True  # because valid ports need to be rewritten

            else:
                w: HlsNetNodeWrite = ioNode
                r: HlsNetNodeRead = ioNode.associatedRead
                assert r.getParentSyncNode() in scc, (
                    ioNode, "other channel port must be in the same HsSCC otherwise this should not be marked as channel")
                if w.hasAnyUsedReadyPort():
                    return True  # because ready ports need to be rewritten

            if w._getBufferCapacity() == 0:
                if not not r.hasAnyUsedValidPort():
                    # buffer logic has no state and it will be completely inlined into HsSCC logic
                    return False
                vldHasUseOutsideOfSyncLogic = False
                clkPeriod = self.toAbc.clkPeriod

                for vld in (r._valid, r._validNB):
                    if vld is not None:
                        for u in r.usedBy[vld.out_i]:
                            uObj = u.obj
                            useClkI = uObj.scheduledIn[u.in_i] // clkPeriod
                            if (uObj, useClkI) in self.syncLogicNodes:
                                continue
                            elif isinstance(uObj, HlsNetNodeRead):
                                if u in (uObj.extraCond, uObj.skipWhen, uObj._forceEnPort):
                                    continue
                            elif isinstance(uObj, HlsNetNodeWrite):
                                if u in (uObj.extraCond, uObj.skipWhen, uObj._forceEnPort, uObj._mayFlushPort):
                                    continue
                            vldHasUseOutsideOfSyncLogic = True
                            break

                if not vldHasUseOutsideOfSyncLogic:
                    # buffer logic has no state and it will be completely inlined into HsSCC logic
                    return False
            # else the buffer have state and we need this to control how data is pushed and popped to/from storage
        return True

    def _buildEnableForEveryIO(self, scc: SetList[ArchSyncNodeTy],
                               allSccIOs: AllIOsOfSyncNode):
        """
        Call _translateIOEnExpr, declare en in ABC and fill impliedValues, ioMap, outputsFromAbcNet
        """
        net = self.toAbc.net
        aig: Abc_Aig_t = net.pManFunc
        ioMap = self.ioMap
        outputsFromAbcNet = self.outputsFromAbcNet
        impliedValues = self.impliedValues
        toAbc = self.toAbc

        for (_, ioNode, syncNode, ioTy) in allSccIOs:
            ioNode: HlsNetNodeExplicitSync
            syncNode: ArchSyncNodeTy
            ioTy: ReadOrWriteType
            if not self._buildEnableForEveryIO_requiresEn(scc, ioNode, ioTy):
                continue
            
            # build en for io node
            en = self._translateIOEnExpr(aig, syncNode, ioNode)
            abcO: Abc_Obj_t = net.CreatePo()
            abcO.AssignName(f"po{abcO.Id:d}_n{ioNode._id}_en", "")
            abcO.AddFanin(en)

            # if this is external IO cancel ready-valid loop on this node
            # :note: loop is there because HsScc ack is build also from ready/valid of this node
            #    and and after expansion every external node would check also its own ack
            if not ioTy.isChannel():
                if ioTy.isRead():
                    rtlAck = ioNode._validNB
                else:
                    rtlAck = ioNode._readyNB

                if rtlAck is not None and not ioDataIsMixedInControlInThisClk(ioNode, rtlAck):
                    clkI = syncNode[1]
                    _rtlAck = toAbc._translate(aig, (rtlAck, clkI))
                    impliedValues[abcO] = {_rtlAck}

            if ioTy.isChannel():
                if ioTy.isRead():
                    r = ioNode
                    w = ioNode.associatedWrite
                    ioNodeItsefRequiresEnable = r.hasAnyUsedValidPort()
                    # enable required for rewrite of uses of valid/validNB of this node
                    # enable required because other side of channel uses rtl valid signal
                else:
                    w = ioNode
                    ioNodeItsefRequiresEnable = w.hasAnyUsedReadyPort()
                    # enable required for rewrite of uses of ready/readyNB of this node
                    # enable required because other side of channel uses rtl valid signal

                ioNodeItsefRequiresEnable = (
                    ioNodeItsefRequiresEnable or
                    w._getBufferCapacity() != 0 or
                    (ioNode.getParentSyncNode() not in scc
                     and (ioNode._rtlUseReady if ioTy.isRead() else ioNode._rtlUseValid))
                )
            elif ioTy.isRead():
                ioNodeItsefRequiresEnable = ioNode._rtlUseReady
            else:
                ioNodeItsefRequiresEnable = ioNode._rtlUseValid

            if ioNodeItsefRequiresEnable:
                ioMap[abcO.Name()] = ioNode
                outputsFromAbcNet.add(abcO)
            else:
                if ioNode.extraCond is not None:
                    unlink_hls_node_input_if_exists(ioNode.extraCond)
                    ioNode._removeInput(ioNode.extraCond.in_i)
                ioMap[abcO.Name()] = None
    
    def translateToAbc(self):
        """
        Translate HsSCC handshake logic to ABC AIG
        Handshake logic is composed of:
        * io flags (extraCond, skipWhen, mayFlush, isFlushed, ready, readyNB, valid, validNB, full)
            * including any logic connecting them together
        * enable for each stage of pipeline/state of FSM
        """
        toAbc = self.toAbc
        net = toAbc.net
        toAbc.abcFrame.SetCurrentNetwork(net)
        aig: Abc_Aig_t = net.pManFunc
        scc = self.scc
        syncLogicSearch = self.syncLogicSearch

        readyValidComputedBySyncLogic = syncLogicSearch.collectFlagDefsFromIONodes(self.allSccIOs)
        syncLogicSearch.collectFromSCCEnable(scc)
        syncLogicSearch.collectFromFsmStateNextWrite(scc)
    
        self.syncLogicFlushing.abcDeclareInputsForFlushTokens(self)
        # :note: now all primary inputs from io nodes should be declared
        abcPruneNegatedPrimaryInputs(toAbc, syncLogicSearch)

        syncNodeEn = self._declareArchSyncNodeEnInABC(scc)
        # :note: now all primary inputs should be declared

        self.syncLogicFlushing.constructFlushTokenAcquireFlags(self, aig)
        self._buildReadyValidExprForLocalChannels(
            readyValidComputedBySyncLogic,
        )

        self._buildEnableForEveryIO(scc, self.allSccIOs)

        # build ArchSyncNode enable expressions
        for abcO, syncNode in zip(syncNodeEn, scc):
            ack = self._buildArchSyncNodeEn(scc, aig, self.nodeIo, self.neighborDict, syncNode)
            abcO.AddFanin(ack)

        syncLogicSearch.pruneAggegatePortsInSyncNodes()
        aig.Cleanup()  # removes dangling nodes
        net.Check()
        # net.Io_Write("abc-directly.0.dot", Io_FileType_t.IO_FILE_DOT)

    def abcOptScript(self, net: Abc_Ntk_t, optLevel:int):
        for _ in range(optLevel):
            net = abcCmd_resyn2(net)
            net = abcCmd_compress2(net)
            net.pManFunc.Cleanup()  # removes dangling nodes
        return net

    def expandSyncExprToRmCombinationalLoops(self):
        # for each term completely expand all non primary inputs of handshake logic
        net = self.toAbc.net
        netlist = self.scc[0][0].netlist
        if self._dbgDumpAbc:
            dumpFileNamePrefix = os.path.join("tmp", netlist.label, f"SyncLowering.{self.sccIndex:d}.")
            net.Io_Write(dumpFileNamePrefix + "1.abc-init.dot", Io_FileType_t.IO_FILE_DOT)
            net.Io_Write(dumpFileNamePrefix + "1.abc-init.v", Io_FileType_t.IO_FILE_VERILOG)

        net.Check()
        net = self.abcOptScript(net, 2)

        if self._dbgDumpAbc:
            net.Io_Write(dumpFileNamePrefix + "2.abc-initOpt.dot", Io_FileType_t.IO_FILE_DOT)
            net.Io_Write(dumpFileNamePrefix + "2.abc-initOpt.v", Io_FileType_t.IO_FILE_VERILOG)

        impliedValues, inToOutConnections, outputsFromAbcNet = updateAbcObjRefsForNewNet(
            self.impliedValues, self.inToOutConnections, self.outputsFromAbcNet, net)
        Abc_NtkExpandExternalCombLoops(net, net.pManFunc, impliedValues, inToOutConnections, outputsFromAbcNet)
        net.pManFunc.Cleanup()  # removes dangling nodes
        net.Check()
        if self._dbgDumpAbc:
            net.Io_Write(dumpFileNamePrefix + "3.abc-afterExpand.dot", Io_FileType_t.IO_FILE_DOT)
            net.Io_Write(dumpFileNamePrefix + "3.abc-afterExpand.v", Io_FileType_t.IO_FILE_VERILOG)

        net = self.abcOptScript(net, 3)

        self.toAbc.net = net
        if self._dbgDumpAbc:
            net.Io_Write(dumpFileNamePrefix + "4.abc-afterOpt.dot", Io_FileType_t.IO_FILE_DOT)
            net.Io_Write(dumpFileNamePrefix + "4.abc-afterOpt.v", Io_FileType_t.IO_FILE_VERILOG)

