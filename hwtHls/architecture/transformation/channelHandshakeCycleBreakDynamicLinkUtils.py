from enum import Enum
from functools import cmp_to_key
from typing import Dict, Optional, List, Tuple, Set, Union, Literal

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    ArchSyncNodeIoDict
from hwtHls.architecture.analysis.handshakeSCCs import ArchSyncSuccDict, \
    ArchSyncSuccDiGraphDict, ChannelSyncType, getOtherPortOfChannel
from hwtHls.architecture.transformation.channelHandshakeCycleBreakUtils import ArchElementTermPropagationCtx, \
    _getIOAck, \
    ArchSyncNodeTerm, ArchSyncExprTemplate, optionallyAddNameToOperatorNode
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import offsetInClockCycle
from hwtHls.netlist.transformation.simplifyUtils import popNotFromExpr
from hwtHls.netlist.nodes.const import HlsNetNodeConst


class ChannelHandshakeCycleDeadlockError(AssertionError):
    """
    An exception which is raised if deadlock in channels in handshake SCC is found.
    """


HlsNetNodeOutWithNegationFlag = Tuple[bool, HlsNetNodeOut]
# list of conditions from channel (AND should be applied to resolve final condition) + set to prune list values
# empty list means that the path is always active, None means that the path does not exist
PrunedConditions = Tuple[Set[HlsNetNodeOutWithNegationFlag], List[HlsNetNodeOut]]
# :var DynamicallyDirectlyNotReachableFlagDict: for every node for every connected node a flag which tells that all connections to to that node is disabled and not required (skipWhen=1)
#      There are two skipWhen flags each one for different side of channel.
#      If flag does not exit it is not stored in the dictionary.
#      BIT.from_py(1) means that the channel port is always optional.
# :note: does not contain reflexive edges
DynamicallyDirectlyNotReachableFlagDict = Dict[ArchSyncNodeTy,
                                               Dict[ArchSyncNodeTy,
                                                    Optional[PrunedConditions]
                                                    ]
                                               ]
# Dictionary containing r.skip | (w.condValid() & w.extraCond)
# for each node which has HlsNetNodeWriteForwardedge with bufferCapacity=0
NoBufferWritePossibleToNodeDict = DynamicallyDirectlyNotReachableFlagDict


def PrunedConditions_append_and(skipWhenList: Optional[PrunedConditions],
                                sw: Optional[HlsNetNodeOut]) -> bool:
    shorted = False
    if sw is None:
        if skipWhenList is None:
            skipWhenList = (set(), [])
        else:
            skipWhenList[0].clear()
            skipWhenList[1].clear()
        # None represents 0 -> whole list is resolved as 0
        shorted = True
    else:
        if isinstance(sw.obj, HlsNetNodeConst):
            if sw.obj.val:
                pass
            else:
                skipWhenList[0].clear()
                skipWhenList[1].clear()
                # None represents 0 -> whole list is resolved as 0
                shorted = True
            return shorted, skipWhenList

        swIsNegated, _, swUnnegated = popNotFromExpr(sw)
        swVal = (swIsNegated, swUnnegated)
        if skipWhenList is None:
            skipWhenList = (set((swVal,)), [sw, ])
        elif swVal in skipWhenList[0]:
            # the condition is already in list
            pass
        else:
            # search for negation of condition in list
            swValN = (not swIsNegated, swUnnegated)
            if swValN in skipWhenList[0]:
                # just found complementary condition
                # whole list is resolved as 0
                skipWhenList[0].clear()
                skipWhenList[1].clear()
                shorted = True
            else:
                skipWhenList[0].add(swVal)
                skipWhenList[1].append(sw)

    return shorted, skipWhenList


class ReadOrWriteType(Enum):
    CHANNEL_R, CHANNEL_W, R, W = range(4)


class DST_UNREACHABLE():

    def __init__(self):
        raise AssertionError("This class should be used only as a constant")


