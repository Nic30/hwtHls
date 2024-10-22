from typing import Dict, List, Union, Set

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    HlsAndRtlNetlistAnalysisPassChannelGraph
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.analysis.handshakeSCCs import \
    ArchSyncSuccDiGraphDict, HlsAndRtlNetlistAnalysisPassHandshakeSCC, AllIOsOfSyncNode
from hwtHls.architecture.analysis.syncNodeFlushing import HlsAndRtlNetlistAnalysisPassSyncNodeFlushing
from hwtHls.architecture.analysis.syncNodeGraph import ChannelSyncType, \
    HlsAndRtlNetlistAnalysisPassSyncNodeGraph
from hwtHls.architecture.transformation._syncLowering.syncLogicAbcToHlsNetlist import SyncLogicAbcToHlsNetlist
from hwtHls.architecture.transformation._syncLowering.syncLogicResolver import SyncLogicResolver
from hwtHls.architecture.transformation._syncLowering.utils import hasNotAnySyncOrFlag, \
    _moveNonSccChannelPortsToIO
from hwtHls.architecture.transformation.dce import ArchElementDCE
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.architecture.transformation.simplify import ArchElementValuePropagation
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx, \
    ArchSyncNodeTerm
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel, \
    HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.translation.dumpNodesDot import HlsNetlistAnalysisPassDumpNodesDot
