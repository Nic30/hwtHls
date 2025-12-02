import math
from typing import Union

from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.hwrange import hwrange
from hwtHls.frontend.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint16_t
from tests.adt.collections.binarySearchTreeUtils import _binaryTreeGetNumberOfItemsForHeight, \
    treeToTreeInArray, sortedArrayToBst
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.types.defs import BIT


def _computeTreeLayersLayoutInMemories(memories: list[tuple[IoProxyAddressed, int]]):
    level = 0
    totalItemCnt = 0
    layersPerMemory = []
    for (_, itemCnt) in memories:
        assert itemCnt >= 2 ** level
        nextLevel = math.floor(math.log2(totalItemCnt + itemCnt))
        assert level < nextLevel, "1 memory must accomodate whole level in tree"
        nextTotalItemCnt = _binaryTreeGetNumberOfItemsForHeight(nextLevel)
        layersPerMemory.append((nextLevel - level, nextTotalItemCnt - totalItemCnt))
        level = nextLevel
        totalItemCnt = nextTotalItemCnt

    return totalItemCnt, layersPerMemory


MemoryItemCntTuples = list[Union[tuple[RtlSignal, int], tuple[IoProxyAddressed, int]]]


@hwt_expr_producer
def readExternalOrInternalMemory(memory: HlsScope, address: RtlSignal, dataType: HdlType):
    if isinstance(memory, IoProxyAddressed):
        return memory.read(address).data._reinterpret_cast(dataType)
    else:
        return memory[address]._reinterpret_cast(dataType)


@hlsBytecode
def binaryTreePointerLessArraySearch(layerMemories: MemoryItemCntTuples,
                                     totalItemCnt: int,
                                     layersPerMemory: list[tuple[int, int]],
                                     nodeType: HStruct,
                                     key: RtlSignal,
                                     cmpEqPredicate=HwtOps.EQ._evalFn,
                                     cmpLtPredicate=HwtOps.LT._evalFn):
    """
    Search in binary tree stored in array, which may be divided to multiple memories for tree layers,
    variant without pointers where the childrean are always on known static location.
    
    :note: This implementation is efficient for static balanced trees.

    * 1 memory may contain 1 or more layers
    * 1 memory may contain only full layers 
      (the memory itself may be banked/multiported etc. but there is nothig specific for it in this function)
    * https://algorithmica.org/en/eytzinger
    """
    # https://www.geeksforgeeks.org/binary-tree-array-implementation/
    # index of the node
    indexTy = HBits(log2ceil(totalItemCnt))
    index = indexTy.from_py(0)
    # offset applied to index in layer to compensate for size
    # of previous layer memory
    offset = indexTy.from_py(0)
    found = b0
    itemValue = nodeType.field_by_name["value"].dtype.from_py(None)
    PyBytecodeBlockLabel("bb.binaryTreePointerLessArraySearch.begin")

    for memI, ((memory, _), (layersPerMemoryCnt, itemCnt)) in enumerate(zip(layerMemories, layersPerMemory)):
        # :note: this loop is unrolled in preprocessor
        PyBytecodeBlockLabel(f"bb.binaryTreePointerLessArraySearch.mem{memI:d}")

        for _ in hwrange(layersPerMemoryCnt):  # for layers stored in this memory
            # :note: depending on how layers are packed into memories, this may not be a loop
            item = readExternalOrInternalMemory(memory, index - offset, nodeType)
            if ~found & item.valid:
                PyBytecodeBlockLabel(f"bb.binaryTreePointerLessArraySearch.mem{memI:d}.cmp")
                # break is inteintionally not used to not create premature exits
                # from the loop to have straight pipeline with constant latency
                if cmpEqPredicate(key, item.key):
                    PyBytecodeBlockLabel(f"bb.binaryTreePointerLessArraySearch.mem{memI:d}.eq")
                    found = b1
                    itemValue = item.value
                elif cmpLtPredicate(key, item.key):
                    PyBytecodeBlockLabel(f"bb.binaryTreePointerLessArraySearch.mem{memI:d}.lt")
                    index = (index * 2) + 1  # left, smaller path
                else:
                    PyBytecodeBlockLabel(f"bb.binaryTreePointerLessArraySearch.mem{memI:d}.gt")
                    index = (index * 2) + 2  # right, larger path

        offset += itemCnt

    PyBytecodeBlockLabel("bb.binaryTreePointerLessArraySearch.end")
    return found, itemValue


