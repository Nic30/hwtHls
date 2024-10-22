from typing import Dict, Tuple, Union, Literal

from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.handshakeSCCs import \
    ReadOrWriteType, AllIOsOfSyncNode
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.architecture.transformation._syncLowering.syncLogicExtractor import SyncLogicExtractor, \
    HlsNetOutToAbcOutMap_t
from hwtHls.architecture.transformation._syncLowering.syncLogicResolverFlushing import FLAG_FLUSH_TOKEN_ACQUIRE
from hwtHls.architecture.transformation._syncLowering.syncLogicSearcher import SyncLogicSearcher
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.architecture.transformation.utils.syncUtils import createBackedgeInClkWindow
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx
from hwtHls.netlist.abc.abcAigToHlsNetlist import AbcAigToHlsNetlist
from hwtHls.netlist.abc.abcCpp import Abc_Frame_t, Abc_Ntk_t, \
    Abc_Aig_t, Abc_Obj_t
from hwtHls.netlist.analysis.consistencyCheck import HlsNetlistPassConsistencyCheck
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeStageAck
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, \
    unlink_hls_node_input_if_exists
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifyUtils import getConstOfOutput
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistAnalysisPassDumpNodesDot
from hwtHls.platform.fileUtils import outputFileGetter


# class ChannelDeadlockError(Exception):
#    "Channel is proven to be always deadlocked"
class SyncLogicAbcToHlsNetlist():
    """
    This class is responsible for extraction of nodes used in sync logic to own element
    and for updating them from optimized in ABC 
    
    :ivar _writeFlushTokens: a register holding a token for each flushable write.
        :see: :meth:`SyncLogicResolverFlushing.constructFlushTokenAcquireReleaseFlags`
    """

    def __init__(self,
                 scc: SetList[ArchSyncNodeTy],
                 sccIndex: int,
                 allSccIOs: AllIOsOfSyncNode,
                 clkPeriod: SchedTime,
                 syncLogicSearch: SyncLogicSearcher,
                 toAbcTranslationCache: Dict[Tuple[HlsNetNodeOut, int], Abc_Obj_t],
                 ioMap: Dict[str, Union[HlsNetNodeStageAck, None, HlsNetNodeExplicitSync, HlsNetNodeOut]],
                 abcFrame: Abc_Frame_t,
                 net: Abc_Ntk_t,
                 dbgDumpNodes: bool,
                 dbgAllowDisconnectedInputs: bool,
                 # dbgDetectDeadlockedChannels: bool,
                 ):
        self.scc = scc
        self.sccIndex = sccIndex
        self.allSccIOs = allSccIOs
        self.clkPeriod = clkPeriod
        self.toAbcTranslationCache = toAbcTranslationCache
        self.syncLogicSearch = syncLogicSearch
        self.syncLogicNodes = syncLogicSearch.nodes
        self.ioMap = ioMap

        self.abcFrame = abcFrame
        self.net = net
        self.aig: Abc_Aig_t = net.pManFunc
        self.c1 = net.Const1()

        self._dbgDumpNodes = dbgDumpNodes
        self._dbgAllowDisconnectedInputs = dbgAllowDisconnectedInputs
        # self._dbgDetectDeadlockedChannels = dbgDetectDeadlockedChannels

    @staticmethod
    def _removeIoInputSyncFlags(allSccIOs: AllIOsOfSyncNode):
        """
        Remove all io input flags because they will be replaced with enable flag (extraCond) later and
        now it would generate useless arch element ports.
        """
        for (_, ioNode, _, ioTy) in allSccIOs:
            ioNode: HlsNetNodeExplicitSync
            ioTy: ReadOrWriteType
            ec = ioNode.extraCond
            portsToDiscard = (ioNode.skipWhen, ioNode._forceEnPort)

            unlink_hls_node_input_if_exists(ec)  # extraCond flag will be generated a new
            if ec is not None and ioTy.isChannel():
                if ioNode.getAssociatedWrite()._getBufferCapacity() == 0:
                    # this will be completely inlined
                    ioNode._removeInput(ec.in_i)

            for inPort in reversed(portsToDiscard):  # reverse to make remove from list more efficient
                if inPort is not None:
                    unlink_hls_node_input_if_exists(inPort)
                    ioNode._removeInput(inPort.in_i)

    @staticmethod
    def _scheduleDefault(syncNode: ArchSyncNodeTy, out: HlsNetNodeOut) -> SchedTime:
        return scheduleUnscheduledControlLogic(syncNode, out)

    def translateFromAbcToHlsNetlistWriteFlushTokenAcquire(self, writeFlushTokens: Dict[HlsNetNodeWrite, HlsNetNodeWriteBackedge],
                                                           termPropagationCtx: ArchElementTermPropagationCtx,
                                                           ioObj: Tuple[HlsNetNodeWriteBackedge, Literal[FLAG_FLUSH_TOKEN_ACQUIRE]],
                                                           driver: HlsNetNodeOut):
        """
        Translate an expression which activates flush token acquire from ABC to HlsNetlist.
        Flush tokens are bits which guarding flushable write nodes. 
        """
        assert len(ioObj) == 2
        w, t = ioObj
        w: HlsNetNodeWrite
        t: Literal[FLAG_FLUSH_TOKEN_ACQUIRE]
        assert t is FLAG_FLUSH_TOKEN_ACQUIRE, t
        tokenWrite = writeFlushTokens[w]
        driverC = getConstOfOutput(driver)
        if tokenWrite is None:
            assert driverC is not None and not driverC, ("If token was resolved useless it must have been because it is never acquired", driver)
        else:
            tokenR: HlsNetNodeReadBackedge = tokenWrite.associatedRead
            assert tokenR.extraCond is None, (tokenR, "extraCond port for flush tokens reads should be created only on this place")
            # if tokenR.scheduledZero <= driver.obj.scheduledOut[driver.out_i]:
            #    raise NotImplementedError()
            assert driverC is None or driverC, ("If token is never acquired this token buffer is useless", tokenR, driverC)
            # driver is likely to be dependent on outputs of tokenR, in this case the forward declaration of RtlSignal of driver is required
            # this is achieved using this immediate backedge buffer
            parent = termPropagationCtx.parentDstElm
            tokenEnR, tokenEnW = createBackedgeInClkWindow(parent, 0, f"n{w._id}_flushToken_acquire", HVoidData)

            tokenEnW.allocationType = CHANNEL_ALLOCATION_TYPE.IMMEDIATE
            for newNode in (tokenEnR, tokenEnW):
                tokenEnR.setNonBlocking()
                tokenEnR.setRtlUseReady(False)
                parent._addNodeIntoScheduled(0, newNode, allowNewClockWindow=True)

            tokenEnW.addControlSerialExtraCond(driver, addDefaultScheduling=True, checkCycleFree=False)

            tokenR.addControlSerialExtraCond(tokenEnR.getValidNB(), addDefaultScheduling=True, checkCycleFree=False)

    def translateFromAbcToHlsNetlist_Out(self, out: HlsNetNodeOut, replacement: HlsNetNodeOut, termPropagationCtx: ArchElementTermPropagationCtx):
        node = out.obj
        dstNode = node.getParentSyncNode()
        _replacement = termPropagationCtx.propagateFromDstElm(
            dstNode, replacement, out.getPrettyName(useParentName=False), resetTimeToClkWindowBegin=True)
        builder: HlsNetlistBuilder = node.getHlsNetlistBuilder()
        builder.replaceOutput(out, _replacement, True)
        if isinstance(node, HlsNetNodeExplicitSync) and out in (node._ready, node._readyNB, node._valid, node._validNB):
            node._removeOutput(out.out_i)
        
        
    # def _proveChannelWritePossible(self, termPropagationCtx: ArchElementTermPropagationCtx, wNode: HlsNetNodeWrite, writeEn: HlsNetNodeOut):
    #    """
    #    prove that writeEn may become 1 if read.validNB=0
    #    """
    #    writeEnConst = getConstOfOutput(writeEn)
    #    if writeEnConst is not None:
    #        assert writeEnConst._is_full_valid(), wNode
    #        return bool(writeEnConst)
    #
    #    rNode = wNode.associatedRead
    #    _readValidNB = rNode.getValidNB()
    #    clkPeriod = rNode.netlist.normalizedClkPeriod
    #    rClkI = rNode.scheduledOut[_readValidNB.out_i] // clkPeriod
    #    rSyncNode = (rNode.parent, rClkI)
    #    try:
    #        readValidNB_exported = termPropagationCtx.exportedPorts[
    #            ArchSyncNodeTerm(rSyncNode, _readValidNB, "validNB")]
    #        readValidNB: HlsNetNodeOut = termPropagationCtx.importedPorts[
    #            ArchSyncNodeTerm(termPropagationCtx.parentDstNode, readValidNB_exported, "validNB")]
    #    except KeyError:
    #        # write is possible because it does not depend on read.validNB and is not 0
    #        return True
    #
    #    outputs = [writeEn]
    #    inputs = collectHlsNetlistExprTreeInputsSingleHierarchy(writeEn, readValidNB)
    #
    #    toAbcAig = HlsNetlistToAbcAig()
    #    abcAig = toAbcAig.aig
    #    toAbcAig.translationCache[readValidNB] = abcAig.Not(toAbcAig.c1)
    #    abcFrame, abcNet, abcAig, ioMap = toAbcAig.translate(inputs, outputs)
    #
    #    abcAig.Cleanup()
    #
    #    for _ in range(2):
    #        abcNet = abcCmd_resyn2(abcNet)
    #        abcNet = abcCmd_compress2(abcNet)
    #
    #    po: Abc_Obj_t = next(abcNet.IterPo())
    #    poFanIn:Abc_Obj_t = next(po.IterFanin())
    #    # writeEn is not const 0 if readValidNB=0
    #    abcNet.Io_Write("abc.tmp.dot", Io_FileType_t.IO_FILE_DOT)
    #    return not poFanIn.IsConst() or not poFanIn.IsComplement()

    def translateFromAbcToHlsNetlistIoEnable(self,
                                             ioObj: HlsNetNodeExplicitSync,
                                             driver: HlsNetNodeOut,
                                             primaryOutUpdateDict: Dict[HlsNetNodeOut, HlsNetNodeOut],
                                             termPropagationCtx: ArchElementTermPropagationCtx,
                                             dstNode: ArchSyncNodeTy):
        """
        Translate an expression which enables IO node from ABC to HlsNetlist
        """
        # update primaryOutUpdateDict with ports which were rewritten
        isRead = isinstance(ioObj, HlsNetNodeRead)
        if isRead:
            if ioObj.associatedWrite is not None:
                if ioObj.associatedWrite._getBufferCapacity() == 0:
                    ackFlags = [ioObj._valid, ioObj._validNB,
                                ioObj.associatedWrite._ready, ioObj.associatedWrite._readyNB]
                else:
                    ackFlags = [ioObj.associatedWrite._ready, ioObj.associatedWrite._readyNB]
            else:
                ackFlags = []
        else:
            r = ioObj.associatedRead
            if r is not None and ioObj._getBufferCapacity() == 0:
                ackFlags = [ioObj._ready, ioObj._readyNB,
                            ioObj.associatedRead._valid, ioObj.associatedRead._validNB]
            else:
                ackFlags = []

        for flag in ackFlags:
            if flag is not None:
                primaryOutUpdateDict[flag] = driver

        if isinstance(driver.obj, HlsNetNodeConst):
            v: HBitsConst = driver.obj.val
            assert v._is_full_valid(), ("en constant must be valid", ioObj)
            if bool(v):
                # always active, extraCond is useless
                if ioObj.extraCond:
                    ioObj._removeInput(ioObj.extraCond.in_i)
                return

