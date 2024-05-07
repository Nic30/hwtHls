from typing import Literal, Union, Dict

from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    ArchSyncNodeIoDict
from hwtHls.architecture.transformation.channelHandshakeCycleBreakUtils import ArchElementTermPropagationCtx, \
    resolveAckFromNodeIo
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.architecture.analysis.handshakeSCCs import ArchSyncSuccDict
from hwtHls.netlist.nodes.read import HlsNetNodeRead


def _resolveLocalOnlyIoAck(scc: UniqList[ArchSyncNodeTy],
                           #neighborDict: ArchSyncSuccDict,
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
        #elmNode, clkI_ = n
        #elmNode: ArchElement
        # isFsm = isinstance(elmNode, ArchElementFsm)
        # if nodeInputs or nodeOutputs or isFsm:
        # builder = builderForRoot.scoped(elmNode)

        # resolve ack from IO ports
        ioAck = None
        if nodeInputs or nodeOutputs:
            ioAck = resolveAckFromNodeIo(n, builder, termPropagationCtx, nodeInputs, nodeOutputs)

        if ioAck is not None:
            assert not isinstance(ioAck, HValue), (n, ioAck)

        ## resolve ack from buffers with capacity > 0
        #for channels in neighborDict[n].values():
        #    for c in channels:
        #        if isinstance(c, HlsNetNodeRead) and \
        #                c.associatedWrite and\
        #                c.associatedWrite._getBufferCapacity() > 0:
        #            vld = termPropagationCtx.propagate(n, c.getValidNB(), f"r{c._id}_validNB")
        #            ioAck = builder.buildAndOptional(ioAck, vld)

        localOnlyAckFromIo[n] = ioAck

    return localOnlyAckFromIo
