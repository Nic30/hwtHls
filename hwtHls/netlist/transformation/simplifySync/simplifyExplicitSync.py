from typing import Optional, Set, Tuple, List

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isNonData
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, HlsNetNodeOut, \
    HlsNetNodeIn, link_hls_nodes, _getPortDrive
from hwtHls.netlist.analysis.syncDependecy import HlsNetlistAnalysisPassSyncDependency
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist
from hwtHls.netlist.debugTracer import DebugTracer

# def collectNodesUntilExplicitSyncAndReduceUseless(dep: HlsNetNodeOut,
#                                                  seen: UniqList[HlsNetNode],
#                                                  worklist: UniqList[HlsNetNode],
#                                                  removed: Set[HlsNetNode]):
#    """
#    Move use->def and collect nodes, if node is HlsNetNodeExplicitSync try reduce it, if it is not reduced
#    stop search there otherwise continue the search.
#    """
#    modified = False
#    if dep.obj in seen or isinstance(dep.obj, HlsNetNodeExplicitSync):
#        seen.add(dep.obj)
#        return modified
#    
#    toSearch: UniqList[HlsNetNode] = UniqList([dep.obj])
#    while toSearch:
#        n = toSearch.pop()
#        if n in seen:
#            continue
#
#        seen.add(n)
#        for dep in n.dependsOn:
#            depO = dep.obj
#            while depO.__class__ is HlsNetNodeExplicitSync:
#                curIn = depO.usedBy[dep.out_i][0]
#                netlistReduceExplicitSyncConditions(depO, worklist, removed)
#                modified |= netlistReduceExplicitSyncUseless(depO, worklist, removed)
#                _curOut = curIn.obj.dependsOn[curIn.in_i]
#                if dep is _curOut:
#                    # reduction did not reduce anything
#                    break
#                else:
#                    dep = _curOut
#                    depO = dep.obj
#            
#            if depO in seen or isinstance(depO, (HlsNetNodeExplicitSync, HlsNetNodeReadSync)):
#                seen.add(depO)
#                if isinstance(depO, HlsNetNodeReadSync):
#                    try:
#                        seen.add(depO.dependsOn[0].obj)
#                    except:
#                        raise
#                continue
#
#            toSearch.append(depO)
#
#    return modified


def extendSyncFlagsFrom(src: HlsNetNodeExplicitSync,
                        dst: HlsNetNodeExplicitSync):
    if src.extraCond:
        dst.addControlSerialExtraCond(src.dependsOn[src.extraCond.in_i])
        # syncDeps.addOutUseChange(src.dependsOn[src.extraCond.in_i].obj)
        # syncDeps.addInDepChange(src)

    if src.skipWhen:
        dst.addControlSerialSkipWhen(src.dependsOn[src.skipWhen.in_i])
        # syncDeps.addOutUseChange(src.dependsOn[src.skipWhen.in_i].obj)
        # syncDeps.addInDepChange(src)


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
                    
    if srcsEc is not None:
        if ec is None:
            dst.addControlSerialExtraCond(srcsEc)
        else:
            unlink_hls_nodes(ec, dst.extraCond)
            link_hls_nodes(b.buildAnd(ec, srcsEc), dst.extraCond)
        worklist.append(dst.dependsOn[dst.extraCond.in_i].obj)

    if srcsSw is not None:
        if sw is None:
            dst.addControlSerialSkipWhen(srcsSw)
        else:
            unlink_hls_nodes(sw, dst.skipWhen)
            link_hls_nodes(b.buildOr(sw, srcsSw), dst.skipWhen)

        worklist.append(dst.dependsOn[dst.skipWhen.in_i].obj)
             

