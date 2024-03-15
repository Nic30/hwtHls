from typing import List, Set, Optional

from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes


def _dependsOnNonOrderingData(n: HlsNetNode, inputs: List[HlsNetNode],
        reachDb:HlsNetlistAnalysisPassReachability):
    for dep in n.dependsOn:
        dep: HlsNetNodeOut
        if HdlType_isNonData(dep._dtype):
            continue
        for inpNode in inputs:
            if reachDb.doesReachTo(inpNode, dep):
                return True

    return False


def _searchOrderingLinksOnlyDFS(src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync):
    seen: Set[HlsNetNodeExplicitSync] = set()
    toSearch: List[HlsNetNodeExplicitSync] = [dst]
    while toSearch:
        n = toSearch.pop()
        if n in seen:
            continue
        seen.add(n)
        if isinstance(n, HlsNetNodeExplicitSync):
            inputs = n.iterOrderingInputs()

        elif isinstance(n, HlsNetNodeDelayClkTick):
            assert HdlType_isNonData(n._outputs[0]._dtype), n
            inputs = n._inputs
        else:
            raise NotImplementedError(n)

        for i in inputs:
            dep = n.dependsOn[i.in_i]
            if dep is None:
                continue
            elif dep.obj is src:
                return True
            else:
                toSearch.append(dep.obj)

    return False


def addOrderingIfRequired(src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync, dstPort: Optional[HlsNetNodeIn],
        reachDb:HlsNetlistAnalysisPassReachability):
    """
    Add ordering connection if there dst is not transitively reachable from src.
    """
    if reachDb.doesReachTo(src, dst) and _searchOrderingLinksOnlyDFS(src, dst):
        return False

    if dstPort is None:
        _i = dst._addInput("orderingIn")
    else:
        _i = dstPort
    link_hls_nodes(src.getOrderingOutPort(), _i)
    return True