class _ExampleBinaryTreePointerLessArraySearchROM0(HwModule):

    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.KEY_T = HwParam(uint16_t)
        self.VALUE_T = HwParam(uint16_t)
        self.ITEMS: tuple[tuple["KEY_T", "VALUE_T"], ...] = HwParam(((0, 1), (2, 3), (5, 8)))
        self.MEM_INDEX_WIDTHS: tuple[int, ...] = HwParam((3,))

    def declareTypes(self):
        self.RESULT_T = HStruct(
           (self.VALUE_T, "value"),
           (BIT, "found"),
        )
        self.NODE_T = HStruct(
           (self.KEY_T, "key"),
           (self.VALUE_T, "value"),
           (BIT, "valid")
        )

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.dataIn = HwIOStructRdVld()
        self.dataIn.T = self.KEY_T
        self.dataOut = HwIOStructRdVld()._m()
        self.declareTypes()
        self.dataOut.T = self.RESULT_T

    def _mkItem(self, key, value):
        # Concat(valid, value, key)
        item = 1 << self.VALUE_T.bit_length()
        item |= value
        item <<= self.KEY_T.bit_length()
        item |= key
        return item

    def buildMemoryFromItems(self, memSize: int, items: tuple[int, int]):
        memWordTy = HBits(self.NODE_T.bit_length())
        mem = memWordTy[memSize].from_py({
            # init nodes of the tree
            ** {i: self._mkItem(k, v) for i, (k, v) in enumerate(treeToTreeInArray(sortedArrayToBst(items)))},
            # init empty items in memory for tree
            ** {i: 0 for i in range(len(self.ITEMS), memSize)}
        })
        return mem

    @hlsBytecode
    def mainThread(self, hls: HlsScope,):
        mem0 = self.buildMemoryFromItems(1 << self.MEM_INDEX_WIDTHS[0], self.ITEMS)
        layerMemories = [(mem0, mem0._dtype.size), ]
        totalItemCnt, layersPerMemory = _computeTreeLayersLayoutInMemories(layerMemories)
        while b1:
            PyBytecodeBlockLabel("bb.mainThread.loop")
            k = hls.read(self.dataIn).data
            found, itemValue = PyBytecodeInline(binaryTreePointerLessArraySearch)(layerMemories, totalItemCnt, layersPerMemory, self.NODE_T, k)
            PyBytecodeBlockLabel("bb.mainThread.loop.latch")
            res = self.dataOut.T.from_py(None)
            res.found = found
            res.value = itemValue
            hls.write(res, self.dataOut)

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle

    dut = _ExampleBinaryTreePointerLessArraySearchROM0()
    dut.CLK_FREQ = int(1e6)
    print(to_rtl_str(dut, target_platform=VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
    )))

    # nodeT = HStruct(
    #    (uint16_t, "key"),
    #    (uint16_t, "value"),
    # )
    #
    # layerMemories = [(uint32_t[8].from_py({
    #    0: _mkItem(2, 3),
    #    1: _mkItem(0, 1),
    #    2: _mkItem(5, 8)
    #    }), 8), ]
    # key = uint16_t.from_py(2)
    # print(binaryTreeArraySearch(None, layerMemories, nodeT, key))
    # key = uint16_t.from_py(5)
    # print(binaryTreeArraySearch(None, layerMemories, nodeT, key))
