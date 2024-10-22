from itertools import islice

from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUncheduledDummyAlap


def replaceOperatorNodeWith(n: HlsNetNodeOperator,
                            newO: HlsNetNodeOut,
                            worklist: SetList[HlsNetNode]):
    assert len(n.usedBy) == 1 or all(not uses for uses in islice(n.usedBy, 1, None)), (
        n, "implemented only for single output nodes or nodes with only first output used")
    assert not newO.obj._isMarkedRemoved, newO
    assert n._outputs[0] is not newO,  ("It is pointless to replace to the same", newO)
    oldTy = n._outputs[0]._dtype
    newTy = newO._dtype
    assert oldTy == newO._dtype or (isinstance(oldTy, HBits) and
                                    isinstance(newTy, HBits) and
                                    oldTy.bit_length() == newTy.bit_length()
                                    ), (oldTy, newO._dtype)
    builder: "HlsNetlistBuilder" = n.getHlsNetlistBuilder()
    addAllUsersToWorklist(worklist, n)

    # add dependencies which do not have any other use to worklist
    for dep in n.dependsOn:
        hasAnyOtherUser = False
        for u in dep.obj.usedBy[dep.out_i]:
            if u.obj is not n:
                hasAnyOtherUser = True
                break
        if not hasAnyOtherUser:
            worklist.append(dep.obj)

    builder.replaceOutput(n._outputs[0], newO, True)
    disconnectAllInputs(n, worklist)
    if n.scheduledOut is not None:
        scheduleUncheduledDummyAlap(newO, n.scheduledOut[0])
    n.markAsRemoved()
    


def iterAllHierachies(netlist: HlsNetlistCtx, postOrder=True):
    for p, _ in netlist.iterNodesFlatWithParentByType(HlsNetNodeAggregate, postOrder):
        yield p


def disconnectAllInputs(n: HlsNetNode, worklist: SetList[HlsNetNode]):
    for i, dep in zip(n._inputs, n.dependsOn):
        i: HlsNetNodeIn
        dep: HlsNetNodeOut
        assert dep is not None, ("The input must not be already disconnected", i, ", this is to check that disconnect is called just once")

        # disconnect driver from self
        dep.obj.usedBy[dep.out_i].remove(i)
        worklist.append(dep.obj)
        n.dependsOn[i.in_i] = None

    if isinstance(n, HlsNetNodeAggregatePortIn):
        i: HlsNetNodeIn = n.parentIn
        dep: HlsNetNodeOut = i.obj.dependsOn[i.in_i]
        # disconnect driver from self
        dep.obj.usedBy[dep.out_i].remove(i)
        worklist.append(dep.obj)
        i.obj.dependsOn[i.in_i] = None

