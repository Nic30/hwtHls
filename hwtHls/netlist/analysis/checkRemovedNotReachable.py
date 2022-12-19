from typing import Set

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode


def checkRemovedNotReachable(netlist: HlsNetlistCtx, removed: Set[HlsNetNode]):
    """
    Check that removed nodes are not reachable from non removed nodes.
    """
    allNodes = set(netlist.iterAllNodes())
    for n in netlist.iterAllNodes():
        n: HlsNetNode
        if n in removed:
            continue
        for dep in n.dependsOn:
            assert dep is not None, n
            assert dep.obj in allNodes, (n, dep)
            assert dep.obj not in removed, (n, dep)
        for users in n.usedBy:
            for u in users:
                assert u.obj in allNodes, (n, u)
                assert u.obj not in removed, (n, u)
