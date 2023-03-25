from itertools import islice
from typing import Set, Sequence, Optional, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps, CMP_OPS_NEG, COMPARE_OPS, OpDefinition
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.transformation.simplifyExpr.cmpInAndUtils import ValueConstrainLatice, \
    _appendKnowledgeTwoVars, _appendKnowledgeVarAndConst, \
    _intervalListIntersection
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith, \
    iterOperatorTreeInputs, popNotFromExpr
from pyMathBitPrecise.bit_utils import mask


def _and(a: Optional[HlsNetNodeOut], b: HlsNetNodeOut):
    if a is None:
        return b
    else:
        return b.obj.netlist.builder.buildAnd(a, b)


def _or(a: Optional[HlsNetNodeOut], b: HlsNetNodeOut):
    if a is None:
        return b
    else:
        return b.obj.netlist.builder.buildOr(a, b)


DIRECT_CMP_PROFITABLE_TO_EXTRACT = 2


def _andNotInRangeExpr(curExpr: Optional[HlsNetNodeOut], inp: HlsNetNodeOut, start: int, stop: int, _min:int, _max: int) -> HlsNetNodeOut:
    """
    Generates expr: curExpr & not inRange(inp, start, stop)
    """

    b: HlsNetlistBuilder = inp.obj.netlist.builder
    intervLen = stop - start
    t = inp._dtype
    if intervLen <= DIRECT_CMP_PROFITABLE_TO_EXTRACT:
        for n in range(start, stop):
            e = b.buildNot(b.buildEq(inp, t.from_py(n)))
            curExpr = _and(curExpr, e)
    else:
        assert start < _max
        e = None
        if start > _min:
            _e = b.buildGt(inp, t.from_py(start - 1))
            e = _and(e, _e)

        if stop < _max + 1:
            _e = b.buildLt(inp, t.from_py(stop))
            e = _and(e, _e)
        assert e is not None
        curExpr = _and(curExpr, b.buildNot(e))

    return curExpr


def _valueLaticeToExpr(b: HlsNetlistBuilder, allInputs: Sequence[HlsNetNodeOut], latice: ValueConstrainLatice):
    """
    Rewrite value latice to the expression.
    """
    inputs = sorted(allInputs, key=lambda x: (x.obj._id, x.out_i))
    res = None
    for i, inp in enumerate(inputs):
        valConstr = latice.get((inp, inp))
        if valConstr is not None:
            t = inp._dtype
            width = inp._dtype.bit_length()
            if inp._dtype.signed:
                raise NotImplementedError()
            else:
                _min = 0
                _max = mask(width)

#            for r in enumerate(valConstr):

            if len(valConstr) == 1:
                r = valConstr[0]
                if r.start == _min and r.stop == _max + 1:
                    # covers whole domain, this can have any value so we skip it
                    # :note: this should already be handled in opt phase
                    continue

                elif len(r) == 1:
                    # inp == c0
                    if t == BIT:
                        # prevent redundant eq
                        if r.start:
                            e = inp
                        else:
                            e = b.buildNot(inp)
                    else:
                        e = b.buildEq(inp, t.from_py(r.start))

                    res = _and(res, e)

                elif r.start == _min:
                    # inp < c0
                    e = b.buildOp(AllOps.LT, BIT, inp, t.from_py(r.stop))
                    res = _and(res, e)

                elif r.stop == _max + 1:
                    # inp > c0
                    e = b.buildOp(AllOps.GT, BIT, inp, t.from_py(r.start - 1))
                    res = _and(res, e)

                elif len(r) == DIRECT_CMP_PROFITABLE_TO_EXTRACT:
                    # inp == c0 or inp == c1
                    e = None
                    for n in (r.start, r.stop):
                        _e = b.buildEq(inp, t.from_py(n))
                        e = _or(e, _e)
                    res = _and(res, e)

                else:
                    # inp > c0 and inp < c1
                    e = b.buildOp(AllOps.GT, BIT, inp, t.from_py(r.start - 1))
                    res = _and(res, e)
                    e = b.buildOp(AllOps.LT, BIT, inp, t.from_py(r.stop))
                    res = _and(res, e)

            elif len(valConstr) == 2:
                r0, r1 = valConstr
                if r1.start - r0.stop <= DIRECT_CMP_PROFITABLE_TO_EXTRACT:
                    # some interval and inp != c
                    for n in range(r0.stop, r1.start):
                        e = b.buildNot(b.buildEq(inp, t.from_py(n)))
                        res = _and(res, e)
                if r1.stop < _max + 1:
                    e = b.buildOp(AllOps.LT, BIT, inp, t.from_py(r1.stop))
                    res = _and(res, e)

                if r0.start > _min:
                    e = b.buildOp(AllOps.GT, BIT, inp, t.from_py(r0.start))
                    res = _and(res, e)

            else:
                # create "and" where each member is negation of interval between intervals defined in valConstr

                # used to get next item
                valConstrIt = iter(valConstr)
                try:
                    # skip first item
                    next(valConstrIt)
                except StopIteration:
                    raise AssertionError("valConstr should have 3 or more items, now it seems that it has 0")
                isFirst = True
                for isLast, r in iter_with_last(valConstr):
                    if isFirst:
                        isFirst = False
                        if r.start != _min:
                            res = _andNotInRangeExpr(res, inp, _min, r.start, _min, _max)

                    if isLast:
                        rNext = None
                        if r.stop != _max + 1:
                            res = _andNotInRangeExpr(res, inp, r.stop, _max + 1, _min, _max)
                    else:
                        rNext = next(valConstrIt)
                        res = _andNotInRangeExpr(res, inp, r.stop, rNext.start, _min, _max)

        for otherInp in islice(inputs, i + 1, None):
            constr = latice.get((inp, otherInp))
            if constr is None:
                continue
            else:
                assert isinstance(constr, OpDefinition), constr
                e = b.buildOp(constr, BIT, inp, otherInp)
                res = _and(res, e)

    if res is None:
        return b.buildConstBit(0)
    else:
        return res


