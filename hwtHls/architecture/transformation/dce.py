from typing import List

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplify import HlsNetlistPassSimplify
from hwtHls.netlist.transformation.simplifyUtils import disconnectAllInputs


def ArchElementDCE(netlist:HlsNetlistCtx, sccSyncArchElements: List[ArchElement]):
    removed = netlist.builder._removedNodes
    assert not removed, ("Should be already filtered before calling this", removed)
    simplify = HlsNetlistPassSimplify(None)

    worklist: UniqList[HlsNetNode] = UniqList()
    for elm in sccSyncArchElements:
        anyNodeRemoved = False
        for n in elm._subNodes:
            anyNodeRemoved |= simplify._DCE(n, worklist, removed)
        while worklist:
            n = worklist.pop()
            simplify._DCE(n, worklist, removed)
        if anyNodeRemoved:
            elm.filterNodesUsingSet(removed)

    # prune unused outputs on all elements
    toRm = []
    for elm in netlist.nodes:
        elm: ArchElement
        for o, oInside, uses in zip(elm._outputs, elm._outputsInside, elm.usedBy):
            if not uses:
                disconnectAllInputs(oInside, worklist)
                toRm.append(o)
        if toRm:
            for o in reversed(toRm):
                elm._removeOutput(o.out_i)
            
            toRm.clear()
            anyNodeRemoved = False
            while worklist:
                n = worklist.pop()
                anyNodeRemoved |= simplify._DCE(n, worklist, removed)

            if anyNodeRemoved:
                elm.filterNodesUsingSet(removed)
