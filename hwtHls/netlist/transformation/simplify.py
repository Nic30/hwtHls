from itertools import chain, islice
from typing import Set, Generator, Tuple, Literal, Optional

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeExplicitSync, HlsNetNodeRead, \
    HlsNetNodeWrite
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.utils import hls_op_not, hls_op_const_index_slice, \
    hls_op_concat_variadic
from pyMathBitPrecise.bit_utils import get_bit, mask
from hwtHls.netlist.transformation.dce import HlsNetlistPassDCE


def iter1and0sequences(v: BitsVal) -> Generator[Tuple[Literal[1, 0], int], None, None]:
    """
    :note: same as ConstBitPartsAnalysisContext::iter1and0sequences
    :note: lower first
    :returns: generators of tuples in format 0/1, width
    """
    # if the bit in c is 0 the output bit should be also 0 else it is bit from v
    l_1: int = -1  # start of 1 sequence, -1 as invalid value
    l_0: int = -1  # start of 0 sequence, -1 as invalid value
    endIndex = v._dtype.bit_length() - 1
    if not v._isFullVld():
        raise NotImplementedError(v)
    _v = v.val
    for h in range(endIndex + 1):
        curBit = get_bit(_v, h)
        if l_1 == -1 and curBit:
            l_1 = h  # start of 1 sequence
        elif l_0 == -1 and not curBit:
            l_0 = h  # start of 0 sequence

        last = h == endIndex
        if l_1 != -1 and (last or not get_bit(_v, h + 1)):
            # end of 1 sequence found
            w = h - l_1 + 1
            yield (1, w)
            l_1 = -1  # reset start
        elif l_0 != -1 and (last or get_bit(_v, h + 1)):
            # end of 0 sequence found
            w = h - l_0 + 1
            yield (0, w)
            l_0 = -1  # reset start


def isAll0OrAll1(v: BitsVal):
    vInt = int(v)
    return vInt == 0 or vInt == mask(v._dtype.bit_length())
                

