from itertools import islice
from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Set

from hwt.hdl.operatorDefs import HwtOps, BITWISE_OPS, COMPARE_OPS
from hwt.hdl.types.defs import BIT
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, \
    offsetInClockCycle
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import iterAllHierachies
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregateTmpForScheduling, \
    HlsNetNodeAggregate


class HlsNetlistPassConsistencyCheck(HlsNetlistAnalysisPass):
    """
    Check consistency of the HlsNetlistCtx.
    
    """

    def __init__(self, checkCycleFree:bool=True, checkAggregatePortsScheduling:bool=False, checkAllArchElementPortsInSameClockCycle:bool=False):
        HlsNetlistAnalysisPass.__init__(self)
        self.checkCycleFree = checkCycleFree
        self.checkAggregatePortsScheduling = checkAggregatePortsScheduling
        self.checkAllArchElementPortsInSameClockCycle = checkAllArchElementPortsInSameClockCycle

    @staticmethod
    def _checkConnections(netlist: HlsNetlistCtx, allowDisconnected=False):
        allNodes = set(netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER))

        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            n: HlsNetNode
            if n._isMarkedRemoved:
                continue
            inCnt = len(n._inputs)
            assert inCnt == len(n.dependsOn), n
            for in_i, (i, d) in enumerate(zip(n._inputs, n.dependsOn)):
                assert isinstance(i, HlsNetNodeIn), i
                i: HlsNetNodeIn
                assert i.obj is n, (n, i)
                assert i.in_i == in_i, (n, i)
                if allowDisconnected and d is None:
                    continue
                assert isinstance(d, HlsNetNodeOut), ("Driven by incorrect port object", d, "->", i)
                assert d.obj in allNodes, ("Driven by something which is not in netlist", n, i, d)
                assert not d.obj._isMarkedRemoved, ("Driven by removed", i, d)
                assert d.obj._outputs[d.out_i] is d, ("Broken HlsNetNodeOut object", n, in_i, d)
                assert i in d.obj.usedBy[d.out_i], ("Output knows about connected input", n, d, i)

            outCnt = len(n._outputs)
            assert outCnt == len(n.usedBy), n
            for out_i, (o, usedBy) in enumerate(zip(n._outputs, n.usedBy)):
                assert isinstance(o, HlsNetNodeOut), (n, o)
                o: HlsNetNode
                assert o.obj is n, ("Output parent check", n, o)
                assert o.out_i == out_i, ( "Output index must be equal to index in node outputs", o.out_i, out_i, o)
                seen = set()
                for u in usedBy:
                    assert u not in seen, (o, "usedBy list should have unique items", usedBy, u)
                    seen.add(u)
                    assert isinstance(u, HlsNetNodeIn), ("User of output must be HlsNetNodeIn instance", n, o, u)
                    assert u.obj in allNodes, ("Drives something which is not in netlist", o, u)
                    assert not u.obj._isMarkedRemoved, ("User is removed", o, u)
                    assert u.obj.parent is n.parent, ("Port connection must not cross hierarchy elements", o, u, n.parent, u.obj.parent)
                    try:
                        assert u.obj._inputs[u.in_i] is u, ("Broken HlsNetNodeIn object", o, u)
                        assert u.obj.dependsOn[u.in_i] is o, ("Input must know about connected output", u, o)
                    except IndexError:
                        raise AssertionError("Use of incorrect port", o, "->", u)

    @staticmethod
    def _checkCycleFree(netlist: HlsNetlistCtx):
        # check for cycles
        g = DiGraph()
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            n: HlsNetNode
            if n._isMarkedRemoved:
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
    def _checkNodeContainers(netlist: HlsNetlistCtx):
        seen: Set[HlsNetNode] = set()
        for elm in iterAllHierachies(netlist):
            for n in elm.subNodes:
                n: HlsNetNode
                if n._isMarkedRemoved:
                    continue
                if n in seen:
                    raise AssertionError("netlist node list has duplicit items", n, elm, n.parent)
                else:
                    assert n.parent is elm or (n.parent is None and n.netlist is elm), ("parent is not set to real parent containing node", n, n.parent, elm)
                    seen.add(n)

    @staticmethod
    def _checkSyncNodes(netlist: HlsNetlistCtx):
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            if n._isMarkedRemoved:
                continue

            assert n.__class__ is not HlsNetNodeExplicitSync, ("HlsNetNodeExplicitSync class is an abstract class and should not be used to represent nodes")
            if isinstance(n, HlsNetNodeMux):
                assert len(n._inputs) % 2 == 1, n
                assert len(n._outputs) == 1, n

    @staticmethod
    def checkRemovedNotReachable(netlist: HlsNetlistCtx):
        """
        Check that removed nodes are not reachable from non removed nodes.
        """
        allNodes = set(netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER))
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            n: HlsNetNode
            assert not n._isMarkedRemoved, n
            for dep in n.dependsOn:
                assert dep is not None, n
                assert dep.obj in allNodes, (n, dep)
                assert not dep.obj._isMarkedRemoved, (n, dep)
            for users in n.usedBy:
                for u in users:
                    assert u.obj in allNodes, (n, u)
                    assert not u.obj._isMarkedRemoved, (n, u)

    @staticmethod
    def _checkTypes(netlist: HlsNetlistCtx):
        OPS_WITH_OP0_AND_RES_OF_SAME_TYPE = {*BITWISE_OPS, HwtOps.UDIV, HwtOps.SDIV, HwtOps.DIV, HwtOps.MUL, HwtOps.ADD, HwtOps.SUB}
        OPS_WITH_SAME_OP_TYPE = {*OPS_WITH_OP0_AND_RES_OF_SAME_TYPE, *COMPARE_OPS}
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER):
            n: HlsNetNode
            assert not n._isMarkedRemoved, n
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

    @staticmethod
    def _checkAggregatePortsScheduling_inputs(dstElm: HlsNetNodeAggregate):
        """
        check that all inputs and HlsNetNodeAggregatePortIn have correct time and type
        """
        clkPeriod = dstElm.netlist.normalizedClkPeriod
        for dep, u, ii in zip(dstElm.dependsOn, dstElm._inputs, dstElm._inputsInside):
            assert ii._outputs[0]._dtype == dep._dtype, (
                "Aggregate port must have same type as its driver", ii._outputs[0]._dtype, dep._dtype, ii, dep)
            dstIsNoSyncElm = isinstance(dstElm, ArchElementNoImplicitSync)
            # check that dst port and port internally inside of dst has correct time
            if dstIsNoSyncElm:
                assert dstElm.scheduledZero == 0
                t = offsetInClockCycle(dstElm.scheduledIn[u.in_i], clkPeriod)
                assert ii.scheduledOut == (t,), (
                    "ArchElementNoImplicitSync instance internal input ports should all be scheduled to offset in clock cycle",
                    u, ii.scheduledOut, t)
            else:
                dstPortTime = dstElm.scheduledIn[u.in_i]
                assert (dstPortTime,) == ii.scheduledOut, (
                    dstPortTime, ii.scheduledOut, ii, "Aggregate input port must have same time inside and outside of element")

    def _checkAggregatePortsScheduling(self, netlist: HlsNetlistCtx, checkArchElementPortsInSameClockCycle: bool):
        """
        Check if all top nodes are instances of ArchElement and all connected ports are always in same clock cycle window.
        """
        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        for srcElm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_POSTORDER):
            if srcElm is netlist:
                continue
            assert not srcElm._isMarkedRemoved, srcElm
            assert isinstance(srcElm, (ArchElement, HlsNetNodeAggregateTmpForScheduling)), ("Expected only ArchElement instances at top level", srcElm)

            srcElm: ArchElement
            # check all inputs connected to this output o

            self._checkAggregatePortsScheduling_inputs(srcElm)

            for srcTime, oInside, o, uses in zip(srcElm.scheduledOut, srcElm._outputsInside, srcElm._outputs, srcElm.usedBy):
                assert uses, o
                assert oInside.scheduledIn == (srcTime,), (oInside.scheduledIn, srcTime, oInside,
                                                            "Aggregate output port must have same time inside and outside of element")
                if not checkArchElementPortsInSameClockCycle:
                    continue
                if HdlType_isVoid(o._dtype):
                    continue

                srcClkI = indexOfClkPeriod(srcTime, clkPeriod)
                for inp in uses:
                    dstElm: ArchElement = inp.obj
                    if not isinstance(dstElm, (ArchElement, HlsNetNodeAggregateTmpForScheduling)):
                        continue

                    dstTime = dstElm.scheduledIn[inp.in_i]
                    assert srcClkI == indexOfClkPeriod(dstTime, clkPeriod), (
                        "At this point all inter element IO paths should be scheduled in a same clk period",
                        o, inp, srcTime, dstTime, clkPeriod)
                    assert isinstance(dstElm, ArchElement), inp

    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        self._checkConnections(netlist)
        if self.checkCycleFree:
            self._checkCycleFree(netlist)
        self._checkNodeContainers(netlist)
        self._checkSyncNodes(netlist)
        self._checkTypes(netlist)
        if self.checkAggregatePortsScheduling or self.checkAllArchElementPortsInSameClockCycle:
            self._checkAggregatePortsScheduling(netlist, self.checkAllArchElementPortsInSameClockCycle)