def _getSyncNodeDynSkipExpression(src: ArchSyncNodeTy,
                           curPath: SetList[ArchSyncNodeTy],
                           dst: ArchSyncNodeTy,
                           successorsUndirected: ArchSyncSuccDict,
                           nodeIsNotDirectlyReachable: DynamicallyDirectlyNotReachableFlagDict,
                           termPropagationCtx: ArchElementTermPropagationCtx)\
                           ->Union[ArchSyncExprTemplate, None, Literal[DST_UNREACHABLE]]:
    """
    Get expression which is 1 if all paths from src to dst have skipWhen=1 and thus dst.ack is not required for src.ack
    """
    if src is dst:
        return None  # no extra condition

    _successors = successorsUndirected.get(src, None)
    if _successors is None:
        return DST_UNREACHABLE

    # hsSccNode = (termPropagationCtx.parentDstElm, 0)
    curPath.append(src)
    andMembers: SetList[HlsNetNodeOut] = SetList()
    notReachFromSrc = nodeIsNotDirectlyReachable.get(src, None)
    for suc in _successors.keys():
        if suc in curPath:
            continue  # all parts of the path are already not skipped

        if notReachFromSrc is None:
            skippingSucFromSrc = None
        else:
            skippingSucFromSrc = notReachFromSrc.get(suc, None)
            if skippingSucFromSrc is not None:
                assert isinstance(skippingSucFromSrc, tuple) and len(skippingSucFromSrc) == 2, skippingSucFromSrc
                skippingSucFromSrc = skippingSucFromSrc[1]
        skippingSucFromSrc: Optional[List[HlsNetNodeOut]]

        # recursion to discover all paths between src and dst
        sucSkippingDst = _getSyncNodeDynSkipExpression(
            suc, curPath, dst, successorsUndirected,
            nodeIsNotDirectlyReachable, termPropagationCtx)
        if sucSkippingDst is None:
            # the dst is reachable and there is no skip option
            if skippingSucFromSrc is None:
                continue  # communication with suc is always optional and thus we can always skip it
            elif len(skippingSucFromSrc) == 0:
                p = curPath.pop()
                assert p is src, ("When leaving this function the path end must the one added at the beginning", p, src)
                return None  # suc is not optional, this makes this node not optional as well
            else:
                # ArchSyncNodeTerm(hsSccNode, skippingSucFromSrc,
                #    f"{ArchSyncNodeTy_stringFormat(src):s}_skipTo_{ArchSyncNodeTy_stringFormat(suc):s}")
                andMembers.extend(skippingSucFromSrc)

        elif sucSkippingDst is DST_UNREACHABLE:
            # Currently any path from suc does not lead to dst, we can ignore it, because we are computing expression only for dst.
            # Even though this is in SCC the path from src to dst may not exist because we are excluding nodes from current path
            # we do not check this part of the graph because it is checked when checking other node than dst.
            pass

        else:
            assert not isinstance(sucSkippingDst, HConst), sucSkippingDst
            assert not (isinstance(sucSkippingDst, ArchSyncNodeTerm) and
                        isinstance(sucSkippingDst.out, HConst)), sucSkippingDst.out

            if skippingSucFromSrc is None:
                if not(isinstance(sucSkippingDst, HConst) and sucSkippingDst):
                    andMembers.append(sucSkippingDst)
            elif len(skippingSucFromSrc) == 0:
                p = curPath.pop()
                assert p is src, ("When leaving this function the path end must the one added at the beginning", p, src)
                return None  # dst is not skippable

            elif isinstance(skippingSucFromSrc, HConst):
                if skippingSucFromSrc:
                    continue  # communication with suc is always optional and thus we can always skip it
                else:
                    p = curPath.pop()
                    assert p is src, ("When leaving this function the path end must the one added at the beginning", p, src)
                    return None  # False in and members -> result is never true -> return None to mark that
                    # dst is not skippable
            else:
                # skippingSucFromSrc = ArchSyncNodeTerm(
                #    hsSccNode, skippingSucFromSrc,
                #    f"{ArchSyncNodeTy_stringFormat(suc):s}_skipPathTo_{ArchSyncNodeTy_stringFormat(dst):s}")
                if isinstance(sucSkippingDst, HConst):
                    if sucSkippingDst:
                        continue  # andMember always True
                    else:
                        andMembers.extend(skippingSucFromSrc)
                else:
                    andMembers.append(
                        (HwtOps.OR, (sucSkippingDst, (HwtOps.AND, tuple(skippingSucFromSrc)))))

    p = curPath.pop()
    assert p is src, ("When leaving this function the path end must be the one added at the beginning", p, src)
    if len(andMembers) == 1:
        return andMembers[0]
    elif andMembers:
        return (HwtOps.AND, tuple(andMembers))
    else:
        return DST_UNREACHABLE


