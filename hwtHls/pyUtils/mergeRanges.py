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
        # compute new newBegin for the case that this
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
