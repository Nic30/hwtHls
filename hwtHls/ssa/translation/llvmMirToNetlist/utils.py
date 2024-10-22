from typing import Optional, List, Tuple

from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoop
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny


class LiveInMuxMeta():

    def __init__(self):
        self.values: List[Tuple[HlsNetNodeOutAny, HlsNetNodeOutAny]] = []


def getTopLoopForBlock(mb: MachineBasicBlock, loop: MachineLoop) -> MachineLoop:
    loop: MachineLoop
    topLoop = loop
    while True:
        p: Optional[MachineLoop] = topLoop.getParentLoop()
        if p and p.getHeader() == mb:
            topLoop = loop
        else:
            break
    return topLoop

# tuples (controlEn, controlObj, allInputDataChannels)
# LoopPortGroup = List[Tuple[HlsNetNodeOutAny,
#                           HlsNetNodeReadAnyChannel,
#                           List[HlsNetNodeExplicitSync]]]

# def _createSyncForAnyInputSelector(builder: HlsNetlistBuilder,
#                                   inputCases: LoopPortGroup,
#                                   externalEn: Optional[HlsNetNodeOut],
#                                   externalEn_n: Optional[HlsNetNodeOut]):
#    """
#    Create a logic circuit which enables data inputs associated some control read port.
#    :param inputCases: list of case tuple (control channel, all input data channels)
#    """
#    if externalEn is None:
#        assert externalEn_n is None
#    else:
#        assert externalEn_n is not None
#
#    #anyPrevVld = None
#    for (controlEn, controlPort, data) in inputCases:
#        controlEn: HlsNetNodeOut
#        data: List[HlsNetNodeExplicitSync]
#        controlPort: Union[HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge]
#        assert controlEn is not None
#        assert isinstance(controlPort, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)), controlPort
#
#        #if not last:
#        #    # only last is non blocking because we need at least one to be blocking so body does not execute
#        #    # if no input is available
#        #    controlPort.setNonBlocking()
#        #if anyPrevVld is not None:
#        #    # controlPort.addControlSerialExtraCond(builder.buildNot(anyPrevVld))
#        #    controlPort.addControlSerialSkipWhen(builder.buildAndOptional(externalEn, anyPrevVld))
#
#        hasData = data and (len(data) > 1 or data[0] is not controlPort)
#        if hasData:
#            # construct conditions for data channels on demand
#            #if anyPrevVld is None:
#            #    # first item
#            #    en = controlEn
#            #else:
#            #    en = builder.buildAnd(builder.buildNot(anyPrevVld), controlEn)
#            #en = builder.buildAndOptional(controlVld, en)
#            en = builder.buildAnd(controlEn, controlPort.getValidNB())
#            dEn = builder.buildAndOptional(externalEn, en)
#            dSw = builder.buildOrOptional(externalEn_n, builder.buildNot(en))
#
#            for liveInSync in data:
#                liveInSync: HlsNetNodeRead
#                if liveInSync is controlPort:
#                    continue
#                liveInSync.addControlSerialExtraCond(dEn)
#                liveInSync.addControlSerialSkipWhen(dSw)
#
#        #anyPrevVld = builder.buildOrOptional(anyPrevVld, controlVld)
#    #return anyPrevVld