def HlsNetNodePreceCmp(a: HlsNetNode, b: HlsNetNode):
    t0 = a[0]
    t1 = b[0]
    if t0 != t1:
        return t0 - t1  # earlier first
    n0 = a[1]
    n1 = b[1]

    for dep in n1.dependsOn:
        if dep is not None and dep.obj is n0:
            return -1

    for dep in n0.dependsOn:
        if dep is not None and dep.obj is n1:
            return 1

    if isinstance(n0, HlsNetNodeReadBackedge):
        if n0.associatedWrite is n1:
            return -1  # read before write
    if isinstance(n0, HlsNetNodeReadForwardedge):
        if n0.associatedWrite is n1:
            return 1  # read after write

    if isinstance(n0, HlsNetNodeWriteBackedge):
        if n0.associatedRead is n1:
            return 1  # read before write
    if isinstance(n0, HlsNetNodeWriteForwardedge):
        if n0.associatedRead is n1:
            return -1  # read after write

    return n0._id - n1._id  # [todo] use reachability


HlsNetNodePreceCmpKey = cmp_to_key(HlsNetNodePreceCmp)


@staticmethod
def sortIoByOffsetInClkWindow(successors: ArchSyncSuccDiGraphDict,
                  nodeIo: ArchSyncNodeIoDict,
                  scc: SetList[ArchSyncNodeTy]):
    clkPeriod = scc[0][0].netlist.normalizedClkPeriod
    allIo: List[Tuple[SchedTime, HlsNetNodeExplicitSync, ArchSyncNodeTy, ReadOrWriteType]] = []
    seen: Set[HlsNetNodeReadOrWriteToAnyChannel] = set()
    for n in scc:
        reads, writes = nodeIo[n]
        for r in reads:
            allIo.append((r.scheduledZero, r, n, ReadOrWriteType.R))
        for w in writes:
            allIo.append((w.scheduledZero, w, n, ReadOrWriteType.W))

        for suc, sucChannelIo in successors[n].items():
            for chTy, chPort in sucChannelIo:
                chTy: ChannelSyncType
                chPort: HlsNetNodeReadOrWriteToAnyChannel
                otherChPort = getOtherPortOfChannel(chPort)
                if chPort not in seen:
                    seen.add(chPort)
                    if chTy == ChannelSyncType.READY:
                        ioTy = ReadOrWriteType.CHANNEL_R
                        _chPort = otherChPort
                        assert isinstance(_chPort, HlsNetNodeRead), _chPort
                    else:
                        assert chTy == ChannelSyncType.VALID
                        ioTy = ReadOrWriteType.CHANNEL_W
                        _chPort = chPort
                        assert isinstance(_chPort, HlsNetNodeWrite), _chPort

                    timeOff = offsetInClockCycle(_chPort.scheduledZero, clkPeriod)
                    allIo.append((timeOff, _chPort, n, ioTy))

                if otherChPort not in seen:
                    seen.add(otherChPort)
                    if chTy == ChannelSyncType.READY:
                        ioTy = ReadOrWriteType.CHANNEL_W
                        _otherChPort = chPort
                        assert isinstance(_otherChPort, HlsNetNodeWrite), _chPort
                    else:
                        assert chTy == ChannelSyncType.VALID
                        ioTy = ReadOrWriteType.CHANNEL_R
                        _otherChPort = otherChPort
                        assert isinstance(_otherChPort, HlsNetNodeRead), _chPort
                    timeOff = offsetInClockCycle(_otherChPort.scheduledZero, clkPeriod)
                    allIo.append((timeOff, _otherChPort, suc, ioTy))

    allIo = sorted(allIo, key=HlsNetNodePreceCmpKey)  # sort by offset in clock window
    return allIo


