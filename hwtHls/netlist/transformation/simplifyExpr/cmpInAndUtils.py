from typing import Dict, Union, Tuple, List, Optional

from hwt.hdl.operatorDefs import OpDefinition, AllOps
from hwt.hdl.value import HValue
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from pyMathBitPrecise.bit_utils import mask

# matrix variables X variables,
# value range may appear on diagonal
# None means no knowledge available
# :attention: because bottom-left triangle is only negation of top-right triangle, only top-right is present,
#      variables are ordered "see: _:func:`~._appendKnowledgeTwoVars`
#
ValueConstrainLattice = Dict[HlsNetNodeOut,
                 Union[
                    OpDefinition,  # compare operator
                    Tuple[int, int],
                    None,
                 ]
                 ]

CMP_WITH_EQ = (AllOps.EQ, AllOps.LE, AllOps.GE)
# :note: used to sort operators to reduce number of compares for the operator strength
OP_STRENGTH = {
    AllOps.EQ: 6,
    AllOps.NE: 5,
    AllOps.LT: 4,
    AllOps.GT: 3,
    AllOps.LE: 2,
    AllOps.GE: 1,
}


def _appendKnowledgeTwoVars(lattice: ValueConstrainLattice, rel: OpDefinition, o0: HlsNetNodeOut, o1: HlsNetNodeOut) -> Tuple[Optional[bool], bool]:
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

        # straighten the relation if necessary
        if r0 is AllOps.EQ:
            if r1 in CMP_WITH_EQ:
                rel = AllOps.EQ
            else:
                # always 0
                return False, True

        elif r0 is AllOps.NE:
            if r1 is AllOps.EQ:
                # always 0
                return False, True
            elif r1 is AllOps.LE:
                rel = AllOps.LT
            elif r1 is AllOps.GE:
                rel = AllOps.GT
            else:
                rel = r1

        elif r0 is AllOps.LT:
            if r1 is AllOps.GT:
                # always 0
                return False, True
            elif r1 is AllOps.LE:
                rel = AllOps.LT
            elif r1 is AllOps.GE:
                # always 0
                return False, True
            else:
                raise AssertionError("All cases should be handled", r1)

        elif r0 is AllOps.GT:
            if r1 is AllOps.LE:
                # always 0
                return False, True
            elif r1 is AllOps.GE:
                r1 = AllOps.GT
            else:
                raise AssertionError("All cases should be handled", r1)

        elif r0 is AllOps.LE and r1 is AllOps.GE:
            rel = AllOps.EQ

        else:
            raise AssertionError("All cases should be handled", r1)

        lattice[k] = rel
        return None, True


def _cmpAndConstToInterval(rel: OpDefinition, width: int, signed: bool, c:int) -> Union[int, List[range]]:
    """
    :note: returned intervals are always sorted low to high
    """
    if signed:
        _max = mask(width - 1)
        _min = -_max - 1
    else:
        _min = 0
        _max = mask(width)

    if rel is AllOps.EQ:
        return [range(c, c + 1), ]

    elif rel is AllOps.NE:
        if c == _min:
            return [range(_min + 1, _max + 1), ]
        elif c == _max:
            return [range(_min, _max), ]
        else:
            return [range(_min, c), range(c + 1, _max + 1)]

    elif rel is AllOps.LT:
        if c == _min:
            return 0  # whole and expression resolved to 0
        else:
            return [range(_min, c), ]

    elif rel is AllOps.GT:
        if c == _max:
            return 0  # whole and expression resolved to 0
        else:
            return [range(c + 1, _max + 1), ]

    elif rel is AllOps.LE:
        if c == _max:
            return 1
        else:
            return [range(_min, c + 1), ]

    elif rel is AllOps.GE:
        if c == _min:
            return 1
        else:
            return [range(c, _max + 1), ]

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
                                rel: OpDefinition,
                                v: HlsNetNodeOut,
                                c: HValue) -> Tuple[Optional[bool], bool]:
    """
    Variant of :func:`~._appendKnowledgeTwoVars` where one operand is constant.

    :return: tuple of two flags (final result known value, change in expression)
    """
    intervals = _cmpAndConstToInterval(rel, v._dtype.bit_length(), v._dtype.signed, c)
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
