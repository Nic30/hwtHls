from typing import Set, Optional

from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.node import HlsNetNode


def iterUsersIgnoringHierarchy(o: HlsNetNodeOut, seen:Set[HlsNetNodeIn]):
    for u in o.obj.usedBy[o.out_i]:
        if u in seen:
            continue
        seen.add(u)
        if isinstance(u.obj, HlsNetNodeAggregatePortOut):
            # move outside of aggregate
            yield from iterUsersIgnoringHierarchy(u.obj.parentOut, seen)
        elif isinstance(u.obj, HlsNetNodeAggregate):
            # move inside of aggregate
            yield from iterUsersIgnoringHierarchy(u.obj._inputsInside[u.in_i]._outputs[0], seen)
        else:
            yield u


def removeInputIgnoringHierarchy(in_:HlsNetNodeIn, worklist: Optional[SetList[HlsNetNode]]):
    if isinstance(in_.obj, HlsNetNodeAggregatePortOut):
        # move outside of aggregate
        parentOut: HlsNetNodeAggregate = in_.obj.parentOut
        uses = parentOut.obj.usedBy[parentOut.out_i]
        oToRm = parentOut

    elif isinstance(in_.obj, HlsNetNodeAggregate):
        # move inside of aggregate
        childIn: HlsNetNodeAggregatePortIn = in_.obj._inputsInside[in_.in_i]
        uses = childIn.usedBy[0]
        oToRm = None
    else:
        uses = None
        oToRm = None

    if uses is not None:
        for u in uses:
            u.obj.dependsOn[u.in_i] = None
            removeInputIgnoringHierarchy(u, worklist)
        uses.clear()

    if oToRm is None:
        in_.obj._removeInput(in_.in_i)
        if worklist is not None:
            worklist.append(in_.obj)
    else:
        oToRm.obj._removeOutput(oToRm.out_i)
