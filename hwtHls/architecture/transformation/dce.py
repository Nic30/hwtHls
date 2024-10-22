from itertools import chain
from typing import Sequence, Optional

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx, \
    ArchSyncNodeTerm


def HlsNetNodeAggregate_allSubNodesRemoved(elm: HlsNetNodeAggregate):
    return not elm.subNodes or (len(elm.subNodes) >= len(elm.builder._removedNodes) and all(n._isMarkedRemoved for n in elm.subNodes))


def HlsNetNodeAggregateDCE(elm: HlsNetNodeAggregate, worklist: SetList[HlsNetNode],
                           termPropagationCtx: Optional[ArchElementTermPropagationCtx]):
    clkPeriod = elm.netlist.normalizedClkPeriod
    change = False
    outsToRm = []
    for o, oInside, users in zip(elm._outputs, elm._outputsInside, elm.usedBy):
        o: HlsNetNodeOut
        oInside: HlsNetNodeAggregatePortOut
        if oInside._isMarkedRemoved:
            continue
        users: Sequence[HlsNetNodeIn]
        depInside = oInside.dependsOn[0]
        assert depInside is not None

        if not users:
            if termPropagationCtx is not None:
                k = ArchSyncNodeTerm((elm, oInside.scheduledZero // clkPeriod), depInside, None)
                termPropagationCtx.exportedPorts.pop(k, None)

            worklist.append(depInside.obj)
            oInside._inputs[0].disconnectFromHlsOut(depInside)
            oInside.markAsRemoved()
            change = True
            outsToRm.append(o)
        elif isinstance(depInside.obj, HlsNetNodeConst):
            # propagate constant to user arch elements
            srcConstNode: HlsNetNodeConst = depInside.obj
            clkPeriod = elm.netlist.normalizedClkPeriod
            for u in users:
                uNode = u.obj
                assert isinstance(uNode, ArchElement), u
                uInsideInp: HlsNetNodeAggregatePortIn = uNode._inputsInside[u.in_i]
                replacement = uNode.builder.buildConst(srcConstNode.val, srcConstNode.name)
                replacement.obj.resolveRealization()
                replacement.obj._setScheduleZeroTimeSingleClock(uInsideInp.scheduledZero)
                uNode._addNodeIntoScheduled(uInsideInp.scheduledZero // clkPeriod, replacement.obj)
                addAllUsersToWorklist(worklist, uInsideInp)
                uNode.builder.replaceOutput(uInsideInp._outputs[0], replacement, True, False)
                worklist.append(uNode)
    insToRm = []
    for i, iInside, dep in zip(elm._inputs, elm._inputsInside, elm.dependsOn):
        i: HlsNetNodeIn
        iInside: HlsNetNodeAggregatePortIn
        dep: HlsNetNodeOut
        if iInside._isMarkedRemoved:
            continue
        if not iInside.usedBy[0]:
            if termPropagationCtx is not None:
                k = ArchSyncNodeTerm((elm, iInside.scheduledZero // clkPeriod), dep, None)
                termPropagationCtx.importedPorts.pop(k, None)

            worklist.append(dep.obj)
            i.disconnectFromHlsOut(dep)
            iInside.markAsRemoved()
            change = True
            insToRm.append(i)

    if HlsNetNodeAggregate_allSubNodesRemoved(elm):
        # :note: element is lily to stay even if empty because internal nodes may be removed later
        for n in chain(outsToRm, insToRm):
            n.markAsRemoved()

        elm.markAsRemoved()
        return True

    for o in outsToRm:
        elm._removeOutput(o.out_i)

    for i in insToRm:
        elm._removeInput(i.in_i)

    return change


def ArchElementDCE(netlist:HlsNetlistCtx, archElements: SetList[ArchElement], termPropagationCtx: Optional[ArchElementTermPropagationCtx]):
    if not archElements:
        return
    # assert not removed, ("Should be already filtered before calling this", removed)
    simplify = HlsNetlistPassSimplify(None)

    worklist: SetList[HlsNetNode] = SetList(archElements)  # worklist is used as LIFO, archElements are processed last
    for elm in archElements:
        worklist.extend(elm.subNodes)
    while worklist:
        elm = worklist.pop()
        if isinstance(elm, ArchElement):
            if elm._isMarkedRemoved:
                continue
            if HlsNetNodeAggregateDCE(elm, worklist, termPropagationCtx):
                continue

        elif elm is not netlist:
            n: HlsNetNode = elm
            if n._isMarkedRemoved:
                continue

            if simplify._DCE(n, worklist, termPropagationCtx):
                continue

    netlist.filterNodesUsingRemovedSet(recursive=True)
    # handle empty arch elements
    for elm in archElements:
        if elm is not netlist and elm._isMarkedRemoved:
            continue
        if HlsNetNodeAggregate_allSubNodesRemoved(elm):
            elm.markAsRemoved()

    netlist.filterNodesUsingRemovedSet(recursive=False)
