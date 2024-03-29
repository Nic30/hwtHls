from typing import List, Union, Tuple, Optional

from hwt.hdl.value import HValue
from hwtHls.ssa.value import SsaValue
from copy import copy


class ConcatOfSlices():
    """
    :note: in high to low format
    
    :ivar slices: list of tuples (variable, high bit number, low bit number)
    """

    def __init__(self, slices: List[Union[Tuple[Union[HValue, SsaValue], int, int], Union[HValue, SsaValue]]]):
        # normalize slices to a format List[Tuple[Union[HValue, SsaValue], int, int]]
        w = 0
        _slices:Optional[List] = None
        for i, s in enumerate(slices):
            if isinstance(s, ConcatOfSlices):
                if _slices is None:
                    _slices = []

                _slices.extend(s.slices)
                w += s.bit_length
                continue

            elif isinstance(s, tuple):
                w += s[1] - s[2]
            else:
                width = s._dtype.bit_length()
                if _slices is None:
                    # first item which is missing the slice range part, copy all predecessors
                    # in tmp _slices list
                    _slices = list(slices[:i])

                s = (s, width, 0)
                w += width

            if _slices is not None:
                _slices.append(s)

        if _slices is not None:
            slices = _slices

        self.slices: List[Tuple[Union[HValue, SsaValue], int, int]] = slices
        self.bit_length = w

    def concat(self, other: 'ConcatOfSlices'):
        res = ConcatOfSlices(())
        res.slices = self.slices + other.slices
        res.bit_length = self.bit_length + other.bit_length
        return res

    def slice(self, high:int, low:int):
        if not (high > low and high <= self.bit_length and low >= 0):
            raise IndexError()

        elif low == 0 and high == self.bit_length:
            return ConcatOfSlices(copy(self.slices))

        res = []
        hOffset = self.bit_length  # current position in vector from h side
        for v, _high, _low in self.slices:
            absHigh = hOffset
            w = _high - _low
            absLow = hOffset - w
            # entirely before
            # overlaps on high (cut a piece from current v and exit)
            # overlaps on high and low (cut a piece from current v and exit)
            # current high in interval high-low  (cut a piece from current v and exit)
            if high > absLow:
                # not entirely before
                relHigh = _low + min(absHigh, high) - absLow
                relLow = _low + max(absLow, low) - absLow
                res.append((v, relHigh, relLow))
                if absLow <= low:
                    break
            hOffset -= w

        return ConcatOfSlices(res)

    def __eq__(self, other: "ConcatOfSlices"):
        return self is other or (
            isinstance(other, ConcatOfSlices) and
            self.bit_length == other.bit_length and
            self.slices == other.slices
        )

    def __hash__(self):
        return hash(tuple(self.slices))

    def __repr__(self):
        slices = [f"{s._name if isinstance(s, SsaValue) else s }[{h}:{l}]" for s, h, l in self.slices]
        return f"<{self.__class__.__name__:s} [{', '.join(slices)}] >"

