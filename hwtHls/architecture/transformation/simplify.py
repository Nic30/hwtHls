from typing import Union, Optional

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.transformation.dce import ArchElementDCE, \
    HlsNetNodeAggregateDCE
from hwtHls.architecture.transformation.rehash import _ExprRehasherClockWindowOnly
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.transformation.simplifySync.simplifyNonBlockingIo import netlistReduceExplicitSyncFlags
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import disconnectAllInputs
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchElementTermPropagationCtx


def netlistReduceAggregatePortOut(n: HlsNetNodeAggregatePortOut,
                                  worklist: SetList[HlsNetNode]):
    dep = n.dependsOn[0]
    clkPeriod = n.netlist.normalizedClkPeriod
    nClkI = n.scheduledIn[0] // clkPeriod
    depN = dep.obj
    if nClkI == depN.scheduledOut[dep.out_i] and isinstance(depN, HlsNetNodeAggregatePortIn):
        # AggregatePortIn -> AggregatePortOut case
        depN: HlsNetNodeAggregatePortIn
        depDep = depN.parent.dependsOn[depN.parentIn.in_i]
        depDepTime = depDep.obj.scheduledOut[depDep.out_i]
        changed = False
        parentOut = n.parentOut
        for u in parentOut.obj.usedBy[parentOut.out_i]:
            u: HlsNetNodeIn  # the input port of other HlsNetNodeAggregate

            # if any use of this out (n) can be replaced with an use of
            # out which is driving this out (depDep)

            uNode = u.obj
            useTime = uNode.scheduledIn[u.in_i]
            if depDepTime > useTime:
                raise NotImplementedError(n, depDep, u)
                # optionally move user HlsNetNodeAggregatePortIn to later time if its users and clock window allows it
            else:
                if uNode is depDep.obj and\
                        isinstance(uNode, HlsNetNodeAggregate) and\
                        useTime // clkPeriod == depDepTime // clkPeriod:
                    # case where we do not have to use HlsNetNodeAggregatePort at all and can connect things directly
                    uInside = uNode._inputsInside[u.in_i]
                    builder: HlsNetlistBuilder = uInside.getHlsNetlistBuilder()
                    # HlsNetNodeOut which drives the  HlsNetNodeAggregatePortOut which drives this n
                    depDepDep = uNode._outputsInside[depDep.out_i].dependsOn[0]
                    addAllUsersToWorklist(worklist, uInside)
                    assert uInside._outputs[0] is not depDepDep, ("Self loop on port", depDepDep)
                    builder.replaceOutput(uInside._outputs[0], depDepDep, True)
                    worklist.append(uInside)  # for DCE
                else:
                    u.replaceDriver(depDep)
                    worklist.append(u.obj)

                changed = True

        if not parentOut.obj.usedBy[parentOut.out_i]:
            worklist.append(parentOut.obj)  # for DCE
            return True
        return changed

    return False


def ArchElementValuePropagation(dbgTracer: DebugTracer,
                                modifiedElements: SetList[Union[HlsNetNodeAggregate, HlsNetlistCtx]],
                                worklist: SetList[HlsNetNode],
                                termPropagationCtx: Optional[ArchElementTermPropagationCtx]):
    if modifiedElements:
        elm0 = modifiedElements[0]
        if isinstance(elm0, HlsNetlistCtx):
            netlist = elm0
        else:
            netlist = elm0.netlist
    elif worklist:
        netlist = worklist[0].netlist
    else:
        return

    ArchElementDCE(netlist, modifiedElements, termPropagationCtx)  # to remove unscheduled unused nodes
    _ExprRehasherClockWindowOnly.rehashNodesInElements(worklist, modifiedElements)

    while worklist:
        _modifiedElements:SetList[Union[HlsNetNodeAggregate, HlsNetlistCtx]] = SetList()
        while worklist:
            n: HlsNetNodeOut = worklist.pop()
            if n._isMarkedRemoved:
                continue

            builder = n.getHlsNetlistBuilder()
            if isinstance(n, HlsNetNodeOperator):
                if HlsNetlistPassSimplify._isTriviallyDead(n):
                    builder.unregisterNode(n)
                    disconnectAllInputs(n, worklist)
                    n.markAsRemoved()
                    continue
                else:
                    elm = n.parent
                    if HlsNetlistPassSimplify._simplifyHlsNetNodeOperator(n, worklist):
                        _modifiedElements.append(elm)
                        continue

            elif isinstance(n, HlsNetNodeExplicitSync):
                elm = n.parent
                if netlistReduceExplicitSyncFlags(dbgTracer, n, worklist):
                    _modifiedElements.append(elm)
                    continue

            elif isinstance(n, HlsNetNodeConst):
                if HlsNetlistPassSimplify._isTriviallyDead(n):
                    builder.unregisterNode(n)
                    disconnectAllInputs(n, worklist)
                    n.markAsRemoved()
                    continue

            elif isinstance(n, HlsNetNodeAggregatePortOut):
                if netlistReduceAggregatePortOut(n, worklist):
                    continue

            elif isinstance(n, HlsNetNodeAggregatePortIn):
                if not n.usedBy[0]:
                    worklist.append(n.parent)
                    continue
            elif isinstance(n, HlsNetNodeAggregate):
                if HlsNetNodeAggregateDCE(n, worklist, termPropagationCtx):
                    continue

        _ExprRehasherClockWindowOnly.rehashNodesInElements(worklist, _modifiedElements)

        modifiedElements.extend(_modifiedElements)
