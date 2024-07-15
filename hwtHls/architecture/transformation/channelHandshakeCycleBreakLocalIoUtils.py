from typing import Literal, Union, Dict, List

from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    ArchSyncNodeIoDict
from hwtHls.architecture.analysis.handshakeSCCs import ArchSyncNodeTy_stringFormat_short,\
    TimeOffsetOrderedIoItem, AllIOsOfSyncNode
from hwtHls.architecture.transformation.channelHandshakeCycleBreakUtils import ArchElementTermPropagationCtx, \
    resolveAckFromNodeIo, optionallyAddNameToOperatorNode
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.architecture.analysis.syncNodeGraph import ArchSyncSuccDiGraphDict, \
    ChannelSyncType, getOtherPortOfChannel


def _resolveLocalOnlyIoAck(scc: SetList[ArchSyncNodeTy],
                           # neighborDict: ArchSyncNeighborDict,
                           nodeIo: ArchSyncNodeIoDict,
                           builder: HlsNetlistBuilder,
                           termPropagationCtx: ArchElementTermPropagationCtx):
    """
    for each node flag which is 1 if all IO (are ready/valid and have extraCond=1) or (skipWhen=1)
    (The value is 1 or output port of ArchElement)
    """

    localOnlyAckFromIo: Dict[ArchSyncNodeTy, Union[HlsNetNodeOut, Literal[None]]] = {}
    for n in scc:
        n: ArchSyncNodeTy
        nodeInputs, nodeOutputs = nodeIo[n]

        # ioAck = None
        # elmNode, clkI_ = n
        # elmNode: ArchElement
        # isFsm = isinstance(elmNode, ArchElementFsm)
        # if nodeInputs or nodeOutputs or isFsm:
        # builder = builderForRoot.scoped(elmNode)

        # resolve ack from IO ports
        ioAck = None
        if nodeInputs or nodeOutputs:
            ioAck = resolveAckFromNodeIo(n, builder, termPropagationCtx, nodeInputs, nodeOutputs)

        if ioAck is not None:
            assert not isinstance(ioAck, HConst), (n, ioAck)

        # # resolve ack from buffers with capacity > 0
        # for channels in neighborDict[n].values():
        #    for c in channels:
        #        if isinstance(c, HlsNetNodeRead) and \
        #                c.associatedWrite and\
        #                c.associatedWrite._getBufferCapacity() > 0:
        #            vld = termPropagationCtx.propagate(n, c.getValidNB(), f"r{c._id}_validNB")
        #            ioAck = builder.buildAndOptional(ioAck, vld)

        localOnlyAckFromIo[n] = ioAck
        optionallyAddNameToOperatorNode(ioAck, f"hsScc_localOnlyAckFromIo_{ArchSyncNodeTy_stringFormat_short(n)}")

    return localOnlyAckFromIo


def _moveNonSccChannelPortsToIO(successors: ArchSyncSuccDiGraphDict,
                                scc: SetList[ArchSyncNodeTy],
                                nodeIo: ArchSyncNodeIoDict,
                                allSccIOs: AllIOsOfSyncNode):
    """
    Channel read/write which is not part of handshake SCC is a normal IO and will not be rewritten.
    Thus we move it to nodeIo as normal IO.
    """
    for n in scc:
        n: ArchSyncNodeTy
        inputList, outputList = nodeIo[n]
        _successors = successors[n]
        toRm = set()
        # move suc channel to nodeIo if the suc is not in the same scc
        for suc , sucChannelIo in _successors.items():
            if suc not in scc:
                toRm.add(suc)
                for chTy, ch in sucChannelIo:
                    chTy: ChannelSyncType
                    if chTy == ChannelSyncType.READY:
                        ch = getOtherPortOfChannel(ch)
                        assert ch in n[0]._subNodes, ch
                        outputList.append(ch)
                    else:
                        assert ch in n[0]._subNodes, ch
                        inputList.append(ch)
                        # allSccIOs
        # rm suc which channels were converted to IO
        for suc in toRm:
            _successors.pop(suc)
