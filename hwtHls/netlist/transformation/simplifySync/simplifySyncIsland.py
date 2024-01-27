"""
In general the transformation of an HlsNetNodeExplicitSync instances has to take in account
every first connected sync instances.
This is required because HlsNetNodeExplicitSync is kind of gate and when analyzing the flow through
the gate we have to analyze all possible ways which leads to the gate.
"""

from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_nodes, link_hls_nodes
from hwtHls.netlist.transformation.simplifySync.simplifyExplicitSync import netlistReduceExplicitSyncWithoutInput, \
    extendSyncFlagsFromMultipleParallel, _getPortDrive
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite
from hwtHls.netlist.transformation.simplifySync.simplifySyncUtils import removeExplicitSync


def _analyzeHoistabilityOfSyncFlags(outNode: HlsNetNodeExplicitSync,
                                    reachDb: HlsNetlistAnalysisPassReachability):
    seenInputs: UniqList[HlsNetNodeExplicitSync] = UniqList()
    seenOutputs: UniqList[HlsNetNodeExplicitSync] = UniqList()
    hoistableTo = {}

    inputsToAnalyze = []
    inputsToAnalyze.extend(reachDb.getDirectDataPredecessors(outNode))
    outputsToAnalyze = [outNode]
    while inputsToAnalyze or outputsToAnalyze:
        if inputsToAnalyze:
            src = inputsToAnalyze.pop()
            if src in seenInputs:
                continue
            else:
                seenInputs.append(src)

            for dst in reachDb.getDirectDataSuccessors(src):
                inputsToAnalyze.extend(reachDb.getDirectDataPredecessors(dst))

        if outputsToAnalyze:
            dst = outputsToAnalyze.pop()
            if dst in seenOutputs:
                continue
            else:
                seenOutputs.append(dst)

            syncFlags = tuple(_getPortDrive(p) for p in (dst.skipWhen, dst.extraCond))
            for src in reachDb.getDirectDataPredecessors(dst):
                isHoistable = True
                for syncFlag in syncFlags:
                    if syncFlag is None:
                        continue
                    syncFlag: HlsNetNodeOut
                    if reachDb.doesReachTo(src, syncFlag):
                        # the value of the sync flag depends on src node itself
                        isHoistable = False
                        break

                _hoistableTo = hoistableTo.get(dst, None)
                if _hoistableTo is None:
                    _hoistableTo = hoistableTo[dst] = []
                if isHoistable:
                    _hoistableTo.append(src)

                outputsToAnalyze.extend(reachDb.getDirectDataSuccessors(src))

    return hoistableTo, seenInputs, seenOutputs


dbgCntr = 0


