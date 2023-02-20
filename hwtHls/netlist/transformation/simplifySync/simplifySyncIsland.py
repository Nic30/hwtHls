"""ore
In general the transformation of an HlsNetNodeExplicitSync instances has to take in account
every first connected sync instances.
This is required because HlsNetNodeExplicitSync is kind of gate and when analyzing the flow through
the gate we have to analyze all possible ways which leads to the gate.
"""

from itertools import chain
from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_node_input_if_exists_with_worklist
from hwtHls.netlist.transformation.simplifySync.simplifyExplicitSync import netlistReduceExplicitSyncWithoutInput, \
    extendSyncFlagsFromMultipleParallel, _getPortDrive
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite
from hwtHls.netlist.transformation.simplifySync.simplifySyncUtils import removeExplicitSync


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
    modified = False
    
    anySync = False
    for n in chain(inputs, outputs):
        if n.__class__ is HlsNetNodeExplicitSync:
            if n in removed:
                continue
            
            anySync = True
            if netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite(dbgTracer, n, worklist, removed, reachDb):
                HlsNetlistPassConsystencyCheck._checkCycleFree(n.netlist, removed)
                # HlsNetlistPassConsystencyCheck().apply(None, _n.netlist, removed=removed)
                modified = True
            elif netlistReduceExplicitSyncWithoutInput(dbgTracer, n, worklist, removed, reachDb):
                dbgTracer.log(("hoist", n._id))
                modified = True

    if modified:
        worklist.extend(inputs)
        worklist.extend(outputs)
        worklist.append(coreNode)
        return modified
    elif not anySync:
        return modified

    with dbgTracer.scoped(netlistReduceExplicitSyncMergeSuccessorIsland, coreNode):
        # print("netlistReduceExplicitSyncMergeSuccessorIsland", n, iCnt, oCnt, sorted([n._id for n in inputs]),
        #                    sorted([n._id for n in outputs]))
        # for each output check if it is possible to hoist it
        # for each input check if all its inputs are hoistable
        # the goal is to remove as much of HlsNetNodeExplicitSync instances as possible
        # care must be taken for input/outut which have multiple dependencies
        # because paralell paths do specify a split or join of synchronization graph
        
        # If the HlsNetNodeExplicitSync is removed its dependencies can not be simply removed
        # instead each input must be connected to each output of the HlsNetNodeExplicitSync instance.
        
        # There is also a specific case of where the flag can be hoisted to some input but no
        # to others this leads to a case where HlsNetNodeExplicitSync isntance is disconneced
        # from input/output but must remain there for other IO.
        
        # This leads to a need to modify the HlsNetNodeIoCore node. Depending on combination of removing
        # and keeping of IO and links / may spot or merge HlsNetNodeIoCore instances.
        
        # 
        seenInputs: UniqList[HlsNetNodeExplicitSync] = UniqList()
        hoistableTo = {}
        for io in chain(inputs, outputs):
            assert io not in removed, io
            if io.__class__ is not HlsNetNodeExplicitSync:
                continue
            
            syncFlags = tuple(_getPortDrive(p) for p in (io.skipWhen, io.extraCond))
            for src in reachDb.getDirectDataPredecessors(io):
                seenInputs.append(src)

                isHoistable = True
                for sf in syncFlags:
                    if sf is None:
                        continue
                    sf: HlsNetNodeOut
                    if reachDb.doesReachTo(src, sf):
                        isHoistable = False
                        break

                _hoistableTo = hoistableTo.get(io, None)
                if _hoistableTo is None:
                    _hoistableTo = hoistableTo[io] = []
                if isHoistable:
                    _hoistableTo.append(src)
    
        for i in seenInputs:
            assert i not in removed, i
            allSuccHoistable = True
            anySyncToRm = False
            sucs = tuple(reachDb.getDirectDataSuccessors(i))
            for o in sucs:
                if o.__class__ is HlsNetNodeExplicitSync:
                    anySyncToRm = True
                assert o in hoistableTo, (o, "must have ben seen because it is how ", i, "was discovered")
                if i not in hoistableTo[o]:
                    allSuccHoistable = False
            
            if anySyncToRm and allSuccHoistable:
                dbgTracer.log((sucs, i), lambda x: f"hoist control from many {[o._id for o in x[0]]} to {x[1]._id}")
                extendSyncFlagsFromMultipleParallel(sucs, i, worklist)
                for o in sucs:
                    if o.__class__ is HlsNetNodeExplicitSync:
                        # [todo] only if hoisted to every predecessor
                        unlink_hls_node_input_if_exists_with_worklist(o.skipWhen, worklist, True)
                        unlink_hls_node_input_if_exists_with_worklist(o.extraCond, worklist, True)
                modified = True
                # for o in outputs:
                #    removeExplicitSync(o, worklist, removed)
                # worklist.append(src)
                # worklist.append(coreNode)
                
        return modified 
