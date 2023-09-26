from typing import Set, List, Union, Literal

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidData
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, HlsNetNodeOut, \
    link_hls_nodes, _getPortDrive
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist


def extendSyncFlagsFrom(src: HlsNetNodeExplicitSync,
                        dst: HlsNetNodeExplicitSync):
    if src.extraCond:
        dst.addControlSerialExtraCond(src.dependsOn[src.extraCond.in_i])

    if src.skipWhen:
        dst.addControlSerialSkipWhen(src.dependsOn[src.skipWhen.in_i])


def extendSyncFlagsFromMultipleParallel(srcs: List[HlsNetNodeExplicitSync],
                                        dst: HlsNetNodeExplicitSync,
                                        worklist: UniqList[HlsNetNode]):
    """
    .. code-block:: python

        dst.extraCond &= Or(*src.extraCond & ~src.skipWhen for src in srcs)
        dst.skipWhen |=  And(src.skipWhen for src in srcs)
    """
    b: HlsNetlistBuilder = dst.netlist.builder

    srcsEc, srcsSw = mergeSyncFlagsFromMultipleParallel(srcs, worklist)

    ec = _getPortDrive(dst.extraCond)
    if srcsEc is not NOT_SPECIFIED:
        ecModified = False
        if srcsEc is None:
            # no extension is required because extraCond flags in srcs together al always satisfied
            pass
        elif ec is None:
            # add completly new extraCond
            dst.addControlSerialExtraCond(srcsEc)
            ecModified = True
        else:
            # extend current extraCond
            unlink_hls_nodes(ec, dst.extraCond)
            link_hls_nodes(b.buildAnd(ec, srcsEc), dst.extraCond)
            ecModified = True

        if ecModified:
            worklist.append(dst.dependsOn[dst.extraCond.in_i].obj)

    sw = _getPortDrive(dst.skipWhen)
    if srcsSw is not NOT_SPECIFIED:
        swModified = False
        if srcsSw is None:
            # skipWhen from srcs combined is never satisfied
            # this means that only skipWhen is actual one
            pass
        elif sw is None:
            dst.addControlSerialSkipWhen(srcsSw)
            swModified = True
        else:
            unlink_hls_nodes(sw, dst.skipWhen)
            link_hls_nodes(b.buildOr(sw, srcsSw), dst.skipWhen)
            swModified = True

        if swModified:
            worklist.append(dst.dependsOn[dst.skipWhen.in_i].obj)


def mergeSyncFlagsFromMultipleParallel(srcs: List[HlsNetNodeExplicitSync],
                                       worklist: UniqList[HlsNetNode]):
    b: HlsNetlistBuilder = srcs[0].netlist.builder

    srcsEc: Union[None, Literal[NOT_SPECIFIED], HlsNetNodeOut] = NOT_SPECIFIED
    srcsSw: Union[None, Literal[NOT_SPECIFIED], HlsNetNodeOut] = NOT_SPECIFIED
    for src in srcs:
        sEc = _getPortDrive(src.extraCond)
        sSw = _getPortDrive(src.skipWhen)
        if srcsSw is None:
            # there was some  non-optional path and now everything is non-optional
            pass
        elif srcsSw is NOT_SPECIFIED:
            # first
            srcsSw = sSw

        elif sSw is None:
            # this path in not-optional -> all other paths are not-optional
            srcsSw = None

        else:
            # aggregate another sSw
            srcsSw = b.buildAnd(srcsSw, sSw)
            worklist.append(srcsSw.obj)

        if sEc is None:
            # extraCond of this src is always satisfied
            pass
        else:
            # there is some src.extraCond
            if sSw is not None:
                sEc = b.buildAnd(sEc, b.buildNot(sSw))
                worklist.append(sEc.obj)

            if srcsEc is NOT_SPECIFIED:
                srcsEc = sEc
            else:
                srcsEc = b.buildOr(srcsEc, sEc)
                worklist.append(sEc.obj)

    return srcsEc, srcsSw


def netlistReduceExplicitSyncWithoutInput(
        dbgTracer: DebugTracer,
        n: HlsNetNodeExplicitSync,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        reachDb: HlsNetlistAnalysisPassReachability):
    """
    Collect all nodes which do have sync successors {n, } + successors[n] and do not affect control flags,
    move n before them (possibly duplicate and update data type) and update reachDb.
    """
    assert n._outputs[0]._dtype == HVoidData, (n, "Should be already converted to void")
    assert n.__class__ is HlsNetNodeExplicitSync, (n, "double check that we truly potentially moving just sync")
    builder: HlsNetlistBuilder = n.netlist.builder
    modified = False
    with dbgTracer.scoped(netlistReduceExplicitSyncWithoutInput, n):
        if not tuple(reachDb.getDirectDataPredecessors(n)):
            # sync n does not synchronize anything, safe to remove
            dbgTracer.log("rm because it has no effect on input")

            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)
            worklist.append(n.dependsOn[0].obj)
            addAllUsersToWorklist(worklist, n)
            builder.replaceOutput(n._outputs[0], n.dependsOn[0], True)
            for dep, i in zip(n.dependsOn, n._inputs):
                if dep is not None:
                    unlink_hls_nodes(dep, i)
            removed.add(n)
            modified = True

    return modified
