from typing import Literal, Union, Dict

from hwt.hdl.const import HConst
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    ArchSyncNodeIoDict
from hwtHls.architecture.analysis.handshakeSCCs import ArchSyncNodeTy_stringFormat_short
from hwtHls.architecture.transformation.channelHandshakeCycleBreakUtils import ArchElementTermPropagationCtx, \
    resolveAckFromNodeIo, optionallyAddNameToOperatorNode
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.ports import HlsNetNodeOut


def _resolveLocalOnlyIoAck(scc: SetList[ArchSyncNodeTy],
                           # neighborDict: ArchSyncSuccDict,
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
