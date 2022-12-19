from itertools import chain
from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Set, Optional

from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync


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
                    assert u.obj in allNodes, ("Drives something which is not in netlist", n, o, u)
                    try:
                        assert u.obj._inputs[u.in_i] is u, ("Broken HlsNetNodeIn object", n, o, u)
                        assert u.obj.dependsOn[u.in_i] is o, ("Input must know about connected output", n, u, o)
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
                raise AssertionError("Netlist must be cycle free", scc)
    
    @staticmethod
    def _checkNodeContainers(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
        seen: Set[HlsNetNode] = set()
        for n in chain(netlist.inputs, netlist.nodes, netlist.outputs):
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
                if removed and n in removed:
                    continue
                inT = n.dependsOn[0]._dtype
                outT = n._outputs[0]._dtype
                assert inT == outT, (n, inT, outT)
    
    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]=None):
        self._checkConnections(netlist, removed)
        self._checkCycleFree(netlist, removed)
        self._checkNodeContainers(netlist, removed)
        self._checkSyncNodes(netlist, removed)