def getOperatorOfExpr(p: Union[HlsNetNodeOut, HlsNetNodeIn]):
    if not isinstance(p.obj, HlsNetNodeOperator):
        return None
    else:
        return  p.obj.operator


def getConst(o: HlsNetNodeOut):
    if isinstance(o.obj, HlsNetNodeConst):
        return int(o.obj.val)
    else:
        return None


def netlistReduceCmpInAnd(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    """
    This algorithm simplifies comparations in AND tree. It is similar to Sparse Conditional Constant Propagation (SCC).
    """
    assert n.operator is AllOps.AND, n
    assert n._outputs[0]._dtype.bit_length() == 1, (n, n._outputs[0]._dtype)
    knownResult = None
    allUsersAreAnd = True
    for u in n.usedBy[0]:
        if getOperatorOfExpr(u) is not AllOps.AND:
            allUsersAreAnd = False
            break

    if allUsersAreAnd:
        # optimize later from some parent
        return False

    b: HlsNetlistCtx = n.netlist.builder

    # sorted list of allowed ranges for each input variable (which is realized as node output)
    # values: ValueConstrainLatice = {}
    # equalGroups: Dict[HlsNetNodeOut, Set[HlsNetNodeOut]] = {}
    # a dictionary mapping relations between input variables in oposite direction to "values"
    # varDeps: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
    latice: ValueConstrainLatice = {}
    allInputs: UniqList[HlsNetNodeOut] = UniqList()
    registerInput = allInputs.append
    changed = False
    inputs = tuple(iterOperatorTreeInputs(n, AllOps.AND))
    for inp in inputs:
        inp: HlsNetNodeOut
        negated, inpO, inp = popNotFromExpr(inp)

        if isinstance(inpO, HlsNetNodeOperator):
            o = inpO.operator
            if o in COMPARE_OPS:
                o0, o1 = inpO.dependsOn
                if negated:
                    o = CMP_OPS_NEG[o]

                # if it is a constant, mark constant
                c0 = getConst(o0)
                c1 = getConst(o1)

                if c0 is not None and c1 is not None:
                    changed = True
                    if not o._evalFn(c0, c1):
                        # discovered 0 in "and" tree, whole result is 0
                        knownResult = False
                        break
                    else:
                        # discovered just 1 in "and" tree, it is not important
                        continue

                elif c0 is not None:
                    # change to have value as a first operand
                    c0, c1 = c1, c0
                    o0, o1 = o1, o0

                if c1 is None:
                    changed = True
                    registerInput(o0)
                    registerInput(o1)
                    knownResult, _changed = _appendKnowledgeTwoVars(latice, o, o0, o1)
                else:
                    registerInput(o0)
                    knownResult, _changed = _appendKnowledgeVarAndConst(latice, o, o0, c1)

                changed |= _changed
                if knownResult is not None:
                    break
                continue

        registerInput(inp)
        k = (inp, inp)
        curV = latice.get(k, None)
        if negated:
            ranges = [range(0, 1)]
        else:
            ranges = [range(1, 2)]
        if curV is not None:
            ranges = list(_intervalListIntersection(curV, ranges))
        latice[k] = ranges

    if knownResult is not None:
        replaceOperatorNodeWith(n, b.buildConstBit(knownResult), worklist, removed)
        return True
    elif not changed:
        return False
    else:
        replacement = _valueLaticeToExpr(b, allInputs, latice)
        if replacement is n._outputs[0]:
            return False
        else:
            replaceOperatorNodeWith(n, replacement, worklist, removed)
            return True
