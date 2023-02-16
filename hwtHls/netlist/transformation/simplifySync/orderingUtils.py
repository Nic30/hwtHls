from typing import List, Set, Union, Optional

from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isNonData
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick


def _dependsOnNonOrderingData(n: HlsNetNode, inputs: List[HlsNetNode],
        reachDb:HlsNetlistAnalysisPassReachabilility):
    for oOtherInp, dep in zip(n._inputs, n.dependsOn):
        oOtherInp: HlsNetNodeIn
        dep: HlsNetNodeOut
        if HdlType_isNonData(dep._dtype):
            continue
        for inpNode in inputs:
            if reachDb.doesReachTo(inpNode, dep):
                return True

    return False


def _searchOrderingLinksOnlyDFS(src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync):
    seen: Set[Union[HlsNetNodeExplicitSync, HlsNetNodeIoClusterCore]] = set()
    toSearch: List[Union[HlsNetNodeExplicitSync, HlsNetNodeIoClusterCore]] = [dst]
    while toSearch:
        n = toSearch.pop()
        if n in seen:
            continue
        seen.add(n)
        if isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeIoClusterCore)):
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
        reachDb:HlsNetlistAnalysisPassReachabilility):
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