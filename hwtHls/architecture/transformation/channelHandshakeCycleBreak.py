from typing import Dict, List, Union, Set, \
    Optional, Tuple

from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    ArchSyncNodeIoDict, HlsArchAnalysisPassChannelGraph, \
    ArchSyncChannelToParentDict
from hwtHls.architecture.analysis.handshakeSCCs import \
    ArchSyncSuccDiGraphDict, \
    HlsArchAnalysisPassHandshakeSCC, ArchSyncNodeTy_stringFormat_short, \
    TimeOffsetOrderedIoItem, ReadOrWriteType, AllIOsOfSyncNode
from hwtHls.architecture.analysis.syncNodeFlushing import HlsArchAnalysisPassSyncNodeFlushing
from hwtHls.architecture.analysis.syncNodeGraph import ChannelSyncType, \
    getOtherPortOfChannel, ArchSyncNeighborDict, HlsArchAnalysisPassSyncNodeGraph
from hwtHls.architecture.transformation.channelHandshakeCycleBreakDynamicLinkUtils import resolveDynamicallyDirectlyNotReachable, \
    DynamicallyDirectlyNotReachableFlagDict, DST_UNREACHABLE, \
    _getSyncNodeDynSkipExpression, resolveNodeInputsValidAndMayFlush, \
    ChannelHandshakeCycleDeadlockError, NoBufferWritePossibleToNodeDict, \
    PrunedConditions, PrunedConditions_append_and
from hwtHls.architecture.transformation.channelHandshakeCycleBreakLocalIoUtils import _resolveLocalOnlyIoAck, \
    _moveNonSccChannelPortsToIO
from hwtHls.architecture.transformation.channelHandshakeCycleBreakUtils import \
    hasSameDriver, hasNotAnySyncOrFlag, ArchSyncNodeTerm, \
    constructExpressionFromTemplate, optionallyAddNameToOperatorNode
from hwtHls.architecture.transformation.dce import ArchElementDCE
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.architecture.transformation.utils.syncUtils import insertDummyWriteToImplementSync
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx, \
    exportPortFromArchElement, importPortToArchElement
from hwtHls.netlist.analysis.nodeParentAggregate import HlsNetlistAnalysisPassNodeParentAggregate
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementNoSync import ArchElementNoSync
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel, \
    HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.writeHsSCCSync import HlsNetNodeWriteHsSccSync
from hwtHls.netlist.transformation.simplifyExpr.simplifyAbc import runAbcControlpathOpt


