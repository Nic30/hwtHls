from copy import copy
from typing import Optional


def mergeInRange(range_list: list[tuple[int, int]], beginI: int, endI: int) -> list[tuple[int, int]]:
    """
    :note: ranges are enclosed on both sides (0, 1) encodes "<0,1>", items 0 and 1
    """
    assert beginI <= endI, (beginI, endI)

    result = []
    rangeIt = iter(range_list)

    # Copy ranges strictly before new range
    r = None
    while True:
        r = next(rangeIt, None)
        if r is None:
            break
        if r[1] < beginI - 1:
            result.append(r)
        else:
            break

    # :note: r is now None or the first range overlapping with new range
    # or after it
    if r is None:
        # everything was before new range
        result.append((beginI, endI))
        return result
    elif endI < r[0] - 1:
        # new has no overlap with r
        result.append((beginI, endI))
    else:
        # compute new newBegin for the case that r
        # begins before beginI
        newBegin = min(beginI, r[0])
        newEnd = max(endI, r[1])
        while True:
            r = next(rangeIt, None)
            if r is None:
                # new range is on right boundary
                result.append((newBegin, newEnd))
                return result

            elif endI < r[0] - 1:
                # the newly inserted range begins before end of this range
                result.append((newBegin, newEnd))
                result.append(r)
                break
            # else skip range contained in newly inserted range
            newEnd = r[1]

    # copy leftovers
    result.extend(rangeIt)
    return result


def tryMerging2RangesRightInclusive(r0: tuple[int, int], r1: tuple[int, int]) -> Optional[tuple[int, int]]:
    """
    :note: (0, 1) encodes "<0,1>", items 0 and 1
    """
    if r0[0] > r1[0]:
        # swap so r0 is cloer to left
        r0, r1 = r1, r0
    # check if have overlap
    if r0[1] + 1 >= r1[0]:
        # r0 ends >= r1 begin
        # <0,1> + <2, 3> = <0,3>
        return (min(r0[0], r1[0]), max(r0[1], r1[1]))

    return None


def tryMerging2RangesRightExclusive(r0: tuple[int, int], r1: tuple[int, int]) -> Optional[tuple[int, int]]:
    """
    :note: (0, 2) encodes "<0,2)", item 0 and 1
    """
    if r0[0] > r1[0]:
        # swap so r0 is cloer to left
        r0, r1 = r1, r0
    # check if have overlap
    if r0[1] >= r1[0]:
        # r0 ends >= r1 begin
        # <0,2) + <2, 3> = <0,3)
        return (min(r0[0], r1[0]), max(r0[1], r1[1]))

    return None


def mergeRanges(ranges0: list[tuple[int, int]], ranges1: list[tuple[int, int]],
                rightInclusive:bool=False) -> list[tuple[int, int]]:
    """
    :param rightInclusive: specifies if ranges are in format rightInclusive "<l,h>" or right exclusive format "<l,h)"
    :see: :func:`tryMerging2RangesRightInclusive`, :func:`tryMerging2RangesRightExclusive`
    """
    if not ranges0:
        return copy(ranges1)
    elif not ranges1:
        return copy(ranges0)
    if rightInclusive:
        tryMerging2Ranges = tryMerging2RangesRightInclusive
    else:
        tryMerging2Ranges = tryMerging2RangesRightExclusive
    _ranges0 = iter(ranges0)
    _ranges1 = iter(ranges1)

    result: list[tuple[int, int]] = []
    last: Optional[tuple[int, int]] = None
    r0 = next(_ranges0, None)
    r1 = next(_ranges1, None)
    while True:
        # pick range with min low and append it into result
        if r0 is None:
            if r1 is None:
                break
            else:
                useR0 = False
        elif r1 is None:
            useR0 = True
        else:
            useR0 = r0[0] < r1[0]

        if useR0:
            r = r0
        else:
            r = r1

        if last is None:
            last = r
            result.append(r)
        else:
            merge = tryMerging2Ranges(last, r)
            if merge is None:
                last = r
                result.append(r)
            else:
                result[-1] = last = merge

        if useR0:
            r0 = next(_ranges0, None)
        else:
            r1 = next(_ranges1, None)
    return result