def netlistReduceExplicitSyncDissolve(
        dbgTracer: DebugTracer,
        node: HlsNetNodeExplicitSync,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode],
        reachDb: HlsNetlistAnalysisPassReachability):
    """
    While merging HlsNetNodeExplicitSync nodes it is required to check all sync nodes which are related
    to inputs and outputs of this sync. This means that it is required to search reachability in bout directions,
    when searching for related sync nodes.
    """
    assert node.__class__ is HlsNetNodeExplicitSync, node
    if netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite(dbgTracer, node, worklist, removed, reachDb):
        HlsNetlistPassConsystencyCheck._checkCycleFree(node.netlist, removed)
        # HlsNetlistPassConsystencyCheck().apply(None, _n.netlist, removed=removed)
        return True
    elif netlistReduceExplicitSyncWithoutInput(dbgTracer, node, worklist, removed, reachDb):
        return True

    with dbgTracer.scoped(netlistReduceExplicitSyncDissolve, node):
        # for each output check if it is possible to hoist it
        # for each input check if all its inputs are hoistable
        # the goal is to remove as much of HlsNetNodeExplicitSync instances as possible
        # care must be taken for input/outut which have multiple dependencies
        # because parallel paths do specify a split or join of synchronization graph

        # If the HlsNetNodeExplicitSync is removed its dependencies can not be simply removed
        # instead each input must be connected to each output of the HlsNetNodeExplicitSync instance.

        # There is also a specific case of where the flag can be hoisted to some input but no
        # to others this leads to a case where HlsNetNodeExplicitSync instance is disconnected
        # from input/output but must remain there for other IO.

        # This leads to a need to modify the HlsNetNodeIoCore node. Depending on combination of removing
        # and keeping of IO and links / may spot or merge HlsNetNodeIoCore instances.

        # syncNode can be removed if it can be hoisted to every predecessor
        # syncNode can be hoisted to predecessor only if every successor of every predecessor can be hoisted
        b: HlsNetlistBuilder = node.netlist.builder

        hoistableTo, seenInputs, seenOutputs = _analyzeHoistabilityOfSyncFlags(node, reachDb)
        # print("netlistReduceExplicitSyncDissolve", [i._id for i in seenInputs], [o._id for o in seenOutputs])
        # global dbgCntr
        # dbgTracer.log(f"dbg {dbgCntr:d}")
        # HlsNetlistPassDumpNodesDot(outputFileGetter("tmp", f"dbg.{dbgCntr}.dot")).apply(None, node.netlist)
        # dbgCntr += 1

        modified = False
        for i in seenInputs:
            if i in removed:
                continue
            allSuccHoistable = True
            anySyncToRm = False
            sucs = tuple(reachDb.getDirectDataSuccessors(i))
            for o in sucs:
                if o.__class__ is HlsNetNodeExplicitSync:
                    anySyncToRm = True
                assert o in hoistableTo, (o, "must have been seen because it is how ", i, "was discovered")
                if i not in hoistableTo[o]:
                    allSuccHoistable = False

            if anySyncToRm and allSuccHoistable:
                dbgTracer.log((sucs, i), lambda x: f"hoist control from {[o._id for o in x[0]]} to {x[1]._id:d}")
                extendSyncFlagsFromMultipleParallel(sucs, i, worklist)
                for outNode in sucs:
                    if outNode.__class__ is HlsNetNodeExplicitSync:
                        # [todo] only if hoisted to every predecessor
                        # disconnect void data channels from outNode and connect them to all successors of outNode
                        iVoid = i.getDataVoidOutPort()
                        successors: UniqList[HlsNetNodeExplicitSync] = UniqList()

                        for u in i.usedBy[iVoid.out_i]:
                            if u.obj is outNode:
                                # :note: there should be only a single direct connection
                                uObj: HlsNetNodeExplicitSync = u.obj
                                unlink_hls_nodes(iVoid, u)
                                uIVoid = uObj.getDataVoidOutPort()
                                successors.extend(uu.obj for uu in uObj.usedBy[uIVoid.out_i])

                                hasNoVoidDataPredecs = True
                                for dep in uObj.dependsOn:
                                    if dep is not None and dep._dtype == HVoidData:
                                        hasNoVoidDataPredecs = False
                                        break

                                if hasNoVoidDataPredecs:
                                    # remove because all predecessors were reconnected to successors of uObj
                                    uObjDvo = uObj.getDataVoidOutPort()
                                    for dvoUse in tuple(uObj.usedBy[uObjDvo.out_i]):
                                        unlink_hls_nodes(uObjDvo, dvoUse)
                                        if dvoUse.obj.__class__ is HlsNetNodeExplicitSync and dvoUse.in_i == 0:
                                            v = b.buildConstPy(HVoidData, None)
                                            link_hls_nodes(v, dvoUse)
                                        else:
                                            dvoUse.obj._removeInput(dvoUse.in_i)
                                        worklist.append(dvoUse.obj)

                                    removeExplicitSync(dbgTracer, uObj, worklist, removed)

                                break

                        if successors:
                            currSuccessors = set()
                            for u in i.usedBy[iVoid.out_i]:
                                currSuccessors.add(u.obj)
                            for suc in successors:
                                if suc not in currSuccessors:
                                    link_hls_nodes(iVoid, suc._addInput("dataVoidIn"))
                                    worklist.append(suc)
                modified = True
            # elif len(seenInputs) == 1 and len(seenOutputs) > 1 and all(o.__class__ is HlsNetNodeExplicitSync and o.dependsOn[0].obj is seenInputs[0] for o in seenOutputs):
            #    i = seenInputs[0]
            #    dbgTracer.log((i, seenOutputs), lambda x: f"merge parallel outputs of {x[0]._id:d} {[o._id for o in x[1]]}")
            #    dstO: HlsNetNodeExplicitSync = seenOutputs[0]
            #    ec, sw = mergeSyncFlagsFromMultipleParallel(seenOutputs, worklist)
            #    for syncFlag in (dstO.extraCond, dstO.skipWhen):
            #        if syncFlag is not None:
            #            unlink_hls_nodes(dstO.dependsOn[syncFlag.in_i], syncFlag)
            #            dstO._removeInput(syncFlag.in_i)
            #
            #    if ec is not None:
            #        dstO.addControlSerialExtraCond(ec)
            #    if sw is not None:
            #        dstO.addControlSerialSkipWhen(sw)
            #
            #    newO = dstO._outputs[0]
            #    for otherO in islice(seenOutputs, 1, None):
            #        otherO: HlsNetNodeExplicitSync
            #        assert len(otherO._outputs) == 1
            #        replaceOperatorNodeWith(otherO, newO, worklist, removed)
            #
            #    worklist.append(i)
            #    worklist.append(dstO)
            #    modified = True

            # for o in outputs:
            #    removeExplicitSync(o, worklist, removed)
            # worklist.append(src)
            # worklist.append(coreNode)
    # for o in outputs:
    # if completlyHoisted(o):
    #    unlink_hls_node_input_if_exists_with_worklist(o.skipWhen, worklist, True)
    #    unlink_hls_node_input_if_exists_with_worklist(o.extraCond, worklist, True)

        return modified