#        if self._dbgDetectDeadlockedChannels:
#            if not isRead and\
#                ioObj.associatedRead is not None and\
#                not ioObj.associatedRead.channelInitValues:
#                # check if empty channel is written
#                # if it is never written, reader can never be executed
#                if not self._proveChannelWritePossible(termPropagationCtx, ioObj, driver):
#                    raise ChannelDeadlockError(ioObj)

        driver = termPropagationCtx.propagateFromDstElm(
            dstNode, driver, f"n{ioObj._id:d}_en", resetTimeToClkWindowBegin=True)

        if ioObj.extraCond is None:
            ioObj.addControlSerialExtraCond(driver, addDefaultScheduling=True, checkCycleFree=False)
        else:
            assert ioObj.getExtraCondDriver() is None, (
                "Should have been disconnected at the beginning of translation", ioObj)
            driver.connectHlsIn(ioObj.extraCond, checkCycleFree=False)

    def translateFromAbcToHlsNetlistStageAck(self, extractor: SyncLogicExtractor,
                                             termPropagationCtx: ArchElementTermPropagationCtx,
                                             ioObj: HlsNetNodeStageAck,
                                             driver: HlsNetNodeOut,
                                             dstNode: ArchSyncNodeTy):
        flushTokenReleases = extractor._stageAckToAllWriteFlushTokens.get(ioObj, None)
        if flushTokenReleases is not None:
            for tokenW in flushTokenReleases:
                tokenW: HlsNetNodeWriteBackedge
                # add release of flush tokens
                tokenW.addControlSerialExtraCond(driver, addDefaultScheduling=True)

        driver = termPropagationCtx.propagateFromDstElm(
            dstNode, driver, f"n{ioObj._id:d}_ackIn", resetTimeToClkWindowBegin=True)
        driver.connectHlsIn(ioObj._inputs[0], checkCycleFree=False)

    def translateFromAbcToHlsNetlist(self,
                                     parentElm: ArchElementNoImplicitSync,
                                     termPropagationCtx: ArchElementTermPropagationCtx,
                                    ):

        scc = self.scc
        allSccIOs = self.allSccIOs
        ioMap = self.ioMap
        HlsNetlistPassConsistencyCheck._checkConnections(parentElm.netlist, allowDisconnected=True)
        self._removeIoInputSyncFlags(allSccIOs)

        extractor = SyncLogicExtractor(self.syncLogicSearch,
                                       parentElm,
                                       termPropagationCtx,
                                       self.clkPeriod,
                                       self._scheduleDefault)
        hlsNetOutToAbcOut: HlsNetOutToAbcOutMap_t = {
            ioMap[po.Name()]: po
            for po in self.net.IterPo()
        }

        movedOrRemovedSyncLogicNodes = \
            extractor.extractSyncLogicNodesToNewElm(ioMap, hlsNetOutToAbcOut, self.toAbcTranslationCache)

        if movedOrRemovedSyncLogicNodes:
            for (elm, clkIndex) in scc:
                elm: ArchElement
                elm.filterNodesUsingSetInSingleStage(movedOrRemovedSyncLogicNodes, clkIndex, clearRemoved=False)

        # HlsNetlistPassConsistencyCheck._checkNodeContainers(parentElm.netlist)
        # HlsNetlistPassConsistencyCheck._checkConnections(parentElm.netlist, allowDisconnected=True)
        # for n in movedOrRemovedSyncLogicNodes:
        #    for uses in n.usedBy:
        #        for u in uses:
        #            assert u.obj.parent is parent, ("extracted node must not have use outside of new parent", u, u.obj.parent, parent)

        if self._dbgDumpNodes:
            HlsNetlistAnalysisPassDumpNodesDot(
                outputFileGetter("tmp", f"SyncLowering.{self.sccIndex:d}.5.extractBegin.dot"),
                colorOverride={n:("white", "red")
                               for (n, _) in self.syncLogicNodes}
            ).runOnHlsNetlist(parentElm.netlist)

        SyncLogicExtractor._reconstructNetlistBuilderOperatorCache(parentElm)

        # drop current schedule
        for (n, _) in self.syncLogicNodes:
            if not isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)):
                n.resetScheduling()
        if self._dbgDumpNodes:
            HlsNetlistAnalysisPassDumpNodesDot(outputFileGetter("tmp", f"SyncLowering.{self.sccIndex:d}.6.extract.dot")).runOnHlsNetlist(parentElm.netlist)

        # :attention: abc pointers and ids are likely to be changed, only reliable thing is the name of object
        # translate sync logic from ABC to HlsNetlist
        toHls = AbcAigToHlsNetlist(self.abcFrame, self.net, self.aig, ioMap, parentElm.builder)

        for ioObj, driver in toHls.translate():
            # :note: ioObj is thing stored in ioMap
            self._scheduleDefault((parentElm, 0), driver)
            if ioObj is None:
                continue  # just tmp variable

            elif isinstance(ioObj, tuple):
                self.translateFromAbcToHlsNetlistWriteFlushTokenAcquire(
                    extractor._writeFlushTokens, termPropagationCtx, ioObj, driver)
                continue
            elif isinstance(ioObj, HlsNetNodeOut):
                self.translateFromAbcToHlsNetlist_Out(ioObj, driver, termPropagationCtx)
                continue

            dstNode = ioObj.getParentSyncNode()
            if isinstance(ioObj, HlsNetNodeExplicitSync):
                self.translateFromAbcToHlsNetlistIoEnable(
                    ioObj, driver, extractor._primaryOutUpdateDict, termPropagationCtx, dstNode)

            elif isinstance(ioObj, HlsNetNodeStageAck):
                self.translateFromAbcToHlsNetlistStageAck(
                    extractor, termPropagationCtx, ioObj, driver, dstNode)

            else:
                raise NotImplementedError(ioObj, driver)

        extractor.extractSyncLogicNodesToNewElm_primaryOutputs()

        if self._dbgDumpNodes:
            HlsNetlistAnalysisPassDumpNodesDot(outputFileGetter(
                "tmp", f"SyncLowering.{self.sccIndex:d}.7.after.dot")
            ).runOnHlsNetlist(parentElm.netlist)

        HlsNetlistPassConsistencyCheck._checkNodeContainers(parentElm.netlist)
        HlsNetlistPassConsistencyCheck._checkConnections(parentElm.netlist, allowDisconnected=self._dbgAllowDisconnectedInputs)