class HlsNetlistPassSimplify(HlsNetlistPass):
    """
    Hls netlist simplification:

    * reduce HlsNetNodeMux with a single input
    * reduce and/or/xor
    * remove HlsNetNodeExplicitSync (and subclasses like HlsNetNodeRead,HlsNetNodeWrite) skipWhen and extraCond connected to const  
    """

    def apply(self, hls:"HlsScope", netlist: HlsNetlistCtx):
        threads: HlsNetlistAnalysisPassDataThreads = netlist.requestAnalysis(HlsNetlistAnalysisPassDataThreads)
        
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
                n: HlsNetNodeOperator
                if isinstance(n, HlsNetNodeMux):
                    if self._reduceMux(n, worklist, removed):
                        continue
                elif n.operator == AllOps.NOT:
                    if self._reduceNot(n, worklist, removed):
                        continue

                elif n.operator in (AllOps.AND, AllOps.OR, AllOps.XOR):
                    if self._reduceAndOrXor(n, worklist, removed):
                        continue

            elif isinstance(n, HlsNetNodeExplicitSync):
                n: HlsNetNodeExplicitSync
                if n.skipWhen is not None:
                    dep = n.dependsOn[n.skipWhen.in_i]
                    if isinstance(dep.obj, HlsNetNodeConst):
                        assert int(dep.obj.val) == 0, ("Must be 0 because otherwise this is should not be used at all", n, dep.obj)
                        dep.obj.usedBy[dep.out_i].remove(n.skipWhen)
                        worklist.append(dep.obj)
                        n._removeInput(n.skipWhen.in_i)
                        n.skipWhen = None
                    
                if n.extraCond is not None:
                    dep = n.dependsOn[n.extraCond.in_i]
                    if isinstance(dep.obj, HlsNetNodeConst):
                        assert int(dep.obj.val) == 1, ("Must be 1 because otherwise this is should not be used at all", n, dep.obj)
                        dep.obj.usedBy[dep.out_i].remove(n.extraCond)
                        worklist.append(dep.obj)
                        n._removeInput(n.extraCond.in_i)
                        n.extraCond = None
                        
                # remove ordering if it is redundant information
                for orderingI in tuple(n.iterOrderingInputs()):
                    orderingI: HlsNetNodeIn
                    t0 = threads.threadPerNode[n]
                    dep = n.dependsOn[orderingI.in_i]
                    t1 = threads.threadPerNode[dep.obj]
                    if t0 is t1:
                        if isinstance(n, HlsNetNodeRead) and isinstance(dep.obj, HlsNetNodeRead):
                            n: HlsNetNodeRead
                            if n.src is dep.obj.src:
                                # can not ignore order of reads from same volatile source
                                continue
                        elif isinstance(n, HlsNetNodeWrite) and isinstance(dep.obj, HlsNetNodeWrite):
                            n: HlsNetNodeWrite
                            if n.dst is dep.obj.dst:
                                # can not ignore order of writes to same volatile destination
                                continue
                        dep.obj.usedBy[dep.out_i].remove(orderingI)
                        n._removeInput(orderingI.in_i)

                if n.__class__ is HlsNetNodeExplicitSync:
                    n: HlsNetNodeExplicitSync
                    # remove whole node if not synchronizing anything
                    if not n.usedBy[0]:
                        if n._isHlsNetNodeExplicitSyncFlagsRequred(n):
                            continue
                        for i in n._inputs:
                            dep = n.dependsOn[i.in_i]
                            dep.obj.usedBy[dep.out_i].remove(i)
                            worklist.append(dep.obj)
                        
                        removed.add(n)
                    elif self._getConstDriverOf(n._inputs[0]) is not None and all(not use for use in islice(n.usedBy, 1, None)):
                        for _ in range(len(n.usedBy) - 1):
                            n.usedBy.pop()
                            n._outputs.pop()

                        self._replaceOperatorNodeWith(n, n.dependsOn[0], worklist, removed)

        if removed:
            nodes = netlist.nodes
            netlist.nodes = [n for n in nodes if n not in removed]

    def _isHlsNetNodeExplicitSyncFlagsRequred(self, n: HlsNetNodeExplicitSync) -> bool:
        if n.extraCond is not None:
            c = self._getConstDriverOf(n.extraCond)
            if c is None or int(c) != 1:
                if n.skipWhen is not None:
                    c = self._getConstDriverOf(n.skipWhen)
                    if c is not  None and int(c) == 1:
                        # always skipped extraCond does not matter
                        return False
                    else:
                        # not always skipped with some extraCond, can not remove
                        return True
                else:
                    # not always skipped with some extraCond, can not remove
                    return True
        return False
     
    def _getConstDriverOf(self, inputObj: HlsNetNodeIn) -> Optional[HValue]:
        dep = inputObj.obj.dependsOn[inputObj.in_i]
        if isinstance(dep.obj, HlsNetNodeConst):
            return dep.obj.val
        else:
            return None

    def _disconnectAllInputs(self, n: HlsNetNode, worklist: UniqList[HlsNetNode]):
        for i, dep in zip(n._inputs, n.dependsOn):
            i: HlsNetNodeIn
            dep: HlsNetNodeOut
            # disconnect driver from self
            dep.obj.usedBy[dep.out_i].remove(i)
            worklist.append(dep.obj)

    def _replaceOperatorNodeWith(self, n: HlsNetNodeOperator, o: HlsNetNodeOut, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        assert len(n.usedBy) == 1, (n, "implement only for single output nodes")
        self._disconnectAllInputs(n, worklist)
        self._addAllUsersToWorklist(worklist, n)
        # reconnect all dependencies to an only driver of this mux
        for u in n.usedBy[0]:
            u: HlsNetNodeIn
            u.replaceDriverInInputOnly(o)
        n.usedBy[0].clear()
        removed.add(n)

    def _addAllUsersToWorklist(self, worklist: UniqList[HlsNetNode], n: HlsNetNodeOperator):
        for uses in n.usedBy:
            for u in uses:
                worklist.append(u.obj)

    def _isTriviallyDead(self, n: HlsNetNode):
        if isinstance(n, HlsNetlistPassDCE.NON_REMOVABLE_CLS):
            return False
        else:
            for uses in n.usedBy:
                if uses:
                    return False
            return True

    def _addConstPy(self, netlist: HlsNetlistCtx, dtype: HdlType, v):
        c = HlsNetNodeConst(netlist, dtype.from_py(v))
        netlist.nodes.append(c)
        return c._outputs[0]
    
    def _addConst(self, netlist: HlsNetlistCtx, v: HValue):
        c = HlsNetNodeConst(netlist, v)
        netlist.nodes.append(c)
        return c._outputs[0]
    
    def _reduceMux(self, n: HlsNetNodeMux, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        if len(n._inputs) == 1:
            # mux x = x
            i: HlsNetNodeOut = n.dependsOn[0]
            self._replaceOperatorNodeWith(n, i, worklist, removed)
            return True
        return False

    def _reduceNot(self, n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        netlist: HlsNetlistCtx = n.netlist
        o0, = n.dependsOn
        o0Const = isinstance(o0.obj, HlsNetNodeConst)
        newO = None
        if o0Const:
            newO = self._addConst(netlist, ~o0.obj.val)
        elif isinstance(o0, HlsNetNodeOut) and isinstance(o0.obj, HlsNetNodeOperator) and o0.obj.operator == AllOps.NOT:
            # ~~x = x
            newO = o0.obj.dependsOn[0]
        
        if newO is not None:
            self._replaceOperatorNodeWith(n, newO, worklist, removed)
            return True
        return False

    def _reduceAndOrXor(self, n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
        netlist: HlsNetlistCtx = n.netlist
        # search for const in for commutative operator
        o0, o1 = n.dependsOn
        o0Const = isinstance(o0.obj, HlsNetNodeConst)
        o1Const = isinstance(o1.obj, HlsNetNodeConst)
        newO = None

        if o0Const and not o1Const:
            # make sure const is o1 if const is in operands
            o0, o1 = o1, o0
            o0Const = False
            o1Const = True

        if n.operator == AllOps.AND:
            if o0Const and o1Const:
                newO = self._addConst(netlist, o0.obj.val & o1.obj.val)

            elif o1Const:
                # to concatenation of o0 bits and 0s after const mask is applied 
                if isAll0OrAll1(o1.obj.val):
                    if int(o1.obj.val):
                        # x & 1 = x
                        newO = o0
                    else:
                        # x & 0 = 0
                        newO = self._addConstPy(netlist, o0._dtype, 9)

                else:
                    concatMembers = []
                    offset = 0
                    for bitVal, width in iter1and0sequences(o1.obj.val):
                        if bitVal:
                            # x & 1 = x
                            v0 = hls_op_const_index_slice(netlist, o0, offset + width, offset)
                        else:
                            # x & 0 = 0
                            v0 = self._addConstPy(netlist, Bits(width), 0)

                        concatMembers.append(v0)
                            
                        offset += width
                    newO = hls_op_concat_variadic(netlist, *reversed(concatMembers))

            elif o0 == o1:
                # x & x = x
                newO = o0

        elif n.operator == AllOps.OR:
            if o0Const and o1Const:
                newO = self._addConst(netlist, o0.obj.val | o1.obj.val)

            elif o1Const:
                if isAll0OrAll1(o1.obj.val):
                    if int(o1.obj.val):
                        # x | 1 = 1
                        newO = self._addConstPy(netlist, o0._dtype, mask(o0._dtype.bit_length()))
                    else:
                        # x | 0 = x
                        newO = o0

                else:
                    concatMembers = []
                    offset = 0
                    for bitVal, width in iter1and0sequences(o1.obj.val):
                        if bitVal:
                            # x | 1 = 1
                            v0 = self._addConstPy(netlist, Bits(width), mask(width))
                        else:
                            # x | 0 = x
                            v0 = hls_op_const_index_slice(netlist, o0, offset + width, offset)

                        concatMembers.append(v0)
                            
                        offset += width
                    newO = hls_op_concat_variadic(netlist, *reversed(concatMembers))

            elif o0 == o1:
                # x | x = x
                newO = o0

        elif n.operator == AllOps.XOR:

            if o0Const and o1Const:
                newO = self._addConst(netlist, o0.obj.val ^ o1.obj.val)

            elif o1Const:
                # perform reduction by constant
                if isAll0OrAll1(o1.obj.val):
                    if int(o1.obj.val):
                        # x ^ 1 = ~x
                        newO = hls_op_not(netlist, o0)
                    else:
                        # x ^ 0 = x
                        newO = o0
                else:
                    concatMembers = []
                    offset = 0
                    for bitVal, width in iter1and0sequences(o1.obj.val):
                        v0 = hls_op_const_index_slice(netlist, o0, offset + width, offset)
                        if bitVal:
                            v0 = hls_op_not(netlist, v0)
                        concatMembers.append(v0)
                            
                        offset += width
                    newO = hls_op_concat_variadic(netlist, *reversed(concatMembers))
            
            elif o0 == o1:
                # x ^ x = 0
                newN = HlsNetNodeConst(netlist, o0._dtype.from_py(0))
                netlist.nodes.append(newN)
                newO = newN._outputs[0]
            
        if newO is not None:
            self._replaceOperatorNodeWith(n, newO, worklist, removed)
            return True
        return False

    # def _hoistCommonOperands(self, n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    #    # [todo] it is not clear if such a optimization would be beneficial because some subexpression could be computed sooner
    #             and by this we may genereate a new functional unit 
        
