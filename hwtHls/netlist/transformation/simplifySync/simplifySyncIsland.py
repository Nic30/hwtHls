"""
In general the transformation of an HlsNetNodeExplicitSync instances has to take in account
every first connected sync instances.
This is required because HlsNetNodeExplicitSync is kind of gate and when analyzing the flow through
the gate we have to analyze all possible ways which leads to the gate.
"""

from itertools import chain
from typing import Set, Tuple, Dict

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.syncDependecy import HlsNetlistAnalysisPassSyncDependency
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    unlink_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifySync.simplifyExplicitSync import netlistHoistExplicitSync, \
    extendSyncFlagsFromMultipleParallel, _getPortDrive, extendSyncFlagsFrom
from hwtHls.netlist.transformation.simplifySync.simplifySyncUtils import trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected, removeExplicitSync
from ipCorePackager.constants import DIRECTION
from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.debugTracer import DebugTracer


def discoverSyncIsland(inputNode: HlsNetNodeExplicitSync,
                       syncDeps: HlsNetlistAnalysisPassSyncDependency)\
        ->Tuple[Set[HlsNetNodeExplicitSync], Set[HlsNetNodeExplicitSync]]: 
    """
    This function search for sync nodes related to output first is search for all users of this node outputs
    and then again checks if there are more other sync dependencies and repeats the search also for them.
    This is how the island where this sync is a boundary is discovered.
    """       
    # find boundaries of local synchronization cluster
    inputs = set()
    outputs = set()
    toSearch = [(DIRECTION.IN, inputNode)]
    while toSearch:
        d, n0 = toSearch.pop()
        assert isinstance(n0, HlsNetNodeExplicitSync), n0
        n0: HlsNetNodeExplicitSync
        if d == DIRECTION.IN:
            if n0 in inputs:
                continue  # skip already seen
            else:
                inputs.add(n0)

            for o, uses in zip(n0._outputs, n0.usedBy):
                o: HlsNetNodeOut
                if (isinstance(n0, HlsNetNodeRead) and o is n0._validNB):  # HdlType_isNonData(o._dtype) or 
                    continue  # ignore control deps

                for u in uses:
                    u: HlsNetNodeIn
                    uObj = u.obj
                    if isinstance(uObj, HlsNetNodeExplicitSync):
                        # same as else just more efficient
                        toSearch.append((DIRECTION.OUT, uObj))
                    else:
                        toSearch.extend((DIRECTION.OUT, n1) 
                                        for n1 in syncDeps.getDirectDataSuccessors(n0)
                                        if isinstance(n1, HlsNetNodeExplicitSync))

        else:
            assert d == DIRECTION.OUT, d
            if n0 in outputs:
                continue  # skip already seen
            else:
                outputs.add(n0)
    
            for dep in n0.dependsOn:
                if dep is None:
                    raise AssertionError(n0.__class__, n0._id, "should be already removed")
                if (isinstance(dep.obj, HlsNetNodeRead) and dep is dep.obj._validNB):  # HdlType_isNonData(dep._dtype) or 
                    continue
                depObj = dep.obj
                if isinstance(depObj, HlsNetNodeExplicitSync):
                    toSearch.append((DIRECTION.IN, depObj))  # same as else just more efficient
                else:
                    toSearch.extend((DIRECTION.IN, n1)
                                    for n1 in syncDeps.getDirectDataPredecessors(n0)
                                    if isinstance(n1, HlsNetNodeExplicitSync))
    
    return inputs, outputs


