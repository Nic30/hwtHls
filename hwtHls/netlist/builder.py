
from itertools import islice
from typing import Tuple, Union, Dict, Optional, Type, Callable, Set, List

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import OpDefinition, AllOps, CAST_OPS
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT, SLICE, INT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import grouper, balanced_reduce
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, \
    HlsNetNodeIn, HlsNetNodeOutLazy, HlsNetNodeOutAny, unlink_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.observableList import ObservableList
from hwtHls.netlist.transformation.simplifyUtils import getConstOfOutput
from hwt.pyUtils.uniqList import UniqList


class HlsNetlistBuilder():
    """
    This class can be used to build HlsNetNodes is uses structural hashing for :class:`HlsNetNodeOperator` instances.
    This means that the same operator and operands always yields the same output object.

    :note: constant nodes are always unique nodes and structural hashing does not apply to them.
        (But operator nodes with const operands will yield always the same output object.)
    :note: Constant operands are always store in operatorCache key as a HValue and output of HlsNetNodeConst is never used.
    :ivar _removedNodes: optional set of removed nodes used to discard records from the operatorCache
    """

    def __init__(self, netlist: HlsNetlistCtx, netlistNodes: Optional[ObservableList[HlsNetNode]]=None):
        self.netlist = netlist
        if netlistNodes is None:
            netlistNodes = netlist.nodes
        self.netlistNodes = netlistNodes
        self.operatorCache: Dict[Tuple[Union[OpDefinition, Type[HlsNetNode]],
                                       Tuple[Union[HlsNetNodeOut, HValue], ...]],
                                 HlsNetNodeOut] = {}
