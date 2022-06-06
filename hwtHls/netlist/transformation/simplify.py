from itertools import chain
from typing import Set

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassSimplify(HlsNetlistPass):
    """
    Hls netlist simplification:

    * reduce HlsNetNodeMux with a single input
    * reduce and/or/xor
    * remove HlsNetNodeExplicitSync (and subclasses like HlsNetNodeRead,HlsNetNodeWrite) skipWhen and extraCond connected to const  
    """

    def apply(self, hls:"HlsStreamProc", netlist: HlsNetlistCtx):
        worklist: UniqList[HlsNetNode] = UniqList(chain(netlist.iterAllNodes()))
        removed: Set[HlsNetNode] = set()
        while worklist:
            n = worklist.pop()
            if n in removed:
                continue

            if self._isTriviallyDead(n):
                self._disconnectAllInputs(n, worklist)
                removed.add(n)
                continue
                
            if isinstance(n, HlsNetNodeOperator):
                if isinstance(n, HlsNetNodeMux):
                    n: HlsNetNodeMux
                    if len(n._inputs) == 1:
                        i: HlsNetNodeOut = n.dependsOn[0]
                        self._replaceOperatorNodeWith(n, i, worklist, removed)

                else:
                    n: HlsNetNodeOperator
                    if n.operator in (AllOps.AND, AllOps.OR, AllOps.XOR):
                        self._reduceAndOrXor(n, worklist, removed)
            elif isinstance(n, HlsNetNodeExplicitSync):
                n: HlsNetNodeExplicitSync
                if n.skipWhen is not None:
                    dep = n.dependsOn[n.skipWhen.in_i]
                    if isinstance(dep.obj, HlsNetNodeConst):
                        assert int(dep.obj.val) == 0, ("Bust be 0 because otherwise this is should not be used at all", n, dep.obj)
                        dep.obj.usedBy[dep.out_i].remove(n.skipWhen)
                        worklist.append(dep.obj)
                        n._removeInput(n.skipWhen.in_i)
                        n.skipWhen = None
                    
                if n.extraCond is not None:
                    dep = n.dependsOn[n.extraCond.in_i]
                    if isinstance(dep.obj, HlsNetNodeConst):
                        assert int(dep.obj.val) == 1, ("Bust be 1 because otherwise this is should not be used at all", n, dep.obj)
                        dep.obj.usedBy[dep.out_i].remove(n.extraCond)
                        worklist.append(dep.obj)
                        n._removeInput(n.extraCond.in_i)
                        n.extraCond = None
        if removed:
            nodes = netlist.nodes
            netlist.nodes = [n for n in nodes if n not in removed]

    def _disconnectAllInputs(self, n: HlsNetNode, worklist: UniqList[HlsNetNode]):
        for i, dep in zip(n._inputs, n.dependsOn):
            i: HlsNetNodeIn
            dep: HlsNetNodeOut
            # disconnect driver from self
            dep.obj.usedBy[dep.out_i].remove(i)
            worklist.append(dep.obj)

    def _replaceOperatorNodeWith(self, n: HlsNetNodeOperator, o: HlsNetNodeOut, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        assert len(n.usedBy) == 1, n
        self._disconnectAllInputs(n, worklist)
        self._addAllUsersToWorklist(worklist, n)
        # reconnect all dependencies to an only driver of this mux
        for u in n.usedBy[0]:
            u: HlsNetNodeIn
            u.replace_driver(o)
        removed.add(n)

    def _addAllUsersToWorklist(self, worklist: UniqList[HlsNetNode], n: HlsNetNodeOperator):
        for uses in n.usedBy:
            for u in uses:
                worklist.append(u.obj)

    def _isTriviallyDead(self, n: HlsNetNode):
        if isinstance(n, HlsNetNodeExplicitSync):
            return False
        else:
            for uses in n.usedBy:
                if uses:
                    return False
            return True

    def _reduceAndOrXor(self, n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        netlist: HlsNetlistCtx = n.netlist
        # search for const in for commutative operator
        o0, o1 = n.dependsOn
        o0Const = isinstance(o0.obj, HlsNetNodeConst)
        o1Const = isinstance(o1.obj, HlsNetNodeConst)
        if o0Const and not o1Const:
            # make sure const is o1 if const is in operands
            o0, o1 = o1, o0
            o0Const = False
            o1Const = True
        bitWidth = o0._dtype.bit_length()
        if n.operator == AllOps.AND:
            if o0Const and o1Const:
                v = o0.obj.val & o1.obj.val
                newN = HlsNetNodeConst(netlist, v)
                netlist.nodes.append(newN)
                self._replaceOperatorNodeWith(n, newN._outputs[0], worklist, removed)

            elif o1Const:
                # to concatenation of o0 bits and 0s after const mask is applied 
                if bitWidth == 1:
                    if int(o1.obj.val):
                        # x & 1 = x
                        newO = o0._outputs[0]
                    else:
                        # x & 0 = 0
                        newN = HlsNetNodeConst(netlist, o0._dtype.from_py(0))
                        netlist.nodes.append(newN)
                        newO = newN._outputs[0]

                    self._replaceOperatorNodeWith(n, newO, worklist, removed)
                else:
                    raise NotImplementedError()

            elif o0 == o1:
                # x & x = x
                self._replaceOperatorNodeWith(n, o0, worklist, removed)

        elif n.operator == AllOps.OR:
            if o0Const and o1Const:
                v = o0.obj.val | o1.obj.val
                newN = HlsNetNodeConst(netlist, v)
                netlist.nodes.append(newN)
                self._replaceOperatorNodeWith(n, newN._outputs[0], worklist, removed)

            elif o1Const:
                if bitWidth == 1:
                    if int(o1.obj.val):
                        # x | 1 = 1
                        newN = HlsNetNodeConst(netlist, o0._dtype.from_py(1))
                        netlist.nodes.append(newN)
                        newO = newN._outputs[0]
                    else:
                        # x | 0 = x
                        newO = o0._outputs[0]

                    self._replaceOperatorNodeWith(n, newO, worklist, removed)
                else:
                    raise NotImplementedError()

            elif o0 == o1:
                # x | x = x
                self._replaceOperatorNodeWith(n, o0, worklist, removed)

        elif n.operator == AllOps.XOR:
            if o0Const and o1Const:
                v = o0.obj.val ^ o1.obj.val
                newN = HlsNetNodeConst(netlist, v)
                netlist.nodes.append(newN)
                self._replaceOperatorNodeWith(n, newN._outputs[0], worklist, removed)

            elif o1Const:
                if bitWidth == 1:
                    if int(o1.obj.val):
                        # x ^ 1 = ~x
                        newN = HlsNetNodeOperator(netlist, AllOps.NOT, 2, o0._dtype, n.name)
                        netlist.nodes.append(newN)
                        newO = newN._outputs[0]
                    else:
                        # x ^ 0 = x
                        newO = o0._outputs[0]

                    self._replaceOperatorNodeWith(n, newO, worklist, removed)
                else:
                    raise NotImplementedError()

            elif o0 == o1:
                # x ^ x = 0
                newN = HlsNetNodeConst(netlist, o0._dtype.from_py(0))
                netlist.nodes.append(newN)
                newO = newN._outputs[0]
                self._replaceOperatorNodeWith(n, newO, worklist, removed)
