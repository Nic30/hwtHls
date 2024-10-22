from typing import Dict, Union, Tuple, List, Optional

from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.hdl.const import HConst
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from pyMathBitPrecise.bit_utils import mask, to_unsigned

# matrix variables X variables,
# value range may appear on diagonal
# None means no knowledge available
# :attention: because bottom-left triangle is only negation of top-right triangle, only top-right is present,
#      variables are ordered "see: _:func:`~._appendKnowledgeTwoVars`
#
ValueConstrainLattice = Dict[HlsNetNodeOut,
                 Union[
                    HOperatorDef,  # compare operator
                    Tuple[int, int],
                    None,
                 ]
                 ]

CMP_WITH_EQ = (HwtOps.EQ,
               HwtOps.ULE, HwtOps.UGE,
               HwtOps.SLE, HwtOps.SGE)
# :note: used to sort operators to reduce number of compares for the operator strength
OP_STRENGTH = {
    HwtOps.EQ: 6,
    HwtOps.NE: 5,
    HwtOps.ULT: 4,
    HwtOps.UGT: 3,
    HwtOps.ULE: 2,
    HwtOps.UGE: 1,

    HwtOps.SLT: 4,
    HwtOps.SGT: 3,
    HwtOps.SLE: 2,
    HwtOps.SGE: 1,
}


def _appendKnowledgeTwoVars(lattice: ValueConstrainLattice, rel: HOperatorDef, o0: HlsNetNodeOut, o1: HlsNetNodeOut) -> Tuple[Optional[bool], bool]:
    """
    This function updates the knowledge in lattice from binary relation operator

    :param lattice: lattice object where knowledge about relations between variables is stored
    :param rel: relation operator for specification of new knowledge
    :param o0: operand0 for specification of new knowledge
    :param o1: operand0 for specification of new knowledge
    :returns: known value bits, flag which is true if knowledge changed
    """
    if o0 is o1:
        if rel in CMP_WITH_EQ:
            # always 1 => does not affect reulst of whole AND tree
            return None, True
        else:
            # always 0 => whole AND result will be 0
            return False, True

    if (o0.obj._id, o0.out_i) > (o1.obj._id, o1.out_i):
        o0, o1 = o1, o0

    k = (o0, o1)
    curRel = lattice.get(k, None)
    if curRel is None:
        # newly obtained knowledge about rel between o0 and o1
        lattice[k] = rel
        return None, False
    else:
        if curRel is rel:
            return None, False

        r0 = curRel
        r1 = rel
        if OP_STRENGTH[r1] > OP_STRENGTH[r0]:
            r0, r1 = r1, r0
        raise NotImplementedError()
        # straighten the relation if necessary
        if r0 is HwtOps.EQ:
            if r1 in CMP_WITH_EQ:
                rel = HwtOps.EQ
            else:
                # always 0
                return False, True

        elif r0 is HwtOps.NE:
            if r1 is HwtOps.EQ:
                # always 0
                return False, True
            elif r1 is HwtOps.ULE:
                rel = HwtOps.ULT
            elif r1 is HwtOps.SLE:
                rel = HwtOps.SLT
            elif r1 is HwtOps.UGE:
                rel = HwtOps.UGT
            elif r1 is HwtOps.SGE:
                rel = HwtOps.SGT
            else:
                rel = r1

        elif r0 is HwtOps.LT:
            if r1 is HwtOps.GT:
                # always 0
                return False, True
            elif r1 is HwtOps.LE:
                rel = HwtOps.LT
            elif r1 is HwtOps.GE:
                # always 0
                return False, True
            else:
                raise AssertionError("All cases should be handled", r1)

        elif r0 is HwtOps.GT:
            if r1 is HwtOps.LE:
                # always 0
                return False, True
            elif r1 is HwtOps.GE:
                r1 = HwtOps.GT
            else:
                raise AssertionError("All cases should be handled", r1)

        elif r0 is HwtOps.LE and r1 is HwtOps.GE:
            rel = HwtOps.EQ

        else:
            raise AssertionError("All cases should be handled", r1)

        lattice[k] = rel
        return None, True