def netlistReduceExplicitSyncMergeSuccessorIsland(
        dbgTracer: DebugTracer,
        n: HlsNetNodeExplicitSync,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        syncDeps: HlsNetlistAnalysisPassSyncDependency,
        threads: HlsNetlistAnalysisPassDataThreads,
        optimizedNodes: Set[HlsNetNodeExplicitSync]):
    """
    While merging HlsNetNodeExplicitSync nodes it is required to check all sync nodes which are related
    to inputs and outputs of this sync. This means that it is required to search reachability in bout directions,
    when searching for related sync nodes.
    """
    inputs, outputs = discoverSyncIsland(n, syncDeps)
    iCnt = len(inputs)
    oCnt = len(outputs)
    with dbgTracer.scoped(netlistReduceExplicitSyncMergeSuccessorIsland, n):
        # print("netlistReduceExplicitSyncMergeSuccessorIsland", n, iCnt, oCnt, sorted([n._id for n in inputs]),
        #                    sorted([n._id for n in outputs]))
        optimizedNodes.update(inputs)
        if iCnt == 1 and oCnt == 1:
            # a sequence of sync
            src = tuple(inputs)[0]
            assert src is n
            dst = tuple(outputs)[0]
            if threads.threadPerNode[src] is not threads.threadPerNode[dst]:
                # can not sink or hoist because there is no data dependency which would 
                # assert that the circuit would behave the same once the sync flag is moved
                # up or down in the circuit
                return False
    
            # dst control or ordering depends as well on src
            controlDependsOnSrc = False
            for i, dep in zip(dst._inputs, dst.dependsOn):
                dst: HlsNetNodeExplicitSync
                if i.in_i != 0:
                    depObj = dep.obj
                    controlDependsOnSrc |= depObj is src or\
                        syncDeps.doesReachTo(src, depObj)
    
                    if controlDependsOnSrc:
                        break
            
            # If we hoist sync flags from successor to predecessor we may cancel the move of the successor
            # if predecessor data is not always valid.
            hasNoSkipWhen = src.skipWhen is None and dst.skipWhen is None
            if controlDependsOnSrc:
                # sink control
                if (src.__class__ is HlsNetNodeExplicitSync or hasNoSkipWhen) and\
                        (src.extraCond is not None or src.skipWhen is not None):
                    dbgTracer.log(("sink control to", dst._id))
                    # transfer from successor to this to optimize final extraCond and skipWhen flags
                    # which are controlling the channel
                    trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(src, dst)
                    # if src.__class__ is HlsNetNodeExplicitSync:
                    #    netlistReduceExplicitSyncUseless(src, worklist, removed, syncDeps)
                    # else:
                    optimizedNodes.remove(src)
                    worklist.append(src)
    
                    optimizedNodes.discard(dst)
                    worklist.append(dst)
                    return True
            else:
                # hoist control
                if (dst.__class__ is HlsNetNodeExplicitSync or hasNoSkipWhen) and (dst.extraCond is not None or dst.skipWhen is not None):
                    # transfer from successor to this to optimize final extraCond and skipWhen flags
                    # which are controlling the channel
                    dbgTracer.log(("hoist control from", dst._id))
                    trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(dst, src)
    
                    optimizedNodes.remove(src)
                    worklist.append(src)
                    optimizedNodes.discard(dst)
                    worklist.append(dst)
                    return True
    
        elif iCnt == 1 and oCnt > 1:
            # parallel output sync with a single input
            assert tuple(inputs)[0] is n
            outputs = sorted(outputs, key=lambda o: o._id)
            everySucIsSync = all(o.__class__ is HlsNetNodeExplicitSync for o in outputs)
            if everySucIsSync:
                # it may be possible to hoist all outputs to this
                everyFlagHoistable = True
                for o in outputs:
                    for p in (o.skipWhen, o.extraCond):
                        d = _getPortDrive(p)
                        if p is not None and syncDeps.doesReachTo(n, d):
                            everyFlagHoistable = False
                            break
                        
                if everyFlagHoistable:
                    dbgTracer.log(("hoist control from many and remove sucs", outputs), lambda x: f"{x[0]} {[o._id for o in x[1]]}")
                    extendSyncFlagsFromMultipleParallel(outputs, n, worklist)
                    for o in outputs:
                        removeExplicitSync(o, worklist, removed)
                    worklist.append(n)
                    return True
                
            if n.__class__ is HlsNetNodeExplicitSync:
                # :note: can sink because there is no risk that we require some input which may be optional
                if n.skipWhen is None and n.extraCond is None:
                    # nothing to sink
                    dbgTracer.log("rm")
                    pass
                else:
                    # sink n flags to every o
                    dbgTracer.log(("sink control to many and remove self", outputs), lambda x: f"{x[0]} {[o._id for o in x[1]]}")
                    for o in outputs:
                        extendSyncFlagsFrom(n, o)
    
                removeExplicitSync(n, worklist, removed)
                worklist.extend(outputs)
                
                return True
    
            return False
    
        elif iCnt > 1 and oCnt == 1:
            # parallel input sync with a single output
            
            # :note: For each node a sync from every transitively connected input must be connected at once
            #   or it must not be sinked at all because change in order would change functionality of sync flags.
            
            # :note: there is a risk that some input is optional, for this we have to probe the island
            # to discover if here is some mux which cuts the dependency on input under some condition
            # and there are some sync flags which allow for input skip we must not sink behind this mux
            # because it would make input always required
            return False
            # raise NotImplementedError(inputs, outputs)
    
        elif iCnt > 1 and oCnt > 1:
            # n inputs to m outputs
            # try merge sync with the same sync flags to reduce total number of sync
            # For every output try hoist sync flags as much as possible
            
            # if any other opt. is not possible, try to hoist this node if it is HlsNetNodeExplicitSync
            modified = False
            # :note: inputs/outputs do not need to be disjunct that is why set is used
            for p in sorted(set(chain(inputs, outputs)), key=lambda x: x._id):
                if p.__class__ is HlsNetNodeExplicitSync:
                    if netlistHoistExplicitSync(dbgTracer, p, worklist, removed, syncDeps):
                        dbgTracer.log(("hoist", p._id))
                        modified = True
            
            if modified:
                for i in inputs:
                    optimizedNodes.remove(i)
                for o in outputs:
                    optimizedNodes.discard(o)
    
                worklist.extend(inputs)
                worklist.extend(outputs)

            elif n.__class__ is HlsNetNodeExplicitSync:
                # it is not possible to hoist any sync, the remaining option is to sink flags from this sync to
                # connected nodes sync nodes of this island.
                
                # All sync flags from every input HlsNetNodeExplicitSync can be moved to every direct data successor of each HlsNetNodeExplicitSync
                # The move is impossible if some sync flags can not be moved.
                sucs = tuple(syncDeps.getDirectDataSuccessors(n))
                dbgTracer.log(("sink control to successors and remove self", sucs), lambda x: f"{x[0]} {[o._id for o in x[1]]}")

                for isLast, suc in iter_with_last(sucs):
                    preds = tuple(pred for pred in syncDeps.getDirectDataPredecessors(suc)
                                  if pred.__class__ is HlsNetNodeExplicitSync)
                    everyPredIsSync = True
                    for pred in preds:
                        if pred.__class__ is HlsNetNodeExplicitSync:
                            continue
                        everyPredIsSync = False
                    if not everyPredIsSync:
                        raise NotImplementedError()
                    
                    toRm = []
                    if len(preds) > 1:
                        extendSyncFlagsFromMultipleParallel(preds, n, worklist)
                        for pred in preds:
                            predSuccs = tuple(syncDeps.getDirectDataSuccessors(suc))
                            if len(predSuccs) == 1:
                                # [todo] ther may be the case where predecessors are somehov dependent on each other
                                # and there is some partial ordering betwen them, in this case predSuccs may contain other pred
                                toRm.append(pred)  
                        
                    else:
                        trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(n, suc, removeFromSrc=isLast)
                    worklist.append(suc)

                    for n1 in toRm:
                        removeExplicitSync(n1, worklist, removed)

                modified = True
                worklist.extend(inputs)
    
            return modified
    
        elif iCnt == 1 and oCnt == 0:
            # output of some other sync without any successor sync
    
            if n.__class__ is HlsNetNodeExplicitSync:
                # if not syncDeps.hasControlPredecessor(n):
                #    # this does not synchronize anything and it can be removed
                #    raise NotImplementedError(n)
    
                if netlistHoistExplicitSync(dbgTracer, n, worklist, removed, syncDeps):
                    dbgTracer.log("hoist tailing self")
                    return True
                
            return False
        else:
            raise AssertionError(iCnt, oCnt)
