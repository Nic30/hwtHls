from typing import Set, Optional

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, unlink_hls_node_input_if_exists
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain


def netlistContainsExplicitSync(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
    for n in netlist.nodes:
        if n.__class__ is HlsNetNodeExplicitSync and not (removed is not None and n in removed):
            return True
    return False


def removeExplicitSync(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    for dep in n.dependsOn:
        worklist.append(dep.obj)
    for uses in n.usedBy:
        for u in uses:
            worklist.append(u.obj)

    dataIn = n.dependsOn[0]
    netlistExplicitSyncDisconnectFromOrderingChain(n)
    assert len(n._outputs) == 2, ("data, ordering")
    unlink_hls_nodes(dataIn, n._inputs[0])
    b: HlsNetlistBuilder = n.netlist.builder
    b.replaceOutput(n._outputs[0], dataIn, True)
    unlink_hls_node_input_if_exists(n.skipWhen)
    unlink_hls_node_input_if_exists(n.extraCond)

    removed.add(n)
    

def trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(
        src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync,
        removeFromSrc=True):

    # reconnect the flag, possibly merge using appropriate logical function and update syncDeps
    if src.extraCond is not None:
        ec = src.dependsOn[src.extraCond.in_i]
        if removeFromSrc:
            unlink_hls_nodes(ec, src.extraCond)
        dst.addControlSerialExtraCond(ec)
        if removeFromSrc:
            src._removeInput(src.extraCond.in_i)
            src.extraCond = None
        
    if src.skipWhen is not None:
        sw = src.dependsOn[src.skipWhen.in_i]
        if removeFromSrc:
            unlink_hls_nodes(sw, src.skipWhen)
        dst.addControlSerialSkipWhen(sw)
        if removeFromSrc:
            src._removeInput(src.skipWhen.in_i)
            src.skipWhen = None
