"""ore
In general the transformation of an HlsNetNodeExplicitSync instances has to take in account
every first connected sync instances.
This is required because HlsNetNodeExplicitSync is kind of gate and when analyzing the flow through
the gate we have to analyze all possible ways which leads to the gate.
"""

from itertools import chain
from typing import Set

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifySync.simplifyExplicitSync import netlistHoistExplicitSync, \
    extendSyncFlagsFromMultipleParallel, _getPortDrive, extendSyncFlagsFrom
from hwtHls.netlist.transformation.simplifySync.simplifySyncUtils import trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected, removeExplicitSync
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite


def netlistReduceExplicitSyncMergeSuccessorIsland(
        dbgTracer: DebugTracer,
        coreNode: HlsNetNodeIoClusterCore,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        reachDb: HlsNetlistAnalysisPassReachabilility,
        threads: HlsNetlistAnalysisPassDataThreads):
    """
    While merging HlsNetNodeExplicitSync nodes it is required to check all sync nodes which are related
    to inputs and outputs of this sync. This means that it is required to search reachability in bout directions,
    when searching for related sync nodes.
    """
    assert isinstance(coreNode, HlsNetNodeIoClusterCore), coreNode
    inputs = [dep.obj for dep in coreNode.usedBy[coreNode.inputNodePort.out_i]]
    outputs = [dep.obj for dep in coreNode.usedBy[coreNode.outputNodePort.out_i]]
    iCnt = len(inputs)
    oCnt = len(outputs)
    modified = False
    for n in chain(inputs, outputs):
        if n.__class__ is HlsNetNodeExplicitSync:
            if n not in removed:
                continue
            if netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite(dbgTracer, n, worklist, removed, reachDb):
                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                # HlsNetlistPassConsystencyCheck().apply(None, _n.netlist, removed=removed)
                modified = True
            elif netlistHoistExplicitSync(dbgTracer, n, worklist, removed, reachDb):
                dbgTracer.log(("hoist", n._id))
                modified = True

    if modified:
        worklist.extend(inputs)
        worklist.extend(outputs)
        worklist.append(coreNode)
        return modified

    with dbgTracer.scoped(netlistReduceExplicitSyncMergeSuccessorIsland, coreNode):
        # print("netlistReduceExplicitSyncMergeSuccessorIsland", n, iCnt, oCnt, sorted([n._id for n in inputs]),
        #                    sorted([n._id for n in outputs]))
        if iCnt == 0 and oCnt == 0:
            removed.add(coreNode)
            return True
        elif iCnt == 1 and oCnt == 0:
            return False  # nothing to optimize
        elif iCnt == 0 and oCnt == 1:
            return False  # nothing to optimize
        elif iCnt == 1 and oCnt == 1:
            # a sequence of sync
            src = inputs[0]
            dst = outputs[0]
            if src is dst:
                return False  # case where this node is input and output together

            # if threads.threadPerNode[src] is not threads.threadPerNode[dst]:
            #    # can not sink or hoist because there is no data dependency which would 
            #    # assert that the circuit would behave the same once the sync flag is moved
            #    # up or down in the circuit
            #    return False
    
            # dst control or ordering depends as well on src
            controlDependsOnSrc = False
            for i, dep in zip(dst._inputs, dst.dependsOn):
                dst: HlsNetNodeExplicitSync
                if i.in_i != 0:
                    depObj = dep.obj
                    controlDependsOnSrc |= depObj is src or\
                        reachDb.doesReachTo(src, depObj)
    
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
                    #    netlistReduceExplicitSyncUseless(src, worklist, removed, reachDb)
                    # else:
                    worklist.append(src)
                    worklist.append(dst)
                    worklist.append(coreNode)
                    return True
            else:
                # hoist control
                if (dst.__class__ is HlsNetNodeExplicitSync or hasNoSkipWhen) and (dst.extraCond is not None or dst.skipWhen is not None):
                    # transfer from successor to this to optimize final extraCond and skipWhen flags
                    # which are controlling the channel
                    dbgTracer.log(("hoist control from", dst._id))
                    trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(dst, src)
    
                    worklist.append(src)
                    worklist.append(dst)
                    worklist.append(coreNode)
                    return True
    
        elif iCnt == 1 and oCnt > 1:
            # parallel output sync with a single input
            src = inputs[0]
            outputs = sorted(outputs, key=lambda o: o._id)
            everySucIsSync = all(o.__class__ is HlsNetNodeExplicitSync for o in outputs)
            if everySucIsSync:
                # it may be possible to hoist all outputs to this
                everyFlagHoistable = True
                for o in outputs:
                    for p in (o.skipWhen, o.extraCond):
                        d = _getPortDrive(p)
                        if p is not None and reachDb.doesReachTo(src, d):
                            everyFlagHoistable = False
                            break
                        
                if everyFlagHoistable:
                    dbgTracer.log(("hoist control from many and remove sucs", outputs), lambda x: f"{x[0]} {[o._id for o in x[1]]}")
                    extendSyncFlagsFromMultipleParallel(outputs, src, worklist)
                    for o in outputs:
                        removeExplicitSync(o, worklist, removed)
                    worklist.append(src)
                    worklist.append(coreNode)
                    return True
                
            if src.__class__ is HlsNetNodeExplicitSync:
                # :note: can sink because there is no risk that we require some input which may be optional
                if src.skipWhen is None and src.extraCond is None:
                    # nothing to sink
                    dbgTracer.log(("rm", src._id))
                    pass
                else:
                    # sink n flags to every o
                    dbgTracer.log(("sink control to many and remove self", outputs), lambda x: f"{x[0]} {[o._id for o in x[1]]}")
                    for o in outputs:
                        extendSyncFlagsFrom(src, o)
    
                removeExplicitSync(src, worklist, removed)
                worklist.extend(outputs)
                worklist.append(src)
                worklist.append(coreNode)

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
            if outputs[0].__class__ is HlsNetNodeExplicitSync:
                raise NotImplementedError("Try hoist flags from output", inputs, outputs)
                
            return False
    
        elif iCnt > 1 and oCnt > 1:
            # n inputs to m outputs
            # try merge sync with the same sync flags to reduce total number of sync
            # For every output try hoist sync flags as much as possible
            # if any other opt. is not possible, try to hoist this node if it is HlsNetNodeExplicitSync
            for n in inputs:
                if n in removed:
                    continue
                _modified = False
                # :note: inputs/outputs do not need to be disjunct that is why set is used
                if n.__class__ is HlsNetNodeExplicitSync:
                    # it is not possible to hoist any sync, the remaining option is to sink flags from this sync to
                    # connected nodes sync nodes of this island.
                    
                    # All sync flags from every input HlsNetNodeExplicitSync can be moved to every direct data successor of each HlsNetNodeExplicitSync
                    # The move is impossible if some sync flags can not be moved.
                    sucs = tuple(reachDb.getDirectDataSuccessors(n))
                    dbgTracer.log(("sink control to successors and remove self", n._id, sucs),
                                  lambda x: f"{x[0]} {x[1]:d}-> {[o._id for o in x[2]]}")
    
                    for isLast, suc in iter_with_last(sucs):
                        preds = tuple(pred for pred in reachDb.getDirectDataPredecessors(suc)
                                      if pred.__class__ is HlsNetNodeExplicitSync)
                        everyPredIsSync = True
                        for pred in preds:
                            if pred.__class__ is not HlsNetNodeExplicitSync:
                                everyPredIsSync = False
                                break

                        if not everyPredIsSync:
                            raise NotImplementedError()
                        
                        toRm = []
                        if len(preds) > 1:
                            extendSyncFlagsFromMultipleParallel(preds, n, worklist)
                            for pred in preds:
                                predSuccs = tuple(reachDb.getDirectDataSuccessors(suc))
                                if len(predSuccs) == 1:
                                    # [todo] ther may be the case where predecessors are somehov dependent on each other
                                    # and there is some partial ordering betwen them, in this case predSuccs may contain other pred
                                    toRm.append(pred)  
                            
                        else:
                            trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(n, suc, removeFromSrc=isLast)

                        if isLast:
                            toRm.append(n)
                        worklist.append(suc)
    
                        for n1 in toRm:
                            if n1 in removed:
                                continue
                            removeExplicitSync(dbgTracer, n1, worklist, removed)
    
                    _modified = True
                    worklist.extend(inputs)
    
                if _modified:
                    worklist.append(n)
                    worklist.append(coreNode)
                    modified = True
                    break
    
            return modified
    
        elif iCnt == 1 and oCnt == 0:
            # output of some other sync without any successor sync
            src = tuple(inputs)[0]
            if src.__class__ is HlsNetNodeExplicitSync:
                # if not reachDb.hasControlPredecessor(n):
                #    # this does not synchronize anything and it can be removed
                #    raise NotImplementedError(n)
    
                if netlistHoistExplicitSync(dbgTracer, src, worklist, removed, reachDb):
                    dbgTracer.log("hoist tailing self")
                    worklist.append(src)
                    worklist.append(coreNode)
                    return True
                
            return False

        elif iCnt != 0 and oCnt == 0:
            # [todo] converto to outputs if beneficial
            return False

        else:
            raise AssertionError("Unsupported combination of input/output count in IO cluster", iCnt, oCnt)