def _resolveDynamicallyDirectlyNotReachableLink(
        builder: HlsNetlistBuilder,
        termPropagationCtx: ArchElementTermPropagationCtx,
        ioCondVld: Dict[HlsNetNodeExplicitSync, HlsNetNodeOut],
        node: ArchSyncNodeTy,
        otherNode: ArchSyncNodeTy,
        sucChannels: List[HlsNetNodeReadOrWriteToAnyChannel],
        ):

    skipWhenList: Optional[PrunedConditions] = None
    writeSkipOrReadAcceptList: Optional[PrunedConditions] = None

    for channel in sucChannels:
        if channel._isBlocking:
            sw = channel.getSkipWhenDriver()
            if sw is not None:
                sw = termPropagationCtx.propagate(node, sw, f"w{channel._id}_sw")
                sw = builder.buildAndOptional(sw, ioCondVld[channel])

            if isinstance(channel, HlsNetNodeWrite):
                if channel._getBufferCapacity() > 0:
                    # sw = can skip or there is a place in the buffer
                    full = channel.getFullPort()
                    full = termPropagationCtx.propagate(node, full, f"w{channel._id}_full")
                    sw = builder.buildOrOptional(sw, builder.buildNot(full))
                else:
                    full = None
                # :note: if writeAckList becomes shorted it means that the channel
                # is never active and there is a deadlock on arch level

                # write.skipWhen | read.extraCond
                r = channel.associatedRead
                rEc = channel.associatedRead.getExtraCondDriver()
                if rEc is not None:
                    rEc = termPropagationCtx.propagate(otherNode, rEc, f"r{r._id}_extraCond")

                if rEc is not None and full is not None:
                    # dst ready or there is a place in buffer
                    rEc = builder.buildOr(rEc, builder.buildNot(full))

                writePossible = builder.buildOrOptional(sw, rEc)
                if writePossible is not None:
                    shorted, writeSkipOrReadAcceptList = PrunedConditions_append_and(
                        writeSkipOrReadAcceptList, writePossible)
                    if shorted:
                        raise ChannelHandshakeCycleDeadlockError(
                            "Conditions for channels without buffer between sync nodes result in deadlock"
                            " because write to channel is proven impossible", node, otherNode, channel)

            elif isinstance(channel, HlsNetNodeRead):
                if channel.getAssociatedWrite()._getBufferCapacity() > 0:
                    # there is some data in buffer we do not have to wait on src (otherNode) element to provide it
                    validNB = channel.getValidNB()
                    validNB = termPropagationCtx.propagate(node, validNB, f"w{channel._id}_validNB")
                    sw = builder.buildOrOptional(sw, validNB)

            shorted, skipWhenList = PrunedConditions_append_and(skipWhenList, sw)
            if shorted:
                # we discovered non optional link
                break

        else:
            # if it is non blocking it can be not-ready, thus same case as if skipWhen=1
            continue

    return skipWhenList, writeSkipOrReadAcceptList


def resolveDynamicallyDirectlyNotReachable(neighborDict: ArchSyncSuccDict,
                                           nodes: List[ArchSyncNodeTy],
                                           ioCondVld: Dict[HlsNetNodeExplicitSync, HlsNetNodeOut],
                                           builder: HlsNetlistBuilder,
                                           termPropagationCtx: ArchElementTermPropagationCtx)\
                                           ->Tuple[DynamicallyDirectlyNotReachableFlagDict,
                                                   NoBufferWritePossibleToNodeDict]:
    """
    For each node for each direct successor a flag which is 1 if all channels connected between these two nodes
    have skipWhen flags present and =1 on side from src node or buffer capacity allow to perform operation
    of src node without ready from dst node.
    
    :attention: There is an obscurity related to a fact that skipWhen conditions are ORed in expression
        and skipWhen expression may be invalid if it is resolved from invalid inputs. This is a problem if
        we use raw skipWhen conditions from other node without proper and with validity flag. 
    
    :param successorsUndirected: dictionary which holds the connections between nodes
    :param nodes: list of nodes to process
    :param termPropagationCtx: an object used to transfer values between ArchElement instances
    """
    nodeIsNotDynDirectlyReachable: DynamicallyDirectlyNotReachableFlagDict = {}
    writePossible: NoBufferWritePossibleToNodeDict = {}
    for node in nodes:
        _neighborDict = neighborDict.get(node, None)
        if not _neighborDict:
            continue  # no successors nothing to check
        nodeIsNotDynDirectlyReachable[node] = _nodeIsNotDirectlyReachable = {}
        writePossible[node] = _writePossible = {}
        for otherNode, sucChannels in _neighborDict.items():
            if otherNode == node:
                continue  # skip reflexive edges
            if otherNode not in nodes:
                # buffers to outside of SCC are considered IO and standard ready/valid
                # signaling is used for them
                continue

            _nodeIsNotDirectlyReachable[otherNode], _writePossible[otherNode] = _resolveDynamicallyDirectlyNotReachableLink(
                builder, termPropagationCtx, ioCondVld, node, otherNode, sucChannels)

    return nodeIsNotDynDirectlyReachable, writePossible


