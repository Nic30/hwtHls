import itertools
import random
from typing import Optional

from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from pyMathBitPrecise.bit_utils import to_signed, mask


class _ABContainer():

    def __init__(self, a, b):
        self.a = a
        self.b = b


def _allCombinationsOfValuesForBitewidths(N: int, M: int, signed: Optional[bool]):
    for a in range(2 ** M):
        for b in range(2 ** N):
            if signed:
                yield (to_signed(a, M), to_signed(b, N))
            else:
                yield (a, b)


def _allCombinationsOfValuesForBitewidthsForTy(Ty: HBits):
    yield from _allCombinationsOfValuesForBitewidths(Ty.bit_length(), Ty.bit_length(), Ty.signed)


def _testMulGenerateRandomTestVals(rand: random.Random, signed: bool, w: int, N: int):
    """
    :attention: output len may be different from N
    """
    if signed:
        max_val = mask(w - 1) - 1
        min_val = -mask(w - 1)
        test_vals = SetList([0,
                             1, -1, max_val, min_val,
                             max_val // 2, min_val // 2
                             ])
    else:
        max_val = mask(w)
        min_val = 0
        test_vals = SetList([0, 1, max_val, max_val // 2])

    # Add a few random values within range
    if 2 ** w - 1 <= N:
        for i in range(2 ** w - 1):
            test_vals.append(i + min_val)
    else:
        for _ in range(N):
            test_vals.append(rand.randint(min_val, max_val))

    return test_vals


def _testMulGenerateRandomTestValPairs(rand: random.Random, T0: HBits, T1: HBits, N: int):
    testVals0 = _testMulGenerateRandomTestVals(rand, T0.signed, T0.bit_length(), N)
    if T0 == T1:
        testVals1 = testVals0
    else:
        testVals1 = _testMulGenerateRandomTestVals(rand, T1.signed, T1.bit_length(), N)
    return list(itertools.product(testVals0, testVals1))

