from typing import Set, Tuple, List

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidData
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, HlsNetNodeOut, \
    HlsNetNodeIn, link_hls_nodes, _getPortDrive
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
    ec = _getPortDrive(dst.extraCond)
    sw = _getPortDrive(dst.skipWhen)

    srcsEc = NOT_SPECIFIED
    srcsSw = NOT_SPECIFIED
    for src in srcs:
        sEc = _getPortDrive(src.extraCond)
        sSw = _getPortDrive(src.skipWhen)
        if srcsSw is None:
            pass
        elif srcsSw is NOT_SPECIFIED:
            srcsSw = sSw
        elif sSw is None:
            srcsSw = None
        else:
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
                    
    if srcsEc is not NOT_SPECIFIED:
        if ec is None:
            dst.addControlSerialExtraCond(srcsEc)
        else:
            unlink_hls_nodes(ec, dst.extraCond)
            link_hls_nodes(b.buildAnd(ec, srcsEc), dst.extraCond)
        worklist.append(dst.dependsOn[dst.extraCond.in_i].obj)

    if srcsSw is not NOT_SPECIFIED:
        if sw is None:
            dst.addControlSerialSkipWhen(srcsSw)
        else:
            unlink_hls_nodes(sw, dst.skipWhen)
            link_hls_nodes(b.buildOr(sw, srcsSw), dst.skipWhen)

        worklist.append(dst.dependsOn[dst.skipWhen.in_i].obj)
             

def _findBoundaryForSyncHoisting(n: HlsNetNodeExplicitSync) -> UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]]:
    boundary: UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]] = UniqList(zip(n.dependsOn, n._inputs))
    tiedSuccessorSync = UniqList(u.obj for u in n.usedBy[n.getOrderingOutPort().out_i])
    return boundary, tiedSuccessorSync

    
def netlistHoistExplicitSync(
        dbgTracer: DebugTracer,
        n: HlsNetNodeExplicitSync,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        reachDb: HlsNetlistAnalysisPassReachabilility):
    """
    Collect all nodes which do have sync successors {n, } + successors[n] and do not affect control flags,
    move n before them (possibly duplicate and update data type) and update reachDb.
    """
    assert n._outputs[0]._dtype == HVoidData, (n, "Should be already converted to void")
    assert n.__class__ is HlsNetNodeExplicitSync, (n, "double check that we truly potentially moving just sync")
    boundary, tiedSuccessorSync = _findBoundaryForSyncHoisting(n)
    boundary: UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]]
    tiedSuccessorSync: UniqList[HlsNetNodeExplicitSync]
    builder: HlsNetlistBuilder = n.netlist.builder
    modified = False
    with dbgTracer.scoped(netlistHoistExplicitSync, n):
        # [fixme] there may be io cluster core
        if len(boundary) == 1:
            (insertO, insertI), = boundary
            insertO: HlsNetNodeOut
            insertI: HlsNetNodeIn
            assert insertI.obj is n
            # if insertO is n.dependsOn[0]:
            #    # is the current dependency
            #    raise NotImplementedError("Hoist sync flags if possible")
            #    assert hasSingleBoundary
            #    return modified  # no change
                
            # inserting on a place where n was connected to source
            pred = insertO.obj
            if isinstance(pred, HlsNetNodeExplicitSync) and\
                    not reachDb.doesReachToControl(pred, n):
                # hoist by move of flags to predecessor and removal of this
                pred: HlsNetNodeExplicitSync
                dbgTracer.log(("rm and hoist sync to predec", pred._id))
                # print("hoist 0", n, "->", pred)
                # for _n in (n, pred):
                #    reachDb.addAllDepsToOutUseChange(_n)
                if len(tiedSuccessorSync) > 1:
                    assert n in tiedSuccessorSync, n
                    extendSyncFlagsFromMultipleParallel(tiedSuccessorSync, pred, worklist)
                else:
                    extendSyncFlagsFrom(n, pred)
    
                rmN = True
                nDataOut = n._outputs[0]
                assert insertO._dtype == nDataOut._dtype, (insertO, nDataOut)
                
                raise NotImplementedError("merge io clusters")
                builder.replaceOutput(nDataOut, insertO, True)
                builder.replaceOutput(n.getOrderingOutPort(), pred.getOrderingOutPort(), True)
                
                # reachDb.addOutUseChange(insertO.obj)
                if rmN:
                    for i, dep in tuple(zip(n._inputs, n.dependsOn)):
                        unlink_hls_nodes(dep, i)
    
                    # reachDb.popNode(n)
                    removed.add(n)
    
                modified = True
                worklist.append(pred)
    
            if modified:
                worklist.append(n)
                # reachDb.commitChanges()
    
        elif not tuple(reachDb.getDirectDataPredecessors(n)) and not tuple(reachDb.getDirectDataSuccessors(n)):
            # sync n does not synchronize anything, safe to remove
            dbgTracer.log("rm because it has no effect")

            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, removed)
            worklist.append(n.dependsOn[0].obj)
            addAllUsersToWorklist(worklist, n)
            builder.replaceOutput(n._outputs[0], n.dependsOn[0], True)
            for dep, i in zip(n.dependsOn, n._inputs):
                if dep is not None:
                    unlink_hls_nodes(dep, i)
            removed.add(n)
            modified = True
    
    return modified