def resolveNodeInputsValid(successors: ArchSyncSuccDiGraphDict,
            nodeIo: ArchSyncNodeIoDict,
            scc: SetList[ArchSyncNodeTy],
            builder: HlsNetlistBuilder,
            termPropagationCtx: ArchElementTermPropagationCtx):
    # prepare ordered sequence of all IO and channels
    # vld means that the input data is valid or input is skipped
    # inVld = And(*((allPredecInVld(i) & ((i.valid & i.extraCond) | i.skipWhen)) for i in inputs))
    # ack means that node is skipped or ready to perform its function
    # ack = And(inVld,
    #           *((allPredecInVld(o) & ((o.ready & o.extraCond) | o.skipWhen)) for o in outputs)))
    # reach means that there is at least one channel path leading to/from node to dstNode
    # which is not skipped
    nodeCurrentIOVld: Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]] = {
        n: termPropagationCtx.getStageEn(n) for n in scc
    }
    # dictionary with output marking that the condition of write is in valid state
    ioCondVld: Dict[HlsNetNodeExplicitSync, HlsNetNodeOut] = {}
    # nodeCurrentAck: Dict[ArchSyncNodeTy, Optional[HlsNetNodeOut]] = {n:None for n in scc}
    # nodeCurrentReach: Dict[ArchSyncNodeTy, Tuple[Optional[HlsNetNodeOut], SetList[ArchSyncNodeTy]]] = {n:(None, SetList()) for n in scc}
    allIo = sortIoByOffsetInClkWindow(successors, nodeIo, scc)
    for (_, ioNode, syncNode, ioTy) in allIo:
        ioNode: HlsNetNodeExplicitSync
        syncNode: ArchSyncNodeTy
        ioTy: ReadOrWriteType
        _nodeCurrentIoVld: Optional[HlsNetNodeOut] = nodeCurrentIOVld[syncNode]
        ioCondVld[ioNode] = _nodeCurrentIoVld
        # _nodeCurrentIoAck = nodeCurrentAck[syncNode]
        if ioTy == ReadOrWriteType.R or ioTy == ReadOrWriteType.W:
            # :note: IO write may also read, that is why we process it the same
            inVld = _getIOAck(syncNode, builder, termPropagationCtx, _nodeCurrentIoVld, ioNode)
            # [todo] if it is write check that it also reads otherwise ignore this node

        elif ioTy == ReadOrWriteType.CHANNEL_R:
            # each channel port adds an a term to enable condition of node where it is
            # the term represents the enable of communication to node and ack of other node
            # :note: the ack from other node is at this point build only for predecessor IO
            # thus it can not create combinational loop because
            if ioNode.associatedWrite._getBufferCapacity() > 0:
                # if this is backedge we do not need to do anything special as the data is stored in some buffer
                inVld = _getIOAck(syncNode, builder, termPropagationCtx, _nodeCurrentIoVld, ioNode)
            else:
                # a situation where we have to check for ack in this dst node and also ack from src node
                # optionally we have to update node reachability if this is the channel is optional
                assert isinstance(ioNode, HlsNetNodeReadForwardedge), ioNode
                wEn = ioCondVld[ioNode.associatedWrite]
                # wEn = builder.buildAndOptional(wEn, _nodeCurrentIoVld)
                # if wEn is not None:
                #    optionallyAddNameToOperatorNode(wEn, f"r{ioNode._id}_wEn")
                inVld = _getIOAck(syncNode, builder, termPropagationCtx, _nodeCurrentIoVld, ioNode, extraExtraCond=wEn)

        elif ioTy == ReadOrWriteType.CHANNEL_W:
            if ioNode._getBufferCapacity() > 0:
                inVld = _nodeCurrentIoVld
            else:
                # situation where we must check from ack from this node side and also for ack in dst node
                # propagate inputs valid to dst node
                inVld = _nodeCurrentIoVld

            # If valid is used in non standard way, we have to and valid/validNB with en for this SCC part
            # because we have to assert that the channel valid signal correctly marks that
            # data is valid.
            # :note: We can not just and HsSCC en to extraCond because it would
            # just introduce another cycle in sync logic.
            # lcg = ioNode._loopChannelGroup
            # if lcg is not None:
            #    for loop, _ in lcg.connectedLoops:
            #        loop: HlsNetNodeLoopStatus
            #        # export en of src  node back to node
            #        en = localOnlyAckFromIo.get(srcNode)
            #        if en is None:
            #            continue  # does not need any change because srcNode turned out to be always active
            #        enName = f"{ArchSyncNodeTy_stringFormat_short(srcNode):s}_ioAck"
            #        en = exportPortFromArchElement((termPropagationCtx.parentDstElm, dstNode[1]), en,
            #            enName, termPropagationCtx.exportedPorts)
            #        en, time = importPortToArchElement(en, enName, dstNode)
            #        loop.addChannelExtraEnCondtion(lcg, en, enName, addDefaultScheduling=True,
            #                                       inputWireDelay=loop.scheduledZero - time)

        else:
            raise ValueError(ioTy)

        nodeCurrentIOVld[syncNode] = inVld

    return nodeCurrentIOVld, ioCondVld