#        class ObservableSet(set):
#            def add(self, n):
#                super(ObservableSet, self).add(n)
#        self._removedNodes: Set[HlsNetNode] = ObservableSet()
        self._removedNodes: Set[HlsNetNode] = set()

    def _outputOfConstNodeToHValue(self, o: Union[HlsNetNodeOut, HValue]):
        if isinstance(o, (HValue, HlsNetNodeOutLazy)):
            return o
        else:
            assert isinstance(o, HlsNetNodeOut), o

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
        c = HlsNetNodeConst(self.netlist, v)
        self.netlistNodes.append(c)
        return c._outputs[0]

    def buildConstBit(self, v: int):
        return self.buildConst(BIT.from_py(v))

    def _tryToFindInCache(self, operator: OpDefinition, operands: Tuple[Union[HlsNetNodeOut, HValue], ...]):
        key = (operator, operands)
        rm = self._removedNodes
        opCache = self.operatorCache

        v = opCache.get(key, None)
        if v is not None:
            if v.obj in rm:
                opCache.pop(key)
            else:
                return v, None
        # if there are constants in operands try to search them as well
        # variant of the key where all constants are converted to HValue
        operandsWithHValues = tuple(self._outputOfConstNodeToHValue(o) for o in operands)
        keyWithHValues = (operator, operandsWithHValues)
        v = opCache.get(keyWithHValues, None)
        if v is not None:
            if v.obj in rm:
                opCache.pop(keyWithHValues)
            else:
                return v, None

        return None, keyWithHValues

    def buildOp(self,
                operator: OpDefinition,
                resT: HdlType,
                *operands: Tuple[Union[HlsNetNodeOut, HValue], ...],
                name:Optional[str]=None,
                worklist: Optional[UniqList[HlsNetNode]]=None) -> HlsNetNodeOut:
        assert operator not in {AllOps.DIV, AllOps.GT, AllOps.GE, AllOps.LT, AllOps.LE}, ("Signed or unsigned variant should be used instead", operator, operands)
        assert operator not in CAST_OPS, ("Internally there is no cast required", operator, operands)
        assert not isinstance(resT, Bits) or not resT.signed, ("Only unsigned should be used internally", resT)
        res, keyWithHValues = self._tryToFindInCache(operator, operands)
        if res is not None:
            if worklist is not None:
                for o in operands:
                    if isinstance(o, HlsNetNodeOut):
                        worklist.append(o.obj)

            return res

        operandsWithOutputsOnly = tuple(self._toNodeOut(o) for o in operands)

        n = HlsNetNodeOperator(self.netlist, operator, len(operands), resT, name=name)
        self.netlistNodes.append(n)
        for i, arg in zip(n._inputs, operandsWithOutputsOnly):
            link_hls_nodes(arg, i)

        o = n._outputs[0]
        self.operatorCache[keyWithHValues] = o
        if operator is AllOps.NOT:
            # if operator is NOT automatically precompute not not x to x
            self.operatorCache[(AllOps.NOT, o)] = keyWithHValues[1][0]

        return o

    def buildOpWithOpt(self, operator: OpDefinition, resT: HdlType, *operands: Tuple[Union[HlsNetNodeOut, HValue], ...]) -> HlsNetNodeOut:
        if operator == AllOps.EQ:
            assert resT == BIT, resT
            return self.buildEq(*operands)
        elif operator == AllOps.NE:
            assert resT == BIT, resT
            return self.buildNe(*operands)

        elif operator == AllOps.ULT:
            assert resT == BIT, resT
            return self.buildULt(*operands)
        elif operator == AllOps.ULE:
            assert resT == BIT, resT
            return self.buildULe(*operands)
        elif operator == AllOps.UGT:
            assert resT == BIT, resT
            return self.buildUGt(*operands)
        elif operator == AllOps.UGE:
            assert resT == BIT, resT
            return self.buildUGe(*operands)

        elif operator == AllOps.SLT:
            assert resT == BIT, resT
            return self.buildSLt(*operands)
        elif operator == AllOps.SLE:
            assert resT == BIT, resT
            return self.buildSLe(*operands)
        elif operator == AllOps.SGT:
            assert resT == BIT, resT
            return self.buildSGt(*operands)
        elif operator == AllOps.SGE:
            assert resT == BIT, resT
            return self.buildSGe(*operands)

        elif operator == AllOps.AND:
            assert resT == operands[0]._dtype, (resT, operands[0]._dtype)
            return self.buildAndVariadic(operands)
        elif operator == AllOps.OR:
            assert resT == operands[0]._dtype, (resT, operands[0]._dtype)
            return self.buildOrVariadic(operands)
        elif operator == AllOps.NOT:
            return self.buildNot(*operands)
        else:
            return self.buildOp(operator, resT, *operands)

    def buildEq(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        assert a._dtype == b._dtype, (a, b)
        if a is b:
            return self.buildConstBit(1)
        return self.buildOp(AllOps.EQ, BIT, a, b)

    def buildNe(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        assert a._dtype == b._dtype, (a, b)
        if a is b:
            return self.buildConstBit(0)
        return self.buildOp(AllOps.NE, BIT, a, b)

    def buildULt(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildLt(AllOps.ULT, a, b)

    def buildSLt(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildLt(AllOps.SLT, a, b)

    def buildLt(self, op: OpDefinition, a: HlsNetNodeOut, b: HlsNetNodeOut):
        assert a._dtype == b._dtype, (a, b)
        assert op in (AllOps.ULT, AllOps.SLT)
        if a is b:
            return self.buildConstBit(0)
        return self.buildOp(op, BIT, a, b)

    def buildULe(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildLe(AllOps.ULE, a, b)

    def buildSLe(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildLe(AllOps.SLE, a, b)

    def buildLe(self, op: OpDefinition, a: HlsNetNodeOut, b: HlsNetNodeOut):
        assert a._dtype == b._dtype, (a, b)
        assert op in (AllOps.ULE, AllOps.SLE)
        if a is b:
            return self.buildConstBit(1)
        return self.buildOp(op, BIT, a, b)

    def buildUGt(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildGt(AllOps.UGT, a, b)

    def buildSGt(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildGt(AllOps.SGT, a, b)

    def buildGt(self, op: OpDefinition, a: HlsNetNodeOut, b: HlsNetNodeOut):
        assert a._dtype == b._dtype, (a, b)
        assert op in (AllOps.UGT, AllOps.SGT)
        if a is b:
            return self.buildConstBit(0)
        return self.buildOp(op, BIT, a, b)

    def buildUGe(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildGe(AllOps.UGE, a, b)

    def buildSGe(self, a: HlsNetNodeOut, b: HlsNetNodeOut):
        return self.buildGe(AllOps.SGE, a, b)

    def buildGe(self, op: OpDefinition, a: HlsNetNodeOut, b: HlsNetNodeOut):
        assert a._dtype == b._dtype, (a, b)
        assert op in (AllOps.UGE, AllOps.SGE)
        if a is b:
            return self.buildConstBit(1)
        return self.buildOp(op, BIT, a, b)

    def buildRom(self, data: Union[Dict[int, HValue], List[HValue], Tuple[HValue]], index: HlsNetNodeOut):
        assert data, ("ROM array should not be of zero size", data)
        itemCnt = 2 ** index._dtype.bit_length()

        if isinstance(data, dict):
            for d in data.values():
                resT = d._dtype
                break
            if len(data) == itemCnt:
                data = tuple(data[i] for i in range(itemCnt))
        elif not isinstance(data, tuple):
            data = tuple(data)
            resT = data[0]._dtype
        data = resT[itemCnt].from_py(data)
        return self.buildOp(AllOps.INDEX, resT, data, index)

    def buildAndVariadic(self, ops: Tuple[Union[HlsNetNodeOut, HValue], ...], name:Optional[str]=None):
        return balanced_reduce(ops, lambda a, b: self.buildAnd(a, b, name=name))

    def buildOrVariadic(self, ops: Tuple[Union[HlsNetNodeOut, HValue], ...], name:Optional[str]=None):
        return balanced_reduce(ops, lambda a, b: self.buildOr(a, b, name=name))

    def buildAnd(self, a: Union[HlsNetNodeOut, HValue], b:Union[HlsNetNodeOut, HValue], name:Optional[str]=None) -> HlsNetNodeOut:
        assert a._dtype == b._dtype, (a, b, a._dtype, b._dtype)
        if a is b or isinstance(a, HlsNetNodeOut) and\
                isinstance(a.obj, HlsNetNodeOperator) and\
                a.obj.operator == AllOps.AND and\
                (a.obj.dependsOn[0] is b or a.obj.dependsOn[1] is b):
            return a
        for op0, other in ((a, b), (b, a)):
            if isinstance(op0, HlsNetNodeConst):
                op0 = op0.val

            if isinstance(op0, HValue) and op0._is_full_valid():
                if op0._eq(op0._dtype.all_mask()):
                    if isinstance(other, HValue):
                        c = HlsNetNodeConst(self.netlist, other)
                        self.netlistNodes.append(c)
                        return c._outputs[0]
                    else:
                        return other
                elif op0._eq(0):
                    c = HlsNetNodeConst(self.netlist, op0._dtype.from_py(0))
                    self.netlistNodes.append(c)
                    return c._outputs[0]

        return self.buildOp(AllOps.AND, a._dtype, a, b, name=name)

    def buildAndOptional(self, a: Optional[Union[HlsNetNodeOut, HValue]], b: Optional[Union[HlsNetNodeOut, HValue]])\
            ->Union[HlsNetNodeOut, HValue, None]:
        if a is None:
            return b
        elif b is None or b is a:
            return a
        else:
            return self.buildAnd(a, b)

    def buildOr(self, a: Union[HlsNetNodeOut, HValue], b:Union[HlsNetNodeOut, HValue], name:Optional[str]=None) -> HlsNetNodeOut:
        assert a._dtype == b._dtype, (a, b, a._dtype, b._dtype)
        if isinstance(a, HlsNetNodeOut) and\
                isinstance(a.obj, HlsNetNodeOperator) and\
                a.obj.operator == AllOps.OR and\
                (a.obj.dependsOn[0] is b or a.obj.dependsOn[1] is b):
            return a

        for op0, other in ((a, b), (b, a)):
            if isinstance(op0, HlsNetNodeConst):
                op0 = op0.val

            if isinstance(op0, HValue) and op0._is_full_valid():
                if op0._eq(0):
                    if isinstance(other, HValue):
                        c = HlsNetNodeConst(self.netlist, other)
                        self.netlistNodes.append(c)
                        return c._outputs[0]
                    else:
                        return other
                elif op0._eq(op0._dtype.all_mask()):
                    c = HlsNetNodeConst(self.netlist, op0._dtype.from_py(op0._dtype.all_mask()))
                    self.netlistNodes.append(c)
                    return c._outputs[0]

        return self.buildOp(AllOps.OR, a._dtype, a, b, name=name)

    def buildOrOptional(self, a: Optional[Union[HlsNetNodeOut, HValue]], b: Optional[Union[HlsNetNodeOut, HValue]])\
            ->Union[HlsNetNodeOut, HValue, None]:
        if a is None:
            if b is None:
                return None
            else:
                return b
        else:
            if b is None or a is b:
                return a
            else:
                return self.buildOr(a, b)

    def buildNot(self, a: Union[HlsNetNodeOut, HValue]) -> HlsNetNodeOut:
        if isinstance(a, HlsNetNodeOut) and isinstance(a.obj, HlsNetNodeOperator) and a.obj.operator == AllOps.NOT:
            return a.obj.dependsOn[0]
        return self.buildOp(AllOps.NOT, a._dtype, a)

    def buildMux(self, resT: HdlType, operands: Tuple[Union[HlsNetNodeOut, HValue]], name:Optional[str]=None):
        """
        :param operands: operands in format of val0, (condN, valN)*
        """
        assert operands, "MUX has to have at least a single input"
        res, keyWithHValues = self._tryToFindInCache(AllOps.TERNARY, operands)
        if res is not None:
            return res

        operandsWithOutputsOnly = tuple(self._toNodeOut(o) for o in operands)
        opLen = len(operands)
        if opLen == 1:
            return operands[0]  # there is only a single value
        elif opLen % 2 == 1:
            v0 = operands[0]
            for last, (src, cond) in iter_with_last(grouper(2, operandsWithOutputsOnly)):
                if src is not v0:
                    break
                if last:
                    return v0  # all cases have same value

            if opLen == 3 and resT.bit_length() == 1:
                v0, c, v1 = operands
                v0 = getConstOfOutput(v0)
                if v0 is not None and v0._is_full_valid():
                    v0 = int(v0)
                    v1 = getConstOfOutput(v1)
                    if v1 is not None and v1._is_full_valid():
                        v1 = int(v1)
                        if v0 and not v1:
                            # res = 1 if c else 0  -> res = c
                            return c
                        elif not v0 and v1:
                            # res = 0 if c else 1  -> res = ~c
                            return self.buildNot(c)

        n = HlsNetNodeMux(self.netlist, resT, name=name)
        self.netlistNodes.append(n)
        for (src, cond) in grouper(2, operandsWithOutputsOnly):
            assert src._dtype == resT, (src, resT, src._dtype)
            i = n._addInput(f"v{len(n._inputs) // 2}")
            link_hls_nodes(src, i)
            if cond is not None:
                assert cond._dtype == BIT, (cond, cond._dtype)
                i = n._addInput(f"c{(len(n._inputs) - 1) // 2}")
                link_hls_nodes(cond, i)

        o = n._outputs[0]
        self.operatorCache[keyWithHValues] = o
        return o

    def buildConcat(self, *lsbToMsbOps: Union[HlsNetNodeOut, HValue]) -> HlsNetNodeOut:
        """
        :param lsbToMsbOps: operands to concatenate, lower bits first
        """
        if len(lsbToMsbOps) == 1:
            return lsbToMsbOps[0]
        else:
            assert lsbToMsbOps, "Needs at least one argument"

        lsbs = lsbToMsbOps[0]
        if HdlType_isVoid(lsbs._dtype):
            t = lsbs._dtype
            for other in islice(lsbToMsbOps, 1, None):
                assert t == other._dtype, ("If this is a concatenation of void types, all ops must be of same type",
                                           t, other._dtype, other, lsbToMsbOps)
        else:
            w = 0
            for o in lsbToMsbOps:
                w += o._dtype.bit_length()
            t = Bits(w)
        return self.buildOp(AllOps.CONCAT, t, *lsbToMsbOps)

    def buildIndexConst(self, resT: HdlType, a: HlsNetNodeOut, high: int, low: Optional[int], worklist: UniqList[HlsNetNode]):
        if resT == a._dtype:
            return a
        elif high == low + 1:
            high = low
            low = None
        return self.buildIndexConstSlice(resT, a, high, low, worklist)

    def buildIndexConstSlice(self, resT: HdlType, a: HlsNetNodeOut, high: int, low: Optional[int], worklist: UniqList[HlsNetNode]):
        if low is None:
            assert resT == BIT, resT
            i = self.buildConst(INT.from_py(high))
        else:
            assert high > low, (high, low)
            i = self.buildConst(SLICE.from_py(slice(high, low, -1)))

        return self.buildOp(AllOps.INDEX, resT, a, i, worklist=worklist)

    def buildReadSync(self, i: HlsNetNodeOutAny):
        isResolvedOut = False
        if isinstance(i, HlsNetNodeOut) and isinstance(i.obj, HlsNetNodeExplicitSync):
            if isinstance(i.obj, (HlsNetNodeRead, HlsNetNodeWrite)):
                return i.obj.getValidNB()

            n = i.obj._associatedReadSync
            if n is not None:
                return n._outputs[0]
            isResolvedOut = True

        n = HlsNetNodeReadSync(self.netlist)
        self.netlistNodes.append(n)
        link_hls_nodes(i, n._inputs[0])
        o = n._outputs[0]
        if isResolvedOut:
            i.obj._associatedReadSync = n

        return o

    def _getOperatorCacheKey(self, obj: HlsNetNodeOperator):
        return (obj.operator, tuple(self._outputOfConstNodeToHValue(o) for o in obj.dependsOn))

    def _replaceInputDriverWithConst1b(self, i: HlsNetNodeIn):
        c = self.buildConstBit(1)
        isOp = isinstance(i.obj, HlsNetNodeOperator)
        if isOp:
            self.unregisterOperatorNode(i.obj)

        i.replaceDriver(c)
        if isOp:
            self.registerOperatorNode(i.obj)

        return c

    def replaceInputDriver(self, i: HlsNetNodeIn, newO: HlsNetNodeOutAny):
        """
        Replace output connected to specified input.
        """
        if isinstance(newO, HlsNetNodeOut):
            assert i.obj is not newO.obj, (i, newO)
        isOp = isinstance(i.obj, HlsNetNodeOperator)
        if isOp:
            self.unregisterOperatorNode(i.obj)

        i.replaceDriver(newO)
        if isOp:
            self.registerOperatorNode(i.obj)

    def replaceOutputWithConst1b(self, o: HlsNetNodeOut, updateCache: bool):
        c = self.buildConstBit(1)
        return self.replaceOutput(o, c, updateCache)

    def replaceOutput(self, o: HlsNetNodeOutAny, newO: HlsNetNodeOutAny, updateCache: bool):
        """
        Replace all uses of this output port.
        """
        assert o._dtype == newO._dtype, (o, newO, o._dtype, newO._dtype)
        assert o is not newO, ("It is pointless to replace to the same", o)
        if isinstance(o, HlsNetNodeOut):
            _uses = o.obj.usedBy[o.out_i]
        else:
            assert isinstance(o, HlsNetNodeOutLazy), o
            o: HlsNetNodeOutLazy
            _uses = o.dependent_inputs

        uses = tuple(_uses)
        _uses.clear()
        for i in uses:
            i: HlsNetNodeIn
            assert i.obj is not newO.obj, ("Can not create a cycle in netlist DAG", i, newO)
            dependsOn = i.obj.dependsOn
            assert dependsOn[i.in_i] is o, (dependsOn[i.in_i], o)
            if updateCache:
                isOp = isinstance(i.obj, HlsNetNodeOperator)
                if isOp:
                    self.unregisterOperatorNode(i.obj)

            i.replaceDriverInInputOnly(newO)
            if updateCache:
                if isOp:
                    self.registerOperatorNode(i.obj)

    def replaceOutputIf(self, o: HlsNetNodeOutAny, newO: HlsNetNodeOutAny, selector: Callable[[HlsNetNodeIn], bool]) -> bool:
        """
        Replace all uses of this output port.
        """
        if o is newO:
            return False

        if isinstance(o, HlsNetNodeOut):
            uses = o.obj.usedBy[o.out_i]

        else:
            assert isinstance(o, HlsNetNodeOutLazy), o
            o: HlsNetNodeOutLazy
            uses = o.dependent_inputs

        newUses = []
        usesToReplace = []
        for i in uses:
            i: HlsNetNodeIn
            assert i.obj is not newO.obj, (i, newO)
            if selector(i):
                usesToReplace.append(i)
            else:
                newUses.append(i)

        if not usesToReplace:
            return False

        uses.clear()
        uses.extend(newUses)

        for i in usesToReplace:
            i: HlsNetNodeIn
            dependsOn = i.obj.dependsOn
            assert dependsOn[i.in_i] is o, (dependsOn[i.in_i], o)
            isOp = isinstance(i.obj, HlsNetNodeOperator)
            if isOp:
                self.unregisterOperatorNode(i.obj)

            i.replaceDriverInInputOnly(newO)
            if isOp:
                self.registerOperatorNode(i.obj)

        return True

    def moveSimpleSubgraph(self, i: HlsNetNodeIn, o: HlsNetNodeOut, insertO: HlsNetNodeOut, insertI: HlsNetNodeIn):
        """
        | ....x0| -> |i o| -> |x1 ... insertO| -> |insertI ...|
        to
        | ....x0| -> |x1 ... insertO| -> |i o| -> |insertI ...|

        """
        x0 = i.obj.dependsOn[i.in_i]
        unlink_hls_nodes(x0, i)
        self.replaceOutput(o, x0, True)
        # oUsers = tuple(o.obj.usedBy[o.out_i])
        self.insertBetween(i, o, insertO, insertI)

    def insertBetween(self, i: HlsNetNodeIn, o: HlsNetNodeOut, insertO: HlsNetNodeOut, insertI: HlsNetNodeIn):
        self.replaceOutputIf(insertO, o, lambda i1: i1 is insertI)
        link_hls_nodes(insertO, i)

    def unregisterNode(self, n: HlsNetNode):
        if isinstance(n, HlsNetNodeOperator):
            self.unregisterOperatorNode(n)

    def unregisterOperatorNode(self, n: HlsNetNodeOperator):
        k = tuple(self._getOperatorCacheKey(n))
        try:
            v = self.operatorCache[k]
        except KeyError:
            return

        if v is n._outputs[0]:
            # there may be the temporary case when some operand is replaced
            # and the operator node becomes something which already exits
            self.operatorCache.pop(k)

    def registerNode(self, n):
        if isinstance(n, HlsNetNodeOperator):
            self.registerOperatorNode(n)

    def registerOperatorNode(self, n: HlsNetNodeOperator):
        k = tuple(self._getOperatorCacheKey(n))
        if k not in self.operatorCache:
            # there may be the temporary case when some operand is replaced
            # and the operator node becomes something which already exits
            self.operatorCache[k] = n._outputs[0]

    def scoped(self, parent: "HlsNetNodeAggregate"):
        scopedBuilder: HlsNetlistBuilder = self.__class__(
            self.netlist, netlistNodes=parent._subNodes
        )
        scopedBuilder._removedNodes = self._removedNodes
        return scopedBuilder