def _findBoundaryForSyncHoisting(n: HlsNetNodeExplicitSync, syncDeps: HlsNetlistAnalysisPassSyncDependency) -> UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]]:
    """
    Walk user->def and find nodes which are just data operations which can be moved behind this sync as they do
    not have any control side effects
    """
    boundary: UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]] = UniqList()
    toSearch: UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]] = UniqList([(n.dependsOn[0], n._inputs[0])])
    # a list of nodes where sync flags must be extended because
    # "n" sync flags were moved into fan-in of these nodes
    tiedSuccessorSync: UniqList[HlsNetNodeExplicitSync] = UniqList()
    while toSearch:
        curItem = toSearch.pop()
        curOut, _ = curItem 
        depObj = curOut.obj
        # if reaches to some port other than main data we can not move because it would create cycle in DAG
        if syncDeps.doesReachToPorts(depObj, n._inputs[1:]) or \
            isinstance(depObj, HlsNetNodeExplicitSync):  # stop search on HlsNetNodeExplicitSync
            boundary.append(curItem)
            continue

        # depObj._validNB is used somewhere else
        if isinstance(depObj, HlsNetNodeRead) and depObj._validNB and depObj.usedBy[depObj._validNB.out_i]:
            boundary.append(curItem)
            continue

        # if this node is in fan-in cones of multiple sync nodes we must check if we can cross it cross it
        dSuc = syncDeps.getDirectDataSuccessors(depObj)
        if len(dSuc) != 1 or tuple(dSuc)[0] is not n:
            # only if we can consume all nodes until set of Sync nodes we can cross this node
            # and implement sync by extension of flags for each predecessor and successor
            # and completely remove this node n
            nDependsOnAny = False
            for suc in dSuc:
                if suc is not n and (syncDeps.doesReachTo(suc, n) or any(syncDeps.doesReachTo(n, i) for i in suc._inputs[1:])):  # any(syncDeps.doesReachTo(o, suc) for o in n._outputs[1:]):
                    # can not hoist because n and suc are not on entirely parallel paths
                    nDependsOnAny = True
                    break
            if nDependsOnAny:
                boundary.append(curItem)
                continue

            tiedSuccessorSync.extend(dSuc)

        # continue search on predecessors of this node
        toSearch.extend(zip(curOut.obj.dependsOn, curOut.obj._inputs))
    # print("_findBoundaryForSyncHoisting", n._id, [b[0].obj._id for b in boundary], [x._id for x in tiedSuccessorSync])
    return boundary, tiedSuccessorSync

    