# def netlistMergeParallelExplicitSync(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]) -> bool:
#    dep = n.dependsOn[0]
#    depUses = dep.obj.usedBy[dep.out_i]
#    parallelSyncs = []
#    for depUse in depUses:
#        if depUse.obj.__class__ is HlsNetNodeExplicitSync:
#            parallelSyncs.append(depUse.obj)
#    
#    if len(parallelSyncs) == 1:
#        return False
#
#    builder: HlsNetlistBuilder = n.netlist.builder
#    seenSyncFlags: Set[Tuple[Optional[HlsNetNodeOut], Optional[HlsNetNodeOut]]] = set()
#    newSkipWhen = None
#    newExtraCond = None
#    noSkipWhen = False
#    for sync in parallelSyncs:
#        sync: HlsNetNodeExplicitSync
#
#        if sync.skipWhen is not None:
#            sw = sync.dependsOn[sync.skipWhen.in_i]
#        else:
#            sw = None
#
#        if sync.extraCond is not None:
#            ec = sync.dependsOn[sync.extraCond.in_i]
#        else:
#            ec = None
#
#        # avoid pointless complication of expression by adding of same member
#        syncFlags = (ec, sw)
#        if syncFlags in seenSyncFlags:
#            continue
#        seenSyncFlags.add(syncFlags)
#    
#        # skipWhen &= skipWhen              # do not skip if any requires not to skip
#        if sw is not None: 
#            if not noSkipWhen: 
#                if newSkipWhen is None:
#                    newSkipWhen = sw
#                else:
#                    newSkipWhen = builder.buildAnd(newSkipWhen, sw)
#        else:
#            noSkipWhen = True
#            newSkipWhen = None
#   
#        # extraCond &= skipWhen | extraCond # en if all non skipping do have en
#        if ec is not None:
#            if sw is not None:
#                sw_n = builder.buildNot(sw)
#                ec = builder.buildAnd(sw_n, ec)
#        else:
#            if sw is not None:
#                ec = builder.buildNot(sw)
#            else:
#                ec = None
#
#        if ec is not None:
#            if newExtraCond is None:
#                newExtraCond = ec
#            else:
#                newExtraCond = builder.buildOr(newExtraCond, ec)
#
#    # find out if a sync which we are trying to create does exist
#    finalSync = None
#    for sync0 in parallelSyncs:
#        sync0: HlsNetNodeExplicitSync
#        if isInputConnectedTo(sync0.extraCond, newExtraCond) and isInputConnectedTo(sync0.skipWhen, newSkipWhen):
#            finalSync = sync0
#            break
#
#    if finalSync is None:
#        finalSync = HlsNetNodeExplicitSync(n.netlist, n._outputs[0]._dtype)
#        n.netlist.nodes.append(finalSync)
#        if newExtraCond is not None:
#            finalSync.addControlSerialExtraCond(newExtraCond)
#        if newSkipWhen is not None:
#            finalSync.addControlSerialSkipWhen(newSkipWhen)
#        link_hls_nodes(dep, finalSync._inputs[0])
#
#    newDataOut = finalSync._outputs[0]
#    # replace every other sync with sync0
#    for sync0 in parallelSyncs:
#        if sync0 is finalSync:
#            continue
#        builder.replaceOutput(sync0._outputs[0], newDataOut, True)
#        removeExplicitSync(sync0, worklist, removed)
#    worklist.append(finalSync)
#
#    return True

# def netlistMergeSerialExplicitSync(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]) -> bool:
#     dataUses = n.usedBy[0]
#     if len(dataUses) == 1 and dataUses[0].obj.__class__ is HlsNetNodeExplicitSync:
#         # remove self and add flags to successor
#         succ: HlsNetNodeExplicitSync = dataUses[0].obj
#         trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(n, succ)
#         mainDataDep = n.dependsOn[0]
#         link_hls_nodes(mainDataDep, succ._inputs[0])
#         removeExplicitSync(n, worklist, removed)
#         return True
#     else:
#         assert n.__class__ is HlsNetNodeExplicitSync  # should be already asserted, just to make extra sure
#         predO = n.dependsOn[0]
#         pred = predO.obj
#         if isinstance(pred, HlsNetNodeExplicitSync) and\
#             hasInputSameDriver(pred.extraCond, n.extraCond) and\
#             hasInputSameDriver(pred.skipWhen, n.skipWhen):
#             # if this have same sync flags as predecessor remove it because it is useless
#             # as the sync flags are already there
#             builder: HlsNetlistBuilder = n.netlist.builder
#             builder.replaceOutput(n._outputs[0], predO, True)
#             removeExplicitSync(n, worklist, removed)
#             return True
# 
#     return False
