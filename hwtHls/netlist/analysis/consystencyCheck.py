from itertools import chain, islice
from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Set, Optional

from hwt.hdl.operatorDefs import AllOps, BITWISE_OPS, COMPARE_OPS
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassConsystencyCheck(HlsNetlistPass):
    """
    Check if connection of nodes is error free.
    """

    @staticmethod
    def _checkConnections(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
        if removed is None:
            allNodes = set(netlist.iterAllNodes())
        else:
            allNodes = set(n for n in netlist.iterAllNodes() if n not in removed)

        for n in netlist.iterAllNodes():
            n: HlsNetNode
            if removed is not None and n in removed:
                continue
            inCnt = len(n._inputs)
            assert inCnt == len(n.dependsOn), n
            for in_i, (i, d) in enumerate(zip(n._inputs, n.dependsOn)):
                assert isinstance(i, HlsNetNodeIn), i
                i: HlsNetNodeIn
                assert i.obj is n, (n, i)
                assert i.in_i == in_i, (n, i)
                assert isinstance(d, HlsNetNodeOut), (d, "->", i)
                assert d.obj in allNodes, ("Driven by something which is not in netlist", n, d.obj)
                assert d.obj._outputs[d.out_i] is d, ("Broken HlsNetNodeOut object", n, in_i, d)
                assert i in d.obj.usedBy[d.out_i], ("Output knows about connected input", n, d, i)

            outCnt = len(n._outputs)
            assert outCnt == len(n.usedBy), n
            for out_i, (o, usedBy) in enumerate(zip(n._outputs, n.usedBy)):
                assert isinstance(o, HlsNetNodeOut), (n, o)
                o: HlsNetNode
                assert o.obj is n, (n, o)
                assert o.out_i is out_i, (n, o)
                seen = set()
                for u in usedBy:
                    try:
                        assert u not in seen, (o, "usedBy list should have unique items", usedBy, u)
                    except:
                        raise
                    seen.add(u)
                    assert isinstance(u, HlsNetNodeIn), (n, o, u)
                    assert u.obj in allNodes, ("Drives something which is not in netlist", o, u)
                    try:
                        assert u.obj._inputs[u.in_i] is u, ("Broken HlsNetNodeIn object", o, u)
                        assert u.obj.dependsOn[u.in_i] is o, ("Input must know about connected output", u, o)
                    except IndexError:
                        raise AssertionError("Use of incorrect port", o, "->", u)

    @staticmethod
    def _checkCycleFree(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
        # check for cycles
        g = DiGraph()
        for n in netlist.iterAllNodes():
            if removed is not None and n in removed:
                continue
            for dep in n.dependsOn:
                if dep is not None:
                    # dep may be None only in metastates where this node is removed
                    # but node list is not updated yet
                    g.add_edge(dep.obj, n)

        for scc in strongly_connected_components(g):
            if len(scc) > 1:
                raise AssertionError("Netlist must be cycle free", sorted(n._id for n in scc))

    @staticmethod
    def _checkNodeContainers(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
        seen: Set[HlsNetNode] = set()
        for n in netlist.iterAllNodesFlat():
            if removed is not None and n in removed:
                continue
            if n in seen:
                raise AssertionError("netlist node list has duplicit items", n)
            else:
                seen.add(n)

    @staticmethod
    def _checkSyncNodes(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
        for n in netlist.iterAllNodes():
            if n.__class__ is HlsNetNodeExplicitSync:
                n: HlsNetNodeExplicitSync
                if removed and n in removed:
                    continue
                inT = n.dependsOn[0]._dtype
                outT = n._outputs[0]._dtype
                assert inT == outT, (n, inT, outT)
                i = n._inputOfCluster
                o = n._outputOfCluster
                if i is None:
                    assert o is None, (n, "_inputOfCluster, _outputOfCluster ports may appear only together")
                else:
                    assert o is not None, (n, "_inputOfCluster, _outputOfCluster ports may appear only together")
                    iClus = n.dependsOn[i.in_i]
                    oClus = n.dependsOn[o.in_i]
                    assert iClus is not None, n
                    assert oClus is not None, n

                    assert iClus.obj is not oClus.obj, (n, iClus.obj, "input/output cluster must be different")

    @staticmethod
    def checkRemovedNotReachable(netlist: HlsNetlistCtx, removed: Set[HlsNetNode]):
        """
        Check that removed nodes are not reachable from non removed nodes.
        """
        allNodes = set(netlist.iterAllNodes())
        for n in netlist.iterAllNodes():
            n: HlsNetNode
            if removed and n in removed:
                continue
            for dep in n.dependsOn:
                assert dep is not None, n
                assert dep.obj in allNodes, (n, dep)
                assert dep.obj not in removed, (n, dep)
            for users in n.usedBy:
                for u in users:
                    assert u.obj in allNodes, (n, u)
                    assert u.obj not in removed, (n, u)

    @staticmethod
    def _checkTypes(netlist: HlsNetlistCtx, removed: Set[HlsNetNode]):
        OPS_WITH_OP0_AND_RES_OF_SAME_TYPE = {*BITWISE_OPS, AllOps.DIV, AllOps.MUL, AllOps.ADD, AllOps.SUB}
        OPS_WITH_SAME_OP_TYPE = {*OPS_WITH_OP0_AND_RES_OF_SAME_TYPE, *COMPARE_OPS}
        for n in netlist.iterAllNodes():
            n: HlsNetNode
            if removed and n in removed:
                continue
            if isinstance(n, HlsNetNodeMux):
                t = n._outputs[0]._dtype
                for v, c in n._iterValueConditionDriverPairs():
                    assert v._dtype == t, ("wrong type of value operand", n, v._dtype, t)
                    assert c is None or c._dtype == BIT, ("wrong type of condition operand", n, c._dtype)

            elif isinstance(n, HlsNetNodeOperator):
                o = n.operator
                op0t = n.dependsOn[0]._dtype
                if o in OPS_WITH_SAME_OP_TYPE:
                    for opN in islice(n.dependsOn, 1, None):
                        assert opN._dtype == op0t, ("wrong type of operand", n, opN._dtype, op0t)
                if o in OPS_WITH_OP0_AND_RES_OF_SAME_TYPE:
                    assert n._outputs[0]._dtype == op0t, ("wrong type of result", n, n._outputs[0]._dtype, op0t)

    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]=None):
        if removed is None:
            removed = netlist.builder._removedNodes
        self._checkConnections(netlist, removed)
        self._checkCycleFree(netlist, removed)
        self._checkNodeContainers(netlist, removed)
        self._checkSyncNodes(netlist, removed)
        self._checkTypes(netlist, removed)
