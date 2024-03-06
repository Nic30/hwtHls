from typing import Optional, List, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoop
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, HlsNetNodeOut


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
LoopPortGroup = List[Tuple[HlsNetNodeOutAny,
                           HlsNetNodeReadAnyChannel,
                           List[HlsNetNodeExplicitSync]]]


def _createSyncForAnyInputSelector(builder: HlsNetlistBuilder,
                                   inputCases: LoopPortGroup,
                                   externalEn: HlsNetNodeOut,
                                   externalEn_n: HlsNetNodeOut):
    """
    Create a logic circuit which select a first control input which is valid and enables all its associated data inputs.

    :param inputCases: list of case tuple (control channel, all input data channels)
    """
    anyPrevVld = None
    for last, (vld, controlPort, data) in iter_with_last(inputCases):
        # convertedToNb = False
        assert isinstance(controlPort, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)), controlPort
        controlPort: HlsNetNodeReadBackedge
        if not last:
            # only last is non blocking because we need at least one to be blocking so body does not execute
            # if no input is available
            controlPort.setNonBlocking()
        # vld: HlsNetNodeOut = controlPort.getValidNB()
        # convertedToNb = True

        # the actual value of controlSrc is not important there because
        # it is interpreted by the circuit, there we only need to provide any data for rest of the circuit
        # controlPort.addControlSerialExtraCond(externalEn)
        # controlPort.addControlSerialSkipWhen(externalEn_n)

        if anyPrevVld is None:
            # if last or convertedToNb:
            #    cEn = 1
            # else:
            #    cEn = vld_n

            # first item
            if data:
                dEn = builder.buildAnd(externalEn, vld)
                dSw = builder.buildOr(externalEn_n, builder.buildNot(vld))
            anyPrevVld = vld
        else:
            # if last or convertedToNb:
            #    cEn = anyPrevVld
            # else:
            #    cEn = builder.buildOr(anyPrevVld, vld_n)

            if data:
                en = builder.buildAnd(builder.buildNot(anyPrevVld), vld)
                dEn = builder.buildAnd(externalEn, en)
                dSw = builder.buildOr(externalEn_n, builder.buildNot(en))
            anyPrevVld = builder.buildOr(anyPrevVld, vld)

        # if isinstance(cEn, int):
        #    assert cEn == 1, cEn
        #    cEn = externalEn_n
        # else:
        #    cEn = builder.buildOr(externalEn_n, cEn)

        # controlPort.addControlSerialSkipWhen(cEn)
        for liveInSync in data:
            liveInSync: HlsNetNodeExplicitSync
            if liveInSync is controlPort:
                continue
            liveInSync.addControlSerialExtraCond(dEn)
            liveInSync.addControlSerialSkipWhen(dSw)

    return anyPrevVld