def _cmpAndConstToInterval(rel: HOperatorDef, width: int, c:int) -> Union[int, List[range]]:
    """
    :note: returned intervals are always sorted low to high
    """
    # if signed:
    smax = mask(width - 1)
    smin = -smax - 1
    # else:
    umin = 0
    umax = mask(width)

    if rel is HwtOps.EQ:
        return [range(c, c + 1), ]

    elif rel is HwtOps.NE:
        if c == umin:
            return [range(umin + 1, umax + 1), ]
        elif c == umax:
            return [range(umin, umax), ]
        else:
            cAsUnsigned = to_unsigned(c, width)
            return [range(umin, cAsUnsigned),
                    range(cAsUnsigned + 1, umax + 1)]

    elif rel is HwtOps.ULT:
        if c == umin:
            return 0  # whole and expression resolved to 0
        else:
            return [range(umin, to_unsigned(c, width)), ]

    elif rel is HwtOps.SLT:
        if c == smin:
            return 0  # whole and expression resolved to 0
        elif c <= 0:
            # smin..c-1, e.g. 0b1000..0b1111
            return [range(smin, to_unsigned(c, width)), ]
        else:
            # 0..c-1 | smin..-1, e.g.  0b0001..0b0000 |  0b1000..0b1111
            return [range(0, c),
                    range(smin, to_unsigned(-1, width) + 1), ]

    elif rel is HwtOps.UGT:
        if c == umax:
            return 0  # whole and expression resolved to 0
        else:
            return [range(c + 1, umax + 1), ]

    elif rel is HwtOps.SGT:
        if c == smax:
            return 0  # whole and expression resolved to 0
        elif c >= 0:
            # c+1..smax
            return [range(c + 1, to_unsigned(smax, width) + 1), ]
        else:
            # 0..smax | c+1..-1
            return [
                range(0, smax + 1),
                range(to_unsigned(c + 1, width), to_unsigned(-1, width) + 1)]

    elif rel is HwtOps.ULE:
        if c == umax:
            return 1
        else:
            return [range(umin, c + 1), ]

    elif rel is HwtOps.SLE:
        # :note: HwtOps.SGT without +1 after c
        if c == smax:
            return 1
        elif c <= -1:
            # smin..c, e.g. 0b1000..0b1111
            return [range(smin, to_unsigned(c, width) + 1), ]
        else:
            # 0..c | smin..-1, e.g.  0b0001..0b0000 |  0b1000..0b1111
            return [range(0, c + 1), range(smin, to_unsigned(-1, width) + 1), ]

    elif rel is HwtOps.UGE:
        if c == umin:
            return 1
        else:
            return [range(c, umax + 1), ]

    elif rel is HwtOps.SGE:
        # :note: HwtOps.SGT without +1 after c
        if c == smin:
            return 1
        elif c >= 0:
            # c..smax
            return [range(c, to_unsigned(smax, width) + 1), ]
        else:
            # 0..smax | c..-1
            return [range(0, smax + 1), range(to_unsigned(c, width), to_unsigned(-1, width) + 1)]

    else:
        raise AssertionError("All cases should be handled", rel)


def _intervalListIntersection(l0: List[range], l1: List[range]):
    # https://stackoverflow.com/questions/40367461/intersection-of-two-lists-of-ranges-in-python
    l0 = iter(l0)
    l1 = iter(l1)
    # Try to get the first range in each iterator:
    try:
        i0 = next(l0)
        i1 = next(l1)
    except StopIteration:
        return

    while True:
        # Yield the intersection of the two ranges, if it's not empty:
        intersection = range(
            max(i0.start, i1.start),
            min(i0.stop, i1.stop)
        )
        if intersection:
            yield intersection

        # Try to increment the range with the earlier stopping value:
        try:
            if i0.stop <= i1.stop:
                i0 = next(l0)
            else:
                i1 = next(l1)
        except StopIteration:
            return


def _appendKnowledgeVarAndConst(lattice: ValueConstrainLattice,
                                rel: HOperatorDef,
                                v: HlsNetNodeOut,
                                c: HConst) -> Tuple[Optional[bool], bool]:
    """
    Variant of :func:`~._appendKnowledgeTwoVars` where one operand is constant.

    :return: tuple of two flags (final result known value, change in expression)
    """
    intervals = _cmpAndConstToInterval(rel, v._dtype.bit_length(), c)
    if isinstance(intervals, int):
        if intervals == 0:
            return 0, True
        else:
            return None, True

    assert isinstance(intervals, list)
    k = (v, v)
    curV = lattice.get(k, None)
    if curV is None:
        # newly obtained knowledge about exact value
        lattice[k] = intervals
        return None, False

    posibleInterval: List[range] = list(_intervalListIntersection(curV, intervals))
    if not posibleInterval:
        # discovered 0 in "and" tree, whole result is 0
        return 0, True
    else:
        lattice[k] = posibleInterval
        return None, True

# def mergeItemsInGroupDict(d: Dict[HlsNetNodeOut, Set[HlsNetNodeOut]], item0: HlsNetNodeOut, item1: HlsNetNodeOut):
#    g0 = d.get(item0, None)
#    g1 = d.get(item1, None)
#    if g0 is None and g1 is None:
#        g = {item0, item1}
#    elif g0 is None:
#        g = g1
#        g.add(item0)
#    elif g1 is None:
#        g = g0
#        g.add(item1)
#    else:
#        for n in g1:
#            d[n] = g0
#        g0.update(g1)
