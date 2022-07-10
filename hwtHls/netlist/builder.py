
from typing import Tuple, Union, Dict, Optional

from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.types.defs import BIT, SLICE
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import grouper, balanced_reduce
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, \
    HlsNetNodeIn, HlsNetNodeOutLazy, HlsNetNodeOutAny
from hwtHls.netlist.nodes.node import HlsNetNode
from hwt.hdl.types.bits import Bits


class HlsNetlistBuilder():
    """
    This class can be used to build HlsNetNodes is uses structural hashing for :class:`HlsNetNodeOperator` instances.
    This means that the same operator and operands always yields the same output object.

    :note: constant nodes are always unique nodes and structural hashing does not apply to them.
        (But operator nodes with const operands will yield always the same output object.)
    :note: Constant operands are always store in operatorCache key as a HValue and output of HlsNetNodeConst is never used.
    """

    def __init__(self, netlist: HlsNetlistCtx):
        self.netlist = netlist
        self.operatorCache: Dict[Tuple[OpDefinition, Tuple[Union[HlsNetNodeOut, HValue], ...]], HlsNetNodeOut] = {}

    def _outputOfConstNodeToHValue(self, o: Union[HlsNetNodeOut, HValue]):
        if isinstance(o, (HValue, HlsNetNodeOutLazy)):
            return o
        obj = o.obj
        if isinstance(obj, HlsNetNodeConst):
            return obj.val
        return o

    def _toNodeOut(self, o: Union[HlsNetNodeOut, HValue]):
        if isinstance(o, HValue):
            return self.buildConst(o)
        else:
            return o

    def buildConstPy(self, dtype: HdlType, v):
        return self.buildConst(dtype.from_py(v))
    
    def buildConst(self, v: HValue):
        netlist = self.netlist
        try:
            c = HlsNetNodeConst(netlist, v)
        except:
            raise
        netlist.nodes.append(c)
        return c._outputs[0]

    def buildConstBit(self, v: int):
        return self.buildConst(BIT.from_py(v))

    def buildOp(self, operator: OpDefinition, resT: HdlType, *operands: Tuple[Union[HlsNetNodeOut, HValue], ...]) -> HlsNetNodeOut:
        key = (operator, operands)
        try:
            return self.operatorCache[key]
        except KeyError:
            pass
        # if there are constants in operands try to search them as well
        # variant of the key where all constants are converted to HValue
        operandsWithHValues = tuple(self._outputOfConstNodeToHValue(o) for o in operands)
        keyWithHValues = (operator, operandsWithHValues)
        try:
            return self.operatorCache[keyWithHValues]
        except KeyError:
            pass

        operandsWithOutputsOnly = tuple(self._toNodeOut(o) for o in operands)
        
        n = HlsNetNodeOperator(self.netlist, operator, len(operands), resT)
        self.netlist.nodes.append(n)
        for i, arg in zip(n._inputs, operandsWithOutputsOnly):
            link_hls_nodes(arg, i)

        o = n._outputs[0]
        self.operatorCache[keyWithHValues] = o
        return o

    def buildAndVariadic(self, ops: Tuple[Union[HlsNetNodeOut, HValue], ...]):
        return balanced_reduce(ops, lambda a, b: self.buildAnd(a, b))

    def buildOrVariadic(self, ops: Tuple[Union[HlsNetNodeOut, HValue], ...]):
        return balanced_reduce(ops, lambda a, b: self.buildOr(a, b))

    def buildAnd(self, a: Union[HlsNetNodeOut, HValue], b:Union[HlsNetNodeOut, HValue]) -> HlsNetNodeOut:
        return self.buildOp(AllOps.AND, a._dtype, a, b)
    
    def buildOr(self, a: Union[HlsNetNodeOut, HValue], b:Union[HlsNetNodeOut, HValue]) -> HlsNetNodeOut:
        return self.buildOp(AllOps.OR, a._dtype, a, b)
    
    def buildNot(self, a: Union[HlsNetNodeOut, HValue]) -> HlsNetNodeOut:
        return self.buildOp(AllOps.NOT, a._dtype, a)
    
    def buildMux(self, resT: HdlType, operands: Tuple[Union[HlsNetNodeOut, HValue]]):
        assert operands, "MUX has to have at least a single input"
        key = (AllOps.TERNARY, operands)
        try:
            return self.operatorCache[key]
        except KeyError:
            pass
        # if there are constants in operands try to search them as well
        # variant of the key where all constants are converted to HValue
        operandsWithHValues = tuple(self._outputOfConstNodeToHValue(o) for o in operands)
        keyWithHValues = (AllOps.TERNARY, operandsWithHValues)
        try:
            return self.operatorCache[keyWithHValues]
        except KeyError:
            pass

        operandsWithOutputsOnly = tuple(self._toNodeOut(o) for o in operands)
        
        n = HlsNetNodeMux(self.netlist, resT)
        self.netlist.nodes.append(n)
        for (src, cond) in grouper(2, operandsWithOutputsOnly):
            i = n._add_input()
            link_hls_nodes(src, i)
            if cond is not None:
                i = n._add_input()
                link_hls_nodes(cond, i)
        
        o = n._outputs[0]
        self.operatorCache[keyWithHValues] = o
        return o

    def buildConcat(self, lsbs: Union[HlsNetNodeOut, HValue], msbs: Union[HlsNetNodeOut, HValue]) -> HlsNetNodeOut:
        return self.buildOp(AllOps.CONCAT, Bits(lsbs._dtype.bit_length() + msbs._dtype.bit_length()), lsbs, msbs)

    def buildConcatVariadic(self, ops: Tuple[Union[HlsNetNodeOut, HValue], ...]):
        """
        :param ops: operands to concatenate, lower bits first 
        """
        assert ops, "Must have operands because the output can not be void"
        res = None
        for o in ops:
            if res is None:
                res = o
            else:
                res = self.buildConcat(res, o)
        return res
    
    def buildSignCast(self, o: HlsNetNodeOut, signed: Optional[bool]) -> HlsNetNodeOut:
        if signed:
            op = AllOps.BitsAsSigned
        elif signed is None:
            op = AllOps.BitsAsVec
        else:
            op = AllOps.BitsAsUnsigned

        return self.buildOp(op, Bits(o._dtype.bit_length(), signed=signed), o)
        
    def buildIndexConstSlice(self, resT: HdlType, a: HlsNetNodeOut, high: int, low: int):
        assert high > low, (high, low)
        i = self.buildConst(SLICE.from_py(slice(high, low, -1)))
        return self.buildOp(AllOps.INDEX, resT, a, i)

    def _getOperatorCacheKey(self, obj: HlsNetNodeOperator):
        return (obj.operator, tuple(self._outputOfConstNodeToHValue(o) for o in obj.dependsOn))

    def _replaceInputWithConst1b(self, i: HlsNetNodeIn):
        c = self.buildConstBit(1)
        isOp = isinstance(i.obj, HlsNetNodeOperator)
        if isOp:
            self.unregisterOperatorNode(i.obj)

        i.replace_driver(c)
        if isOp:
            self.registerOperatorNode(i.obj)

        return c

    def replaceOutput(self, o: HlsNetNodeOutAny, newO: HlsNetNodeOutAny):
        if isinstance(o, HlsNetNodeOut):
            uses = o.obj.usedBy[o.out_i]
        else:
            assert isinstance(o, HlsNetNodeOutLazy), o
            o: HlsNetNodeOutLazy
            uses = o.dependent_inputs
        
        for i in uses:
            i: HlsNetNodeIn
            dependsOn = i.obj.dependsOn
            assert dependsOn[i.in_i] is o, (dependsOn[i.in_i], o)
            isOp = isinstance(i.obj, HlsNetNodeOperator)
            if isOp:
                self.unregisterOperatorNode(i.obj)
            
            i.replaceDriverInInputOnly(newO)
            if isOp:
                self.registerOperatorNode(i.obj)

        uses.clear()

    def unregisterNode(self, n: HlsNetNode):
        if isinstance(n, HlsNetNodeOperator):
            self.unregisterOperatorNode(n)

    def unregisterOperatorNode(self, n: HlsNetNodeOperator):
        k = tuple(self._getOperatorCacheKey(n))
        v = self.operatorCache.pop(k)
        assert v is n._outputs[0], (v, n)

    def registerNode(self, n):
        if isinstance(n, HlsNetNodeOperator):
            self.registerOperatorNode(n)

    def registerOperatorNode(self, n: HlsNetNodeOperator):
        k = tuple(self._getOperatorCacheKey(n))
        self.operatorCache[k] = n._outputs[0]
              
