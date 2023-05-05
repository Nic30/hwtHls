from typing import Union, Optional, List, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoop
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOutLazy, HlsNetNodeOut
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge


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


def HlsNetNodeExplicitSyncInsertBehindLazyOut(netlist: "HlsNetlistCtx",
                                              valCache: MirToHwtHlsNetlistValueCache,
                                              var: HlsNetNodeOutLazy,
                                              name: str) -> HlsNetNodeExplicitSync:
    """
    Prepend the synchronization to an operation output representing variable.
    """
    assert isinstance(var, HlsNetNodeOutLazy), var
    esync = HlsNetNodeExplicitSync(netlist, var._dtype, name=name)
    netlist.nodes.append(esync)
    assert len(var.keys_of_self_in_cache) == 1, "Implemented only for case where the input var was not propagated anywhere"

    # add original var as valCache unresolvedBlockInputs
    k = var.keys_of_self_in_cache[0]
    block, reg = k
    o = esync._outputs[0]
    # copy endpoints of var to newly generated sync node
    valCache._replaceOutOnInputOfBlock(block, reg, var, k, o)
    var.replaced_by = None  # reset because we will still use the object

    # put original lazy out back to cache so once
    # we resolve input we replace the input to this control and not the explicit sync which we just created
    valCache._moveLazyOutToUnresolvedBlockInputs(block, reg, var, k)
    valCache._toHlsCache[k] = o

    # connect original var to the input of sync node
    link_hls_nodes(var, esync._inputs[0])

    return esync


# tuples (controlEn, controlObj, allInputDataChannels)
LoopPortGroup = List[Tuple[HlsNetNodeOutAny,
                           Union[HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge],
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
        convertedToNb = False
        if isinstance(controlPort, HlsNetNodeReadBackedge):
            controlPort: HlsNetNodeReadBackedge
            controlPort.setNonBlocking()
            # vld: HlsNetNodeOut = controlPort.getValidNB()
            convertedToNb = True
        else:
            controlPort: HlsNetNodeExplicitSync
            # vld: HlsNetNodeOut = builder.buildReadSync(control.dependsOn[0])

        # the actual value of controlSrc is not important there because
        # it is interpreted by the circuit, there we only need to provide any data for rest of the circuit
        # controlPort.addControlSerialExtraCond(externalEn)
        # controlPort.addControlSerialSkipWhen(externalEn_n)

        if anyPrevVld is None:
            #if last or convertedToNb:
            #    cEn = 1
            #else:
            #    cEn = vld_n

            # first item
            if data:
                dEn = builder.buildAnd(externalEn, vld)
                dSw = builder.buildAnd(externalEn, builder.buildNot(vld))
            anyPrevVld = vld
        else:
            #if last or convertedToNb:
            #    cEn = anyPrevVld
            #else:
            #    cEn = builder.buildOr(anyPrevVld, vld_n)

            if data:
                en = builder.buildAnd(builder.buildNot(anyPrevVld), vld)
                dEn = builder.buildAnd(externalEn, en)
                dSw = builder.buildAnd(externalEn, builder.buildNot(en))
            anyPrevVld = builder.buildOr(anyPrevVld, vld)

        #if isinstance(cEn, int):
        #    assert cEn == 1, cEn
        #    cEn = externalEn_n
        #else:
        #    cEn = builder.buildOr(externalEn_n, cEn)

        # controlPort.addControlSerialSkipWhen(cEn)
        for liveInSync in data:
            liveInSync: HlsNetNodeExplicitSync
            liveInSync.addControlSerialExtraCond(dEn)
            liveInSync.addControlSerialSkipWhen(dSw)

    return anyPrevVld
