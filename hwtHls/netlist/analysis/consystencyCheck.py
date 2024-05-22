from itertools import islice
from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Set, Optional

from hwt.hdl.operatorDefs import HwtOps, BITWISE_OPS, COMPARE_OPS
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, \
    offsetInClockCycle
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.nodes.archElementNoSync import ArchElementNoSync


class HlsNetlistPassConsystencyCheck(HlsNetlistPass):
    """
    Check if connection of nodes is error free.
    """

    def __init__(self, checkCycleFree:bool=True, checkAllArchElementPortsInSameClockCycle:bool=False):
        HlsNetlistPass.__init__(self)
        self.checkCycleFree = checkCycleFree
        self.checkAllArchElementPortsInSameClockCycle = checkAllArchElementPortsInSameClockCycle

    @staticmethod
    def _checkConnections(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
        if removed is None:
            allNodes = set(netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER))
        else:
            allNodes = set(n for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER) if n not in removed)

        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
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
                assert d.obj in allNodes, ("Driven by something which is not in netlist", n, i, d)
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
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
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
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            if removed is not None and n in removed:
                continue
            if n in seen:
                raise AssertionError("netlist node list has duplicit items", n)
            else:
                seen.add(n)

    @staticmethod
    def _checkSyncNodes(netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]):
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
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
            elif isinstance(n, HlsNetNodeMux):
                assert len(n._inputs) % 2 == 1, n
                assert len(n._outputs) == 1, n

    @staticmethod
    def checkRemovedNotReachable(netlist: HlsNetlistCtx, removed: Set[HlsNetNode]):
        """
        Check that removed nodes are not reachable from non removed nodes.
        """
        allNodes = set(netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER))
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
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
        OPS_WITH_OP0_AND_RES_OF_SAME_TYPE = {*BITWISE_OPS, HwtOps.UDIV, HwtOps.SDIV, HwtOps.DIV, HwtOps.MUL, HwtOps.ADD, HwtOps.SUB}
        OPS_WITH_SAME_OP_TYPE = {*OPS_WITH_OP0_AND_RES_OF_SAME_TYPE, *COMPARE_OPS}
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
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

    def _checkAllArchElementPortsInSameClockCycle(self, netlist: HlsNetlistCtx, removed: Set[HlsNetNode]):
        """
        Check if all top nodes are instances of ArchElement and all connected ports are always in same clock cycle window.
        """
        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        for srcElm in netlist.nodes:
            if srcElm in removed:
                continue
            assert isinstance(srcElm, ArchElement), srcElm

            srcElm: ArchElement
            for srcTime, oInside, o, uses in zip(srcElm.scheduledOut, srcElm._outputsInside, srcElm._outputs, srcElm.usedBy):
                assert uses, o
                assert oInside.scheduledIn == (srcTime,), (oInside.scheduledIn, srcTime, oInside,
                                                            "Aggregate output port must have same time inside and outside of element")
                # check all inputs connected to this output o
                for u in uses:
                    u: HlsNetNodeIn
                    dstElm: ArchElement = u.obj
                    ii = dstElm._inputsInside[u.in_i]
                    assert ii._outputs[0]._dtype == o._dtype, (
                        "Aggregate port must have same type as its driver", ii._outputs[0]._dtype, o._dtype, ii, o)
                    dstIsNoSyncElm = isinstance(dstElm, ArchElementNoSync)
                    # check that dst port and port internally inside of dst has correct time
                    if dstIsNoSyncElm:
                        assert dstElm.scheduledZero == 0
                        t = offsetInClockCycle(dstElm.scheduledIn[u.in_i], clkPeriod)
                        assert ii.scheduledOut == (t,), (
                            "ArchElementNoSync instance internal input ports should all be scheduled to offset in clock cycle",
                            u, ii.scheduledOut, t)
                    else:
                        dstPortTime = dstElm.scheduledIn[u.in_i]
                        assert (dstPortTime,) == ii.scheduledOut, (
                            dstPortTime, ii.scheduledOut, ii, "Aggregate input port must have same time inside and outside of element")

                if HdlType_isVoid(o._dtype):
                    continue

                srcClkI = indexOfClkPeriod(srcTime, clkPeriod)
                for inp in uses:
                    dstElm: ArchElement = inp.obj
                    dstTime = dstElm.scheduledIn[inp.in_i]
                    assert srcClkI == indexOfClkPeriod(dstTime, clkPeriod), (
                        "At this point all inter element IO paths should be scheduled in a same clk period",
                        o, inp, srcTime, dstTime, clkPeriod)
                    assert isinstance(dstElm, ArchElement), inp

    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx, removed: Optional[Set[HlsNetNode]]=None):
        if removed is None:
            removed = netlist.builder._removedNodes
        self._checkConnections(netlist, removed)
        if self.checkCycleFree:
            self._checkCycleFree(netlist, removed)
        self._checkNodeContainers(netlist, removed)
        self._checkSyncNodes(netlist, removed)
        self._checkTypes(netlist, removed)
        if self.checkAllArchElementPortsInSameClockCycle:
            self._checkAllArchElementPortsInSameClockCycle(netlist, removed)
