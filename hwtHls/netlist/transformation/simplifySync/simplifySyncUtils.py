from itertools import islice
from typing import Set, Optional

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, unlink_hls_node_input_if_exists
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain


def netlistContainsExplicitSync(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
    for n in netlist.nodes:
        if n.__class__ is HlsNetNodeExplicitSync and not (removed is not None and n in removed):
            return True
    return False


def removeExplicitSync(dbgTracer: DebugTracer, n: HlsNetNodeExplicitSync, worklist: Optional[SetList[HlsNetNode]], removed: Set[HlsNetNode]):
    with dbgTracer.scoped(removeExplicitSync, n):
        if worklist is not None:
            for dep in n.dependsOn:
                if dep is None:
                    continue
                worklist.append(dep.obj)
            for uses in n.usedBy:
                for u in uses:
                    worklist.append(u.obj)

        dataIn = n.dependsOn[0]
        netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)
        assert len(n._outputs) == 2 or not any(islice(n.usedBy, 2, None)), ("data, ordering")
        if dataIn is not None:
            unlink_hls_nodes(dataIn, n._inputs[0])
        b: HlsNetlistBuilder = n.netlist.builder
        if dataIn is None:
            assert not n.usedBy[0], (n, n.usedBy[0])
        else:
            b.replaceOutput(n._outputs[0], dataIn, True)
        unlink_hls_node_input_if_exists(n.skipWhen)
        unlink_hls_node_input_if_exists(n.extraCond)

    removed.add(n)


def trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(
        src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync,
        removeFromSrc=True):
    assert src is not dst, src
    # reconnect the flag, possibly merge using appropriate logical function and update reachDb
    if src.extraCond is not None:
        ec = src.dependsOn[src.extraCond.in_i]
        assert ec is not None, (src.extraCond, "If has no driver the input shoud be removed")

        if removeFromSrc:
            unlink_hls_nodes(ec, src.extraCond)
        if dst.extraCond:
            assert dst.dependsOn[dst.extraCond.in_i] is not None, ("If has no driver the input shoud be removed")
        dst.addControlSerialExtraCond(ec)
        if removeFromSrc:
            src._removeInput(src.extraCond.in_i)
            src.extraCond = None

    if src.skipWhen is not None:
        sw = src.dependsOn[src.skipWhen.in_i]
        assert sw is not None, (src.skipWhen, "If has no driver the input shoud be removed")
        if removeFromSrc:
            unlink_hls_nodes(sw, src.skipWhen)
        if dst.skipWhen:
            assert dst.dependsOn[dst.skipWhen.in_i] is not None, ("If has no driver the input shoud be removed")
        dst.addControlSerialSkipWhen(sw)
        if removeFromSrc:
            src._removeInput(src.skipWhen.in_i)
            src.skipWhen = None