class RtlArchPassChannelHandshakeCycleBreak(RtlArchPass):
    """
    This pass detect Strongly Connected Components (SCCs) in handshake synchronization logic.
    Which would result in combinational logic in RTL.
    This logic is then rewritten to a acyclic version of circuit as described in:
    
    * Handshake protocols for de-synchronization https://doi.org/10.1109/ASYNC.2004.1299296
    * Acyclic modeling of combinational loops https://doi.org/10.1109/ICCAD.2005.1560091
    * A Technique to Avoid Combination Feedback Loop and Long Critical Path in Resource Sharing https://doi.org/10.1109/ICASIC.2007.4415842

    :note: There are two main approaches how to solve combinational loops in ready chains.
        1. Rewrite SCC logic to acyclic circuit as described in 
        2. Use buffer which can store data when ready was 0.
            * The buffered handshake https://zipcpu.com/blog/2017/08/14/strategies-for-pipelining.html
        The second method is simple but introduces significant overhead in terms of latency and FF consumption.
        That is why we are trying to avoid it.
    :note: This is typically solved using conversion to Petri net or signal transition graph (STG) (STG is variant of PN)

    :note: One ArchElement may be split to multiple stages. Sync graph uses :var:`~.ArchSyncNodeTy`.
    :note: Edges between arch elements can be implicit or explicit :see:`~.ArchSyncNodeConnection`.
    
    :note: In same clock cycle valid and ready logic must be combinationally solved. 
        When crossing clock boundary "valid" signal has a register so combination path is divided there.
        "ready" signal does not have this register by default and the combination path is connected from dst stage to src stage
        (as is the direction of ready signal).
        Register for "ready" can be added in the cost of duplication of all registers related to this ready signal.
    :attention: This pass expects :class:`hwtHls.architecture.transformation.addImplicitSyncChannels.RtlArchPassAddImplicitSyncChannels` was already applied.
    
    
    :note: Example of transformation (loop with 2 clock cycle body)
    # w1 - write io 1
    # r0 - read io 0
       
    .. code-block:: text
        
        # stage 0
        rb0 <r, v> # read backedge buffer 0 from previous stage
        wf1 <r, v>, capacity=1 # write forward edge 1, leading to next stage
        
        # stage 1
        rf1 <r, v> # read forward edge 1 from previous stage
        wb0 <r, v>, capacity=1 # write backedge 0, leading to previous stage
        
        
        # The combination loop is mainly because of backedge 0 ready signal
        rb0.ready = wf1.ready | ~wf1.full
        wf1.ready = wb0.ready | ~wb0.full
        wb0.ready = rb0.ready
    
        # This pass discards all ready RTL ready signals and
        # rewrites this to:
        
        # stage 0
        wSt0Ack.ready = ~wf1.full | ~wb0.full # can store data for stage 1 or stage 1 can consume current data
        rb0 <v>
        wf1 <v>
        
        # stage 1
        wSt1Ack.ready = ~wb0.full | ~wf1.full # can store data for stage 0 or stage 0 can consume current data 
        rf1 <v>
        wb0 <v>
        
        # ack for stage is build by template
        node0.ack = (n.localAck | (all paths from node0 to n are skipped |
                                   (all write transactions have space in buffers &
                                    all read transactions have data stored in buffer))) for n in nodes if n is not node0
    :note: read/write transactions mentioned in previous equation refers to channels on path between n and node0  

    This algorithm solves the problem of implementation of arbitrary circuit synchronized by handshake logic.
    It solves problem by two things
    1. it re-implements combinational loops in handshake logic as an acyclic circuit
    2. it breaks ready chains by register if previous fails
    
    The circuit is composed from atomic nodes :var:`~.ArchSyncNodeTy` which are always in 1 clock window
    and handshake channels which may be in arbitrary direction (forward, backward).
    Forward edges may have len 0 to 1 clock cycle backedges 0 to inf.
    In addition there are IO channels for each node.
    Each channel port has extraCond and skipWhen condition. skipWhen flag may dynamically disable communication
    with some nodes.
    
    Handshake synchronization may result combinational loops from two reasons.
    1. ready chains in loops or split-join like graphs
    2. communication in a single clock cycle
    
    The loop can be replaced by acyclic logic. The basic idea of this algorithm is to detect loop.
    And for each node in the loop check if all other nodes provide acknowledge.
    For simple handshake this is easy and it is implemented as part of the :class:`hwtLib.handshaked.streamNode.StreamNode`.
    However in this case each channel end  This implies that the graph may dynamically
    fall apart to several individual independently synchronized segments.

    For each node the activation condition is that every dynamically reachable node may be activated.
    Dynamically reachable nodes are those which are connected by channel with skipWhen=False
    
    The node activation condition is that:
    * all IO channels have ready/valid +extraCond or skipWhen
    * network channel ports have extraCond or skipWhen on both sides 
    
    :note: The channel and node activation conditions must be processed for every node separately.
        We can not propagate any partial expressions because such a expression would
        always contain some signal originating from this node thus enclosing the loop which we are trying to avoid.

    For all items in allIo which are ordered by time extract ack condition and append it to current
    expressions for every node in SCC.
    
    There are several potential problems which we are trying to avoid:
    1. Nodes are likely to be connected in loop and we must rewrite this loop to acyclic form
       so we can not just AND all ack conditions from other nodes. Because channel conditions
       are used to compute ACKs and this would result in another combinational loop. 
    2. Channel communication may by optional, this may result in synchronization of nodes
       to be dynamically disconnected.
    3. Cycles in channels also require flushing of outputs even if the part of the circuit scheduled after is not ready.
       This is to prevent deadlock.
    """

    # First we have to find out which part of the circuit can act independently:
    #  * for parts which can not act independently we can discard all internal sync and use just StreamNode approach
    #    for inputs and outputs
    #    (circuit can non act independently if all parts are connected trough non-optional channel path)
    #  * :note: The non optional connection may appear from 2 channels  with complementary condition
    #  * For independent parts we have to resolve if dependency is one-sided or bidirectional
    #    (The communication is optional on just one side if all paths connecting two circuit parts are optional just on on that one side)
    #  * For one-sidely dependent we discard all internal sync but we have to and validity of inputs to all conditions
    #    in part which is dependent
    #  * for bouth-sidely dependent parts we have to and all conditions with validity of all predecessor inputs from other part

    # case0 If channel is not-optional on booth sides                                   (priority 3 (the highest))
    #  * this is the same case as if all IO was in a single node (to each node we add dummy write with condition which is ack of other node)
    #  * reflexive (node0->node0) optional channels are allowed and do not require more complex sync
    #  * we implement this by adding of write with ack of other node to each node
    # case1 If channel is optional just on write side (same applies if it is read side) (priority 2)
    #  * all channel en in node1 should be anded with w.en & node0.allPredecessorIn.ack
    #  * all channel ack should be anded with ack ~w.en | other.ack
    #  * (if there are multiple channels see case3)
    # case2 If channel is optional on both sides                                        (priority 1)
    #  * protocol of inputs is no longer handshake if input is not driven from register
    #    because we require predecessor inputs used in condition to be valid to be ready
    # case3 If there are multiple channels between same nodes
    #  * it is the same as if there was just 1 but with more complex condition
    #    (except for flushing)

    # Flushing:
    #  * marks that data was consumed for sender
    # Flushing is required for writes which have optional read if there is an optional cycle on channel level
    # (c0.w needs to be capable of flushing)
    #   n0                n1
    # +-----------+      +----------------+
    # |     c0.w  | ->   | c0.r(has skip) |
    # |           |      |                |
    # |     c1.r  | <-   | c1.w(has skip) |
    # +-----------+      +----------------+
    #  * n0 has to always wait on n1, but c0 data needs to be transfered to n1 even in c1 is not active
    #  * if not flushed and all predecessor io ack than receiver may consume this data even without sender to have
    #    ack while asserting flushed flag = 1
    #  * flushing is not required for channels between nodes connected non-optionally

    # :note: during resolving of StreamNode for each node, ready signal must not be duplicated
    # and only a single ready per node must be used otherwise combinational loop appears
    #  * Same thing applies for valid if nodes are scheduled to same clock cycle.
    #
    # verify that is is possible to consume inputs and provide outputs on full rate if synchronization is reduced
    # (for example the scheduling may cause that the circuit wont be able to provide output in every cycle)

    # initialize channel sync types based on IO port sync and on presence of loops in code
    # * propagate hasValid and hasReady transitively

    def __init__(self, runLogicOptABC=True):
        RtlArchPass.__init__(self)
        self._runLogicOptABC = runLogicOptABC

    @staticmethod
    def _scheduleDefault(syncNode: ArchSyncNodeTy, out: HlsNetNodeOut) -> SchedTime:
        return scheduleUnscheduledControlLogic(syncNode, out)

    @classmethod
    def _discardSyncCausingLoop(cls, successors: ArchSyncSuccDiGraphDict,
                                scc: SetList[ArchSyncNodeTy]):
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
                        if channelTy == ChannelSyncType.VALID:
                            channelWr.associatedRead._rtlUseValid = channelWr._rtlUseValid = False
                        else:
                            assert channelTy == ChannelSyncType.READY, (channelTy, channelWr)
                            if channelWr._getBufferCapacity():
                                # we still need ready so the data wont leak from buffer read if dst node is stalling
                                channelWr._isBlocking = False
                            else:
                                channelWr.associatedRead._rtlUseReady = channelWr._rtlUseReady = False

    @classmethod
    def _constructWriteToImplementHsSCCnodeSync(cls, sccIndex: int, syncNode: ArchSyncNodeTy,
                                                parentNodeForScheduling: ArchSyncNodeTy,
                                                otherAcks: List[HlsNetNodeOut],
                                                builder: HlsNetlistBuilder,
                                                termPropagationCtx: ArchElementTermPropagationCtx)\
                                                ->HlsNetNodeOut:
        parentElm, dstClkIndex = syncNode
        netlist: HlsNetlistCtx = parentElm.netlist
        clkPeriod = netlist.normalizedClkPeriod
        assert len(syncNode) == 2, syncNode
        _enName = f"{ArchSyncNodeTy_stringFormat_short(syncNode):s}_en"
        enName = f"hsScc{sccIndex:d}_{_enName:s}"
        # create AND of otherAcks, apply scheduling and port it to dst sync node
        otherAcks = builder.buildAndVariadic(otherAcks)
        _otherAcks = otherAcks
        cls._scheduleDefault(parentNodeForScheduling, otherAcks)
        otherAcks = exportPortFromArchElement((termPropagationCtx.parentDstElm, dstClkIndex), otherAcks,
                                              _enName,
                                              termPropagationCtx.exportedPorts)
        otherAcks, _ = importPortToArchElement(otherAcks, enName, syncNode)

        # construct write to implement stalling of sync node
        latestAckTimeOffset: SchedTime = otherAcks.obj.scheduledOut[otherAcks.out_i]
        syncTime = dstClkIndex * clkPeriod + latestAckTimeOffset
        sync, _ = insertDummyWriteToImplementSync(parentElm, syncTime, enName, writeCls=HlsNetNodeWriteHsSccSync)
        sync.addControlSerialExtraCond(otherAcks, addDefaultScheduling=True)
        return _otherAcks

    @staticmethod
    def _getWritePossibleForSyncNode(
            successorsDirected: ArchSyncSuccDiGraphDict,
            writePossible: NoBufferWritePossibleToNodeDict,
            builder: HlsNetlistBuilder,
            node: ArchSyncNodeTy):
        """
        resolve expression which is 1 if all direct successors of node
        are able accept non-buffered writes or the write is skipped
        """

        _writePossible = writePossible[node]
        edgeWriteAckTermList: Optional[PrunedConditions] = None

        for suc in successorsDirected[node].keys():
            _edgeWriteAck = _writePossible.get(suc)
            if _edgeWriteAck is not None:
                print(node, suc, _edgeWriteAck[1])
                assert _edgeWriteAck[1], ("If there is a condition is must be satisfiable", node, suc)
                for term in _edgeWriteAck[1]:
                    shorted, edgeWriteAckTermList = PrunedConditions_append_and(edgeWriteAckTermList, term)
                    if shorted:
                        raise ChannelHandshakeCycleDeadlockError(
                            "It was proven that the node can not write"
                            " to non-buffered channels leading to multiple successor nodes."
                            " This leads to a deadlock.", node, suc, term)

        if edgeWriteAckTermList:
            edgeWriteAck = builder.buildAndVariadic(
                edgeWriteAckTermList[1],
                name=f"{ArchSyncNodeTy_stringFormat_short(node)}_noBuffWritePossible")
            return edgeWriteAck
        else:
            return None

    @classmethod
    def _addWriteWithReadyOfOthersToImplementReadyForSCC(cls,
            netlist: HlsNetlistCtx,
            scc: SetList[ArchSyncNodeTy],
            sccIndex: int,
            neighborDict: ArchSyncNeighborDict,
            localOnlyAckFromIo: Dict[ArchSyncNodeTy, HlsNetNodeOut],
            nodeCurrentIOVld: Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]],
            nodeIsNotDirectlyReachable: DynamicallyDirectlyNotReachableFlagDict,
            noBufferWritePossibleForSrcNode: Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]],
            builder: HlsNetlistBuilder,
            termPropagationCtx: ArchElementTermPropagationCtx) -> Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]]:
        """
        For each node add a HlsNetNodeRead which will not use RTL ready or valid, but it will have extraCond which is build
        from local ack and skipWhen of every other node in SCC.
        
        Builds an expression syncRead.extraCond = And(n.ack | n.notReachableFromCurrentNode() for n in scc if n is not currentNode)
        """

        # in ackForSyncNodes the out is inside of HsScc arch element node termPropagationCtx.parentDstElm
        ackForSyncNode: Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]] = {}
        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        for syncNode in scc:
            syncNode: ArchSyncNodeTy
            otherAcks = []
            _, dstClkIndex = syncNode
            # parentElm: ArchElement
            dstClkIndex: int
            parentNodeForScheduling = (termPropagationCtx.parentDstElm, 0)
            for otherSyncNode in scc:
                if otherSyncNode == syncNode:
                    continue
                ack = localOnlyAckFromIo[otherSyncNode]
                # :note: even if ack from io is None the otherSyncNode may be stalled because of channels
                ioAckOrNotLoaded = nodeCurrentIOVld[otherSyncNode]
                # stVld = termPropagationCtx.getStageEn(otherSyncNode)
                # if stVld is not None:
                #    ioAckOrNotLoaded = builder.buildOrOptional(
                #        ioAckOrNotLoaded,
                #        builder.buildNot(stVld)
                #    )
                ack = builder.buildAndOptional(ack, ioAckOrNotLoaded)
                noBuffWriteAck = noBufferWritePossibleForSrcNode.get(otherSyncNode)
                ack = builder.buildAndOptional(ack, noBuffWriteAck)

                skipOtherSyncNode = None
                if ack is not None and nodeIsNotDirectlyReachable is not None:
                    # build template for an expressions which means all paths from syncNode to otherSyncNode have skipWhen=1
                    _skipOtherSyncNode = _getSyncNodeDynSkipExpression(
                        syncNode, SetList(), otherSyncNode,
                        neighborDict, nodeIsNotDirectlyReachable,
                        termPropagationCtx)
                    assert _skipOtherSyncNode is not DST_UNREACHABLE, (
                        "Node must be reachable because it is in the same scc", syncNode, "->", otherSyncNode)
                    if _skipOtherSyncNode is None:
                        # if is None it means the node is always required and we do not have to modify ack
                        pass
                    else:
                        skipOtherSyncNode = constructExpressionFromTemplate(
                            builder, termPropagationCtx, _skipOtherSyncNode)
                        if isinstance(skipOtherSyncNode, HConst):
                            if skipOtherSyncNode:
                                # communication to otherSyncNode is always skipped we do not need to check for ack
                                continue
                            else:
                                skipOtherSyncNode = None
                        else:
                            optionallyAddNameToOperatorNode(
                                skipOtherSyncNode,
                                f"hsScc_skip_{ArchSyncNodeTy_stringFormat_short(syncNode)}__{ArchSyncNodeTy_stringFormat_short(otherSyncNode)}")
                            time = cls._scheduleDefault(parentNodeForScheduling, skipOtherSyncNode)
                            assert time // clkPeriod <= dstClkIndex, (
                                "importPortToArchElement() should port value to clock window of sync node",
                                syncNode, skipOtherSyncNode, time, time // clkPeriod, dstClkIndex, clkPeriod)

                if ack is not None:
                    if ack.obj.scheduledOut is None:
                        time = cls._scheduleDefault(parentNodeForScheduling, ack)
                    else:
                        time = ack.obj.scheduledOut[ack.out_i]
                    assert time // clkPeriod <= dstClkIndex, (
                        "importPortToArchElement() should port value to clock window of sync node",
                        syncNode, ack, time, time // clkPeriod, dstClkIndex)

                # ack = None means the otherSyncNode is always ready if this scc is

                if skipOtherSyncNode is not None:
                    ack = builder.buildOr(ack, skipOtherSyncNode)
                    time = cls._scheduleDefault(parentNodeForScheduling, ack)
                    assert time // clkPeriod <= dstClkIndex, (
                        "importPortToArchElement() should port value to clock window of sync node",
                        syncNode, ack, time, time // clkPeriod, dstClkIndex)

                if ack is not None:
                    otherAcks.append(ack)

            noBuffWriteAck = noBufferWritePossibleForSrcNode.get(syncNode)
            if noBuffWriteAck is not None:
                otherAcks.append(noBuffWriteAck)
            if otherAcks:
                otherAcks = cls._constructWriteToImplementHsSCCnodeSync(
                    sccIndex, syncNode, parentNodeForScheduling,
                    otherAcks, builder, termPropagationCtx)
                ackForSyncNode[syncNode] = otherAcks
            else:
                ackForSyncNode[syncNode] = None

        return ackForSyncNode

    @classmethod
    def _removeValidFromReadOfBackedgeIfAlwaysContainValidData(cls,
            scc: SetList[ArchSyncNodeTy], successors:ArchSyncSuccDiGraphDict):
        """
        Remove valid from backedges with read and write enabled under same condition
        and have init data so there is always some data in buffer.
        In this case valid is always 1.
        :attention: if all nodes in scc must be active at once
        """
        for n in scc:
            sucDict = successors.get(n, None)
            if not sucDict:
                continue
            for suc, sucChannels in sucDict.items():
                if suc not in scc:
                    continue
                for _, channelWrite in sucChannels:
                    if channelWrite._rtlUseValid and isinstance(channelWrite, HlsNetNodeWriteBackedge):
                        channelWrite: HlsNetNodeWriteBackedge
                        channelRead: HlsNetNodeReadBackedge = channelWrite.associatedRead
                        if hasSameDriver(channelWrite.extraCond, channelRead.extraCond) and\
                            hasSameDriver(channelWrite.skipWhen, channelRead.skipWhen):
                            if channelWrite.channelInitValues:
                                channelWrite._rtlUseValid = channelRead._rtlUseValid = False
                            else:
                                raise ChannelHandshakeCycleDeadlockError("Channel is written and read unconditionally in same handshake SCC, because channel is empty on start this will deadlock", channelWrite)

    @classmethod
    def _removeChannelsWithoutAnyDataSyncOrFlag(cls, nodes: List[ArchSyncNodeTy], successors:ArchSyncSuccDiGraphDict):
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
                        len(w.channelInitValues) == 0 and\
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

    @classmethod
    def _connectFlushingPortsForRestOfTheNodes(cls, netlist: HlsNetlistCtx,
                                               exportedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut],
                                               stageEnForSyncNode: Dict[ArchSyncNodeTy, HlsNetNodeOut],
                                               hsSccs: HlsArchAnalysisPassHandshakeSCC,
                                               ioNodeToParentSyncNode: ArchSyncChannelToParentDict):
        builderForRoot: HlsNetlistBuilder = netlist.builder

        # port+archElm+clkIndex -> output of ArchElement
        # for rest of the nodes connect ports used for flushing if required
        for sn, allNodeIOs in hsSccs.nodesOutsideOfAnySCC:
            sn: ArchSyncNodeTy
            if not allNodeIOs:
                continue

            ioIrelevantForFlushingCnt = 0
            for (_, ioNode, syncNode, ioTy) in reversed(allNodeIOs):
                assert syncNode is sn, (ioNode, syncNode, sn)
                if (ioTy == ReadOrWriteType.CHANNEL_W or ioTy == ReadOrWriteType.W) and ioNode._isFlushable:
                    break
                ioIrelevantForFlushingCnt += 1

            if ioIrelevantForFlushingCnt > 0:
                allNodeIOs = allNodeIOs[:-ioIrelevantForFlushingCnt]

            if not allNodeIOs:
                # there is no node requiring flushing ports
                continue

            syncArcElm = ArchElementNoSync.createEmptyScheduledInstance(
                    netlist, f"{netlist.namePrefix}flushingSync_{ArchSyncNodeTy_stringFormat_short(sn)}")

            builderForRoot.operatorCache.clear()  # we must prevent reuse of expr parts constructed in a different stage/ArchElement
            builder = builderForRoot.scoped(syncArcElm)
            termPropagationCtx = ArchElementTermPropagationCtx(
                exportedPorts, syncArcElm, stageEnForSyncNode)
            _, _, writeMayFlush = resolveNodeInputsValidAndMayFlush(
                [sn], allNodeIOs, builder, termPropagationCtx)

            cls._connectMayFlushPorts(termPropagationCtx, builder, syncArcElm, writeMayFlush, {}, ioNodeToParentSyncNode)
            yield syncArcElm, builder

    @classmethod
    def _connectMayFlushPorts(cls, termPropagationCtx: ArchElementTermPropagationCtx,
                              builder: HlsNetlistBuilder,
                              syncArcElm: ArchElementNoSync,
                              writeMayFlush: List[Tuple[ArchSyncNodeTy, HlsNetNodeWrite, HlsNetNodeOut]],
                              ackForSyncNode: Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]],
                              ioNodeToParentSyncNode: ArchSyncChannelToParentDict,
                              ):
        for syncNode, ioNode, mayFlushSrc in writeMayFlush:
            ioNode: HlsNetNodeWrite
            if not ioNode._rtlUseValid and isinstance(ioNode, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)):
                rNode: Union[HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge] = ioNode.associatedRead
                nodeWhereReadIs = ioNodeToParentSyncNode[rNode]
                ackOfNodeWhereReadIs: Optional[HlsNetNodeOut] = ackForSyncNode.get(nodeWhereReadIs, nodeWhereReadIs)
                rAck = ackOfNodeWhereReadIs
                rEc = rNode.getExtraCondDriver()
                if rEc is not None:
                    rEc = termPropagationCtx.propagate(nodeWhereReadIs, rEc, f"n{rNode._id}_extraCond")
                    rAck = builder.buildAndOptional(rAck, rEc)

                rSw = rNode.getSkipWhenDriver()
                if rSw is not None:
                    rSw = termPropagationCtx.propagate(nodeWhereReadIs, rSw, f"n{rNode._id}_skipWhen")
                    rAck = builder.buildAndOptional(rAck, builder.buildNot(rSw))
                if rAck is not None:
                    mayFlushSrc = builder.buildAnd(mayFlushSrc, rAck, f"n{ioNode._id}_mayFlush")

            if mayFlushSrc is None:
                # if mayFlush condition is None  it means that it is always 1
                # this may be the sign of that the flushing is not required
                # or that the write can really always flush
                isFlushedPort = ioNode._isFlushedPort
                if isFlushedPort is not None:
                    t = ioNode.scheduledOut[isFlushedPort.out_i]
                    builderForWriteNode = builder.scoped(syncNode[0])
                    cOut = builderForWriteNode.replaceOutputWithConst1b(isFlushedPort, False)
                    cNode: HlsNetNodeConst = cOut.obj
                    cNode.resolveRealization()
                    cNode._setScheduleZeroTimeSingleClock(t)

                ioNode.setFlushable(False)
                continue

            cls._scheduleDefault((syncArcElm, syncNode[1]), mayFlushSrc)
            mayFlush = termPropagationCtx.propagateFromDstElm(syncNode, mayFlushSrc, f"n{ioNode._id}_mayFlush")
            link_hls_nodes(mayFlush, ioNode._mayFlushPort, checkCycleFree=False)

    def _breakHandshakeLoopsForHsSCC(self,
                scc: SetList[ArchSyncNodeTy],
                sccIndex: int,
                allSccIOs: AllIOsOfSyncNode,
                sccSyncArcElm: ArchElementNoSync,
                builder: HlsNetlistBuilder,
                termPropagationCtx: ArchElementTermPropagationCtx,
                nodeIo: ArchSyncNodeIoDict,
                neighborDict: ArchSyncNeighborDict,
                successors: ArchSyncSuccDiGraphDict,
                ioNodeToParentSyncNode: ArchSyncChannelToParentDict,
                ):
        netlist = sccSyncArcElm.netlist
        nodeCurrentIOVld, ioCondVld, writeMayFlush = resolveNodeInputsValidAndMayFlush(
            scc, allSccIOs, builder, termPropagationCtx)
        nodeIsNotDynDirectlyReachable, writePossible = resolveDynamicallyDirectlyNotReachable(
            scc, neighborDict, ioCondVld, builder, termPropagationCtx)

        localOnlyAckFromIo = _resolveLocalOnlyIoAck(
            scc, nodeIo, builder, termPropagationCtx)

        writePossibleForSrcNode: Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]] = {
            n: self._getWritePossibleForSyncNode(
                successors,
                writePossible,
                builder,
                n) for n in scc
        }
        ackForSyncNode = self._addWriteWithReadyOfOthersToImplementReadyForSCC(
            netlist, scc, sccIndex, neighborDict, localOnlyAckFromIo,
            nodeCurrentIOVld,
            nodeIsNotDynDirectlyReachable, writePossibleForSrcNode,
            builder, termPropagationCtx)
        self._discardSyncCausingLoop(successors, scc)
        self._connectMayFlushPorts(termPropagationCtx, builder, sccSyncArcElm,
                                   writeMayFlush, ackForSyncNode,
                                   ioNodeToParentSyncNode)

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        channels: HlsArchAnalysisPassChannelGraph = netlist.getAnalysis(HlsArchAnalysisPassChannelGraph)
        syncGraph: HlsArchAnalysisPassSyncNodeGraph = netlist.getAnalysis(HlsArchAnalysisPassSyncNodeGraph)
        hsSccs: HlsArchAnalysisPassHandshakeSCC = netlist.getAnalysis(HlsArchAnalysisPassHandshakeSCC)
        # result stored in write nodes
        netlist.getAnalysis(HlsArchAnalysisPassSyncNodeFlushing)
        builderForRoot: HlsNetlistBuilder = netlist.builder
        assert builderForRoot

        # port+archElm+clkIndex -> output of ArchElement
        exportedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut] = {}
        stageEnForSyncNode: Dict[ArchSyncNodeTy, HlsNetNodeOut] = {}
        successors = syncGraph.successors
        nodeIo = channels.nodeIo

        try:
            sccSyncArchElements: List[ArchElementNoSync] = []
            for sccIndex, (scc, allSccIOs) in enumerate(hsSccs.sccs):
                scc: SetList[ArchSyncNodeTy]
                allSccIOs: AllIOsOfSyncNode
                # if possible, convert Non Oscillatory Feedback Paths in handshake sync to Acyclic circuit

                # :note: HsScc logic is kept in separate element because it tends to significantly reduce readability
                # because most of the terms used in expressions are going to every other node
                # To linearize graph a little bit we use 1 node, pass all terms there and we compute enable conditions there
                # and the result is passed back to nodes of scc.
                sccSyncArcElm = ArchElementNoSync.createEmptyScheduledInstance(
                    netlist, f"{netlist.namePrefix}hsSccSync{sccIndex:d}")
                sccSyncArchElements.append(sccSyncArcElm)

                builderForRoot.operatorCache.clear()  # we must prevent reuse of expr parts constructed in a different stage/ArchElement
                builder = builderForRoot.scoped(sccSyncArcElm)
                termPropagationCtx = ArchElementTermPropagationCtx(
                    exportedPorts, sccSyncArcElm, stageEnForSyncNode)

                _moveNonSccChannelPortsToIO(successors, scc, nodeIo)
                neighborDict = syncGraph.getNeighborDict()

                # [todo] predict ready chain latency and optionally use buffered handshake to cut ready chain to satisfy timing
                self._breakHandshakeLoopsForHsSCC(
                    scc, sccIndex, allSccIOs, sccSyncArcElm, builder, termPropagationCtx,
                    nodeIo, neighborDict, successors, channels.ioNodeToParentSyncNode)
                if self._runLogicOptABC:
                    runAbcControlpathOpt(builder, [], builder._removedNodes, sccSyncArcElm._subNodes)
                    sccSyncArcElm.filterNodesUsingSet(builder._removedNodes)

            for flushElm, builder in self._connectFlushingPortsForRestOfTheNodes(
                    netlist, exportedPorts, stageEnForSyncNode, hsSccs,
                    channels.ioNodeToParentSyncNode):
                sccSyncArchElements.append(flushElm)
                if self._runLogicOptABC:
                    runAbcControlpathOpt(builder, [], builder._removedNodes, flushElm._subNodes)
                    flushElm.filterNodesUsingSet(builder._removedNodes)

            self._removeChannelsWithoutAnyDataSyncOrFlag(channels.nodes, successors)
            # :attention: successors become invalid
            successors = None
            ArchElementDCE(netlist, sccSyncArchElements)
        finally:
            netlist.invalidateAnalysis(HlsNetlistAnalysisPassNodeParentAggregate)  # because we just added logic for sync of HsSCCs