from hwtHls.platform.fileUtils import outputFileGetter
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsArchPassSyncLowering(HlsArchPass):
    """
    This pass lowers abstract HlsNetNodeRead/Write operations to non blocking variant with just extraCond flag.
    In this form nodes directly represent RTL. This lowering generates logical expression for io port enable
    and removes potential combinational loops in synchronization logic.
    
    Handshake logic is generated from several things:
    * synchronization flags of channels
    * control signals of primary inputs/outputs
    * buffer state flags

    Cycles in handshake logic coming from 3 main causes:
    * Cycles in handshake channel graph 
    * Channels without any buffer
    * Channel control flags (extraCond/skipWhen) derived from ready/valid of some channel
    
    This implies that any architecture with a cycle or 0 clock parallel path in handshake will generate combinational cycle
    in control signals :ref:`_fighanshakeDisallowed`. Thus the rewrite implemented in this pass is required.
    
    .. _fighanshakeDisallowed:
    
    .. figure:: _static/syncLowering_hanshakeDisallowed.png
    
    The presence of skipWhen + channels without buffer makes synchronization allocation complex
    * Various subsets of the circuit may be activated under complex conditions
    
    The principle of this algorithm:
    * Detect ArchSyncNodes, channels connecting them and IO.
    * Collect all channel and IO conditions (extraCond/skipWhen/mayFlush/validNB/valid/ready/readyNB, ...)
    * Create a dummy variable representing enable for each ArchSyncNode
    * Replace each channel valid/validNB/ready/readyNB with "and" of it with otherElment.enable & otherSide.extraCond & ~otherSide.skipWhen
    * Set ArchSyncNode enable as ask of StreamNode (all inputs (valid & extraCond) | skipWhen &
                                                    all outputs (ready & extraCond) | skipWhen)
      (generated expressions likely to contain combinational loops)
    * Remove combinational loops in expressions by iterative expansion on terms,
      While setting the term to 1 in equation for itself.
    
    :attention: It is expected that for non-blocking operations the ready/valid is anded to every
        into every channel flag, which is using this data.

    Input circuit:
      * any type of read/write, but immediate backedge must have non blocking read/write
      * possible combinational loop due to ready/valid handshake logic and due to use of ready/valid/stateEn
        in channel sync flag (extraCond/skipWhen/mayFlush)
      * Channels are connecting all sync nodes which needs to be synchronized.
        (:class:`RtlArchPassAddImplicitSyncChannels` is applied)
    
    Output Circuit:
      * each read/write in HsSCC
        * is non-blocking only
        * and has extraCond which includes sync with every other node in HsSCC
        * and has no skipWhen
        * writes may become flushable if allowed and considered required by :class:`HlsAndRtlNetlistAnalysisPassSyncNodeFlushing`
      * all sync logic for every HsSCC is in new arch element to improve readability

    :note: The synchronization SCC may be composed by sync nodes from different clock windows. This may be because
    there are some parallel paths of unequal length in the circuit as shown in  :ref:`_figunbalanced_diamond` or simply
    by ready signal going to a different clock windows.
    
    .. _figunbalanced_diamond:
    
    .. figure:: _static/syncLowering_pipeline_unbalanced_diamond.png
    
    :attention: This does not solve general combinational loop problem.
        This is specifically meant for control logic.
    
    Example of comb loop which this solver can not solve
    .. code-block::python
        def thread0(d):
            if d.ready:
                d.write(0)
            else:
                d.write(x)

        def thread1(d):
            if d.valid and d.data._eq(2):
                d.read()

        # Theoretical this is solvable because transaction happens only if x==2
        # however this prover proving only boolean expressions and d.data is considered
        # to be comb loop free because analysis of every expression like this would be very costly.
        
        # :note: The function of this code can still be realized without overhead
        #   if x==2 is pre-computed in thread0 and send to thread1 using other channel.
        # :note: If the rewrite would require some value from thread1 any backedge channel (including IMMEDIATE)
        #   may be used, but it is user responsibility that there is no combinational loop in the data.

    The problem comes from the fact that control is mixed with data logic which is not translated to ABC.
    In this example :ref:`_figflushProblem_controlMixedWithData` the mux is driven for valid of channels in the same clock
    window. However the the valid will not be 1 unless whole SCC will have ack, thus flushing will not work unless all input channels (r0, r1)
    also implement flushing.
    
    .. _figflushProblem_controlMixedWithData:
    
    .. figure:: _static/syncLowering_flushProblem_controlMixedWithData.png
    """

    def __init__(self, runLogicOptABC: bool=True,
                 dbgDumpAbc: bool=False,
                 dbgDumpNodes: bool=False,
                 dbgAllowDisconnectedInputs: bool=False,
                 # dbgDetectDeadlockedChannels: bool=False,
                 ):
        HlsArchPass.__init__(self)
        self._runLogicOptABC = runLogicOptABC
        self._dbgDumpAbc = dbgDumpAbc
        self._dbgDumpNodes = dbgDumpNodes
        self._dbgAllowDisconnectedInputs = dbgAllowDisconnectedInputs
        # self._dbgDetectDeadlockedChannels = dbgDetectDeadlockedChannels

    @staticmethod
    def _scheduleDefault(syncNode: ArchSyncNodeTy, out: HlsNetNodeOut) -> SchedTime:
        return scheduleUnscheduledControlLogic(syncNode, out)

    @classmethod
    def _discardSyncCausingLoop(cls, successors: ArchSyncSuccDiGraphDict,
                                scc: SetList[ArchSyncNodeTy], allSccIOs: AllIOsOfSyncNode):
        """
        Remove ready/valid signals which are reason for handshake SCC,
        (Before it will be replaced with acyclic logic)
        """
        for srcNode in scc:
            srcNode: ArchSyncNodeTy
            _successors = successors.get(srcNode, None)
            if _successors is None:
                continue
            for dstNode, channels in _successors.items():
                if dstNode in scc:
                    for channelTy, channelWr in channels:
                        channelWr: HlsNetNodeWriteAnyChannel
                        channelR: HlsNetNodeReadAnyChannel = channelWr.associatedRead
                        full = channelWr._fullPort
                        hasNotUsedfullPort = full is None or not channelWr.usedBy[full.out_i]
                        if channelTy == ChannelSyncType.VALID:
                            if not channelR.hasAnyUsedValidPort() and hasNotUsedfullPort:
                                channelR.setRtlUseValid(False)
                                channelWr.setRtlUseValid(False)

                        else:
                            assert channelTy == ChannelSyncType.READY, (channelTy, channelWr)
                            if channelWr._getBufferCapacity() == 0:
                                if channelR.extraCond is None:
                                    # if read is never blocked ready signal is not required
                                    channelR.setRtlUseReady(False)
                                    channelWr.setRtlUseReady(False)

                            # else
                            # we still need ready so the data wont leak from buffer read if dst node is stalling

                        if hasNotUsedfullPort and full is not None:
                            channelWr._removeOutput(full.out_i)

        for (_, ioNode, _, _) in allSccIOs:
            # set non blocking because check for ready/valid is already contained in every extraCond of every other ioNode
            ioNode._isBlocking = False
            for syncFlag in (ioNode._ready, ioNode._readyNB, ioNode._valid, ioNode._validNB):
                if syncFlag is not None and not ioNode.usedBy[syncFlag.out_i]:
                    ioNode._removeOutput(syncFlag.out_i)

    @classmethod
    def _removeChannelsWithoutAnyDataSyncOrFlag(cls, nodes: List[ArchSyncNodeTy],
                                                successors:ArchSyncSuccDiGraphDict):
        """
        :attention: The read/write nodes are moved from ArchElement but the successors dictionary is not updated.
        """
        nodesToRemove: Set[Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel]] = set()
        modifiedElements:SetList[ArchElement] = []
        for n in nodes:
            sucDict = successors.get(n, None)
            if not sucDict:
                continue
            for suc, w in sucDict.items():
                if not isinstance(w, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)):
                    continue
                w: HlsNetNodeWriteAnyChannel
                r: HlsNetNodeReadAnyChannel = w.associatedRead
                if hasNotAnySyncOrFlag(w) and\
                        len(r.channelInitValues) == 0 and\
                        HdlType_isVoid(r._portDataOut._dtype) and\
                        hasNotAnySyncOrFlag(r):
                    nodesToRemove.add(w)
                    nodesToRemove.add(r)
                modifiedElements.append(n[0])
                modifiedElements.append(suc[0])

        if modifiedElements:
            for elm in modifiedElements:
                elm: ArchElement
                elm.filterNodesUsingSet(nodesToRemove, recursive=True)
        else:
            assert not nodesToRemove

    @classmethod
    def _runSimplify(cls, dbgTracer: DebugTracer, netlist: HlsNetlistCtx,
                     scc: SetList[ArchSyncNodeTy],
                     sccSyncArcElm: ArchElementNoImplicitSync,
                     termPropagationCtx: ArchElementTermPropagationCtx):
        modifiedArchElements: SetList[ArchElement] = SetList([*(elm for elm, _ in scc), sccSyncArcElm, ])
        valPropagationWorklist: SetList[HlsNetNode] = SetList()
        for elm in modifiedArchElements:
            valPropagationWorklist.extend(elm.subNodes)
        ArchElementValuePropagation(dbgTracer, modifiedArchElements, valPropagationWorklist, termPropagationCtx)
        #ArchElementDCE(netlist, modifiedArchElements)

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        channels: HlsAndRtlNetlistAnalysisPassChannelGraph = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassChannelGraph)
        syncGraph: HlsAndRtlNetlistAnalysisPassSyncNodeGraph = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassSyncNodeGraph)
        hsSccs: HlsAndRtlNetlistAnalysisPassHandshakeSCC = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassHandshakeSCC)

        # result stored in write nodes
        netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassSyncNodeFlushing)

        # port+archElm+clkIndex -> output of ArchElement
        exportedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut] = {}
        stageEnForSyncNode: Dict[ArchSyncNodeTy, HlsNetNodeOut] = {}
        successors = syncGraph.successors
        neighborDict = channels.neighborDict
        nodeIo = channels.nodeIo
        clkPeriod = netlist.normalizedClkPeriod
        dbgTracer = DebugTracer(None)
        sccSyncArchElements: List[ArchElementNoImplicitSync] = []
        for sccIndex, (scc, allSccIOs) in enumerate(hsSccs.sccs):
            scc: SetList[ArchSyncNodeTy]
            allSccIOs: AllIOsOfSyncNode
            # print("HlsArchPassSyncLowering", sccIndex, scc)
            # generate synchronization logic and if possible, convert Non Oscillatory Feedback Paths
            # in handshake sync to Acyclic circuit

            # :note: HsScc logic is kept in separate element because it tends to significantly reduce readability
            # because most of the terms used in expressions are going to every other node
            # To linearize graph a little bit we use 1 node, pass all terms there and we compute enable conditions there
            # and the result is passed back to nodes of scc.
            sccSyncArcElm = ArchElementNoImplicitSync.createEmptyScheduledInstance(
                netlist, f"{netlist.namePrefix}hsSccSync{sccIndex:d}")
            sccSyncArchElements.append(sccSyncArcElm)

            termPropagationCtx = ArchElementTermPropagationCtx(
                exportedPorts, sccSyncArcElm, stageEnForSyncNode)

            _moveNonSccChannelPortsToIO(neighborDict, successors, scc, nodeIo)

            # [todo] predict ready chain latency and optionally use buffered handshake to cut ready chain to satisfy timing

            if self._dbgDumpNodes:
                HlsNetlistAnalysisPassDumpNodesDot(outputFileGetter("tmp", f"SyncLowering.{sccIndex:d}.0.before.dot")).runOnHlsNetlist(netlist)

            combLoopSolver = SyncLogicResolver(
                clkPeriod, scc, sccIndex,
                nodeIo,
                neighborDict,
                allSccIOs,
                self._dbgDumpAbc)
            combLoopSolver.translateToAbc()
            combLoopSolver.expandSyncExprToRmCombinationalLoops()

            toHlsNetlist = SyncLogicAbcToHlsNetlist(
                scc, sccIndex, allSccIOs, clkPeriod,
                combLoopSolver.syncLogicSearch,
                combLoopSolver.toAbc.translationCache,
                combLoopSolver.ioMap,
                combLoopSolver.toAbc.abcFrame,
                combLoopSolver.toAbc.net,
                self._dbgDumpNodes,
                self._dbgAllowDisconnectedInputs,
                # self._dbgDetectDeadlockedChannels
            )
            toHlsNetlist.translateFromAbcToHlsNetlist(
                sccSyncArcElm, termPropagationCtx)
            self._runSimplify(dbgTracer, netlist, scc, sccSyncArcElm, termPropagationCtx)

        for sccIndex, (scc, allSccIOs) in enumerate(hsSccs.sccs):
            scc: SetList[ArchSyncNodeTy]
            allSccIOs: AllIOsOfSyncNode
            # :note: this must be done after all SCCs were processed because this converts
            # io to non blocking and other SCC may use this to prove that the ready/valid must be always 1 if this SCC is executed
            self._discardSyncCausingLoop(successors, scc, allSccIOs)

        self._removeChannelsWithoutAnyDataSyncOrFlag(channels.nodes, successors)

        # :attention: successors become invalid
        successors = None
        ArchElementDCE(netlist, sccSyncArchElements, termPropagationCtx)

        pa = PreservedAnalysisSet.preserveScheduling()
        pa.add(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        # Not preserved because ready/valid of internal channels was dissolved:
        # HlsAndRtlNetlistAnalysisPassSyncNodeGraph
        # HlsAndRtlNetlistAnalysisPassHandshakeSCC
        return pa