def netlistHoistExplicitSync(
        dbgTracer: DebugTracer,
        n: HlsNetNodeExplicitSync,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        syncDeps: HlsNetlistAnalysisPassSyncDependency):
    """
    Collect all nodes which do have sync successors {n, } + successors[n] and do not affect control flags,
    move n before them (possibly duplicate and update data type) and update syncDeps.
    """

    assert n.__class__ is HlsNetNodeExplicitSync, (n, "double check that we truly potentially moving just sync")
    boundary, tiedSuccessorSync = _findBoundaryForSyncHoisting(n, syncDeps)
    boundary: UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]]
    tiedSuccessorSync: UniqList[HlsNetNodeExplicitSync]
    builder: HlsNetlistBuilder = n.netlist.builder
    modified = False
    with dbgTracer.scoped(netlistHoistExplicitSync, n):
        if boundary:
            hasSingleBoundary = len(boundary) == 1
            for last, (insertO, insertI) in iter_with_last(boundary):
                insertO: HlsNetNodeOut
                insertI: HlsNetNodeIn
                if insertI.obj is n:
                    # if insertO is n.dependsOn[0]:
                    #    # is the current dependency
                    #    raise NotImplementedError("Hoist sync flags if possible")
                    #    assert hasSingleBoundary
                    #    return modified  # no change
                        
                    # inserting on a place where n was connected to source
                    pred = insertO.obj
                    if hasSingleBoundary and\
                            isinstance(pred, HlsNetNodeExplicitSync) and\
                            not syncDeps.doesReachToControl(pred, n):
                        # hoist by move of flags to predecessor and removal of this
                        pred: HlsNetNodeExplicitSync
                        dbgTracer.log(("rm and hois sync to predec", pred._id))
                        # print("hoist 0", n, "->", pred)
                        syncDeps.doesReachToControl(pred, n)
                        # syncDeps.addAllDepsToOutUseChange(n)
                        # syncDeps.addAllUsersToInDepChange(n)
                        # for _n in (n, pred):
                        #    syncDeps.addAllDepsToOutUseChange(_n)
                        if len(tiedSuccessorSync) > 1:
                            assert n in tiedSuccessorSync, n
                            extendSyncFlagsFromMultipleParallel(tiedSuccessorSync, pred, worklist)
                        else:
                            extendSyncFlagsFrom(n, pred)
    
                        # syncDeps.addAllDepsToOutUseChange(pred)
    
                        rmN = True
                        nDataOut = n._outputs[0]
                        if insertO._dtype != nDataOut._dtype:
                            if HdlType_isNonData(insertO._dtype) and nDataOut._dtype == BIT:
                                insertO = insertO.obj.getValid()
                                rmN = False
                            else:
                                raise NotImplementedError(insertO, nDataOut, insertO._dtype, nDataOut._dtype)
                        
                        builder.replaceOutput(nDataOut, insertO, True)
                        builder.replaceOutput(n.getOrderingOutPort(), pred.getOrderingOutPort(), True)
                        
                        # syncDeps.addOutUseChange(insertO.obj)
                        if rmN:
                            for i, dep in tuple(zip(n._inputs, n.dependsOn)):
                                unlink_hls_nodes(dep, i)
    
                            # syncDeps.popNode(n)
                            removed.add(n)
    
                        modified = True
                        worklist.append(pred)
                        break
        
                    # skip because we would replace n with the same n
                    continue
        
                elif hasSingleBoundary or last:
                    # move this node before this nodes, keeping node instance and its flags and ordering as is
                    if len(tiedSuccessorSync) > 1:
                        assert n in tiedSuccessorSync, n
                        dbgTracer.log(("hoist sync from successors", tiedSuccessorSync),
                                      formater=lambda x: f"{x[0]:s} {[suc._id for suc in x[1]]}")
                        extendSyncFlagsFromMultipleParallel([suc for suc in tiedSuccessorSync if suc is not n], n, worklist)

                    dbgTracer.log(("hoist behind", insertO.obj._id, insertO.out_i))
                    builder.moveSimpleSubgraph(n._inputs[0], n._outputs[0], insertO, insertI)
                    # HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
        
                    assert n._associatedReadSync is None, "Is expected to be removed by previous steps"
                else:
                    # possibly duplicate this node if there are multiple inputs of this graph which is being moved behind this explicit sync node
                    n1: HlsNetNodeExplicitSync = n.__class__(n.netlist, insertO._dtype)
                    if len(tiedSuccessorSync) > 1:
                        assert n in tiedSuccessorSync, n
                        dbgTracer.log(("hoist sync from successors", tiedSuccessorSync),
                                      formater=lambda x: f"{x[0]:s} {[suc._id for suc in x[1]]}")
                        extendSyncFlagsFromMultipleParallel(tiedSuccessorSync, n1, worklist)
                    else:
                        extendSyncFlagsFrom(n, n1)
    
                    # syncDeps.addAllDepsToOutUseChange(n1)
                    # syncDeps.addAllUsersToInDepChange(n1)
                    # syncDeps.addOutUseChange(insertO.obj)
                    # syncDeps.addInDepChange(insertI.obj)
                    dbgTracer.log(("duplicate n as", n1._id, "and insert behind", insertO.obj._id, insertO.out_i))

                    n.netlist.nodes.append(n1)
                    # HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                    builder.insertBetween(n1._inputs[0], n1._outputs[0], insertO, insertI)
                    # HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
        
                    worklist.append(n1)
        
                modified = True
    
            if modified:
                worklist.append(n)
                # syncDeps.commitChanges()
    
        elif not tuple(syncDeps.getDirectDataPredecessors(n)) and not tuple(syncDeps.getDirectDataSuccessors(n)):
            # sync n does not synchronize anything, safe to remove
            dbgTracer.log("rm")

            netlistExplicitSyncDisconnectFromOrderingChain(n)
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
