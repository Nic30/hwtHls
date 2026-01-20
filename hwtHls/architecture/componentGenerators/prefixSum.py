from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.math import log2ceil
from hwtHls.code import ctpop
from pyMathBitPrecise.bit_utils import set_least_significant_0, \
    clear_least_significant_1, separate_least_significant_1


@hwt_expr_producer
def prefixSum1bFenwickTree(vec: list[AnyHBitsValue]) -> list[AnyHBitsValue]:
    """
    Prefix sum implementation using Fenwick Tree (resource efficient, high latency,
    the input vector is divided recursively (in this case to half))
    based on: https://cp-algorithms.com/data_structures/fenwick.html
              https://github.com/b0nes164/GPUPrefixSums
              https://brilliant.org/wiki/fenwick-tree/
    :note: this is inclusive variant (the x[i] of output is summed with original x[i] )
    :note: Kogge-Stone algorithm is not work-efficient
           Brent-Kung has high delay
           https://github.com/R100001/Programming-Massively-Parallel-Processors/blob/master/Chapters/Ch08%20-%20Parallel%20Patterns%3A%20Prefix%20Sum/README.md
    .. code-block:: python
        .. caption:: naive prefix sum (sequential scan)
            
            for(int i = 1; i < size; i++) {
                x[i] += x[i-1];
            }
    """
    assert vec[0]._dtype.bit_length() == 1, vec[0]._dtype
    width = len(vec)
    indexWidth = log2ceil(width + 1)
    indexT = HBits(indexWidth)
    # index 0 unused, but requred for correct indexing
    binIndexedTree = [indexT.from_py(0) for _ in range(width + 1)]

    # https://cp-algorithms.com/data_structures/fenwick.html, Linear construction O(n) instead of O(n log n)
    for i, inBit in enumerate(vec):
        i += 1
        # :note: not using += to overwirte reference in python list
        binIndexedTree[i] = binIndexedTree[i] + inBit._zext(indexWidth)
        r = i + separate_least_significant_1(i)
        # r = set_least_significant_0(i)
        if r <= width:
            binIndexedTree[r] = binIndexedTree[r] + binIndexedTree[i]

    # https://algocademy.com/blog/implementing-fenwick-trees-for-efficient-range-queries/
    # FenwickTree::sum
    prefixSumArray = []
    for i in range(width):
        inBit = vec[i]
        resSum = None
        origI = i
        i += 1
        while i > 0:
            if resSum is None:
                resSum = binIndexedTree[i]
            else:
                resSum = resSum + binIndexedTree[i]
            i -= separate_least_significant_1(i)  # clear_least_significant_1(i)

        if resSum is None:
            assert origI == 0, origI
            resSum = inBit._zext(indexWidth)
        else:
            # discard bits which ware knonw to be 0 and then zext back to original width
            resSum = resSum._trunc(log2ceil(origI + 1 + 1))._zext(indexWidth)

        prefixSumArray.append(resSum)

    return prefixSumArray

# @hwt_expr_producer
# def ctpop_fn(num: list[AnyHBitsValue], bitsToLookupInROM: int=4):
#    w = num._dtype.bit_length()
#    res = HBits(log2ceil(w + 1)).from_py(None)
#    if w == 1:
#        res = num
#    elif w <= bitsToLookupInROM:
#        itemT = res._dtype
#        popcountRom = [itemT.from_py(i.bit_count()) for i in range(1 << w)]
#        popcountRom = itemT[len(popcountRom)].from_py(popcountRom)
#        res = popcountRom[num]
#        # res = ctpop(num)
#    else:
#        leftRes = ctpop_fn(num[w // 2:], bitsToLookupInROM=bitsToLookupInROM)
#        rightRes = ctpop_fn(num[:w // 2], bitsToLookupInROM=bitsToLookupInROM)
#        res = leftRes._reinterpret_cast(res._dtype) + rightRes._reinterpret_cast(res._dtype)
#
#    return res


@hwt_expr_producer
def prefixSum1bPerResultBinTreeBased(vec: list[AnyHBitsValue], inclusive=True) -> list[AnyHBitsValue]:
    """
    Latency optimized variant, large resource consumption for large vec sizes
    """
    assert vec[0]._dtype.bit_length() == 1, (vec[0]._dtype, "all input items are expected to be 1b")
    num = Concat(*reversed(vec))
    width = len(vec)
    indexWidth = log2ceil(width + 1)
    prefixSumArray = []
    for i in range(width):
        if inclusive:
            resSum = ctpop(num[i + 1:])  # ctpop_fn(num[i + 1:], bitsToLookupInROM=bitsToLookupInROM)
        else:
            if i == 0:
                resSum = HBits(indexWidth).from_py(0)
            else:
                resSum = ctpop(num[i:])
        resSum = resSum._zext(indexWidth)
        prefixSumArray.append(resSum)

    return prefixSumArray


def prefixSumNaivePy(vec: list[int]):
    prefixSum = []
    for v in vec:
        if prefixSum:
            v += prefixSum[-1]
        prefixSum.append(v)
    return prefixSum

