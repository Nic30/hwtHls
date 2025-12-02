from collections import deque
from typing import Sequence, Callable, Optional

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.simulator.utils import Bits3valToInt
from hwtHls.platform.debugBundle import DebugId, HlsDebugBundle
from tests.adt.collections.binarySearchTreePointerLess import _ExampleBinaryTreePointerLessArraySearchROM0, \
    binaryTreePointerLessArraySearch, _computeTreeLayersLayoutInMemories
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC


class BinaryTreePointerLessArraySearch_TC(BaseIrMirRtl_TC):

    def _test_search(self, dut: _ExampleBinaryTreePointerLessArraySearchROM0,
                          model: Callable[Sequence[int], list[HStruct]],
                          dataIn: Sequence[int],
                          wallTimeIr: Optional[int]=None,
                          wallTimeOptIr: Optional[int]=None,
                          wallTimeOptMir: Optional[int]=None,
                          wallTimeRtlClks: Optional[int]=None,
                          debugFilter: Optional[set[DebugId]]=HlsDebugBundle.DEFAULT,
                          freq=int(1e6),
                          *args, **kwargs):
        """
        :param model: a function which process all inputs and generate all outputs
        For meaning of params check :meth:`~._testOneOut`
        """
        _dataOutRef = []
        try:
            model(iter(dataIn), _dataOutRef)
        except StopIteration:
            pass
        dataOutRef = []
        for d in _dataOutRef:
            dataOutRef.append(tuple(Bits3valToInt(member) for member in d))

        def prepareIrAndMirArgs():
            dataOut = []
            return (iter(dataIn), dataOut)

        def checkIrAndMirArgs(args: tuple[deque]):
            dataOut = args[1]
            RESULT_T = dut.RESULT_T
            dataOut = [tuple(Bits3valToInt(member) for member in d._reinterpret_cast(RESULT_T)) for d in dataOut]
            self.assertValSequenceEqual(dataOut, dataOutRef)

        def prepareRtlSimArgs(dut: _ExampleBinaryTreePointerLessArraySearchROM0):
            dut.dataIn._ag.data.extend(dataIn)
            ref = dataOutRef
            return ref

        def checkRtlSimResults(dut: _ExampleBinaryTreePointerLessArraySearchROM0, ref: list):
            self.assertValSequenceEqual(dut.dataOut._ag.data, ref)

        if wallTimeRtlClks is None:
            wallTimeRtlClks = len(dataIn) + 1

        self._test(dut,
            prepareIrAndMirArgs, checkIrAndMirArgs,
            prepareRtlSimArgs, checkRtlSimResults,
            wallTimeIr=wallTimeIr,
            wallTimeOptIr=wallTimeOptIr,
            wallTimeOptMir=wallTimeOptMir,
            wallTimeRtlClks=wallTimeRtlClks,
            freq=freq,
            debugFilter=debugFilter,
            *args, **kwargs
        )

    def getRandVal(self, t: HdlType):
        return t.from_py(self._rand.getrandbits(t.bit_length()))

    def _test_python(self, dut: _ExampleBinaryTreePointerLessArraySearchROM0,
                     itemDict: dict[int, int],
                     searchIn: list[int]):
        mem0 = dut.buildMemoryFromItems(1 << dut.MEM_INDEX_WIDTHS[0], dut.ITEMS)
        layerMemories = [(mem0, mem0._dtype.size), ]
        totalItemCnt, layersPerMemory = _computeTreeLayersLayoutInMemories(layerMemories)
        for k in searchIn:
            found, itemValue = binaryTreePointerLessArraySearch(layerMemories, totalItemCnt, layersPerMemory, dut.NODE_T, k)
            v = itemDict.get(int(k))
            if v is not None:
                self.assertTrue(bool(found), (k))
                self.assertValEqual(itemValue, v, (k))
            else:
                self.assertFalse(bool(found), (k))

    def test_search(self, OUT_CNT=8, randomData=False):
        dut = _ExampleBinaryTreePointerLessArraySearchROM0()
        dut.CLK_FREQ = int(50e6)
        dut.KEY_T = HBits(4)
        dut.declareTypes()
        if randomData:
            searchIn = [
                self.getRandVal(dut.KEY_T)
                for _ in range(OUT_CNT)
            ]
        else:
            # use sequential data
            searchIn = []
            for i in range(OUT_CNT):
                k = dut.KEY_T.from_py(i)
                searchIn.append(k)

        itemDict = {}
        for k, v in dut.ITEMS:
            itemDict[k] = v

        def model(toSearchIn, resultsOut):
            assert not resultsOut
            for k in toSearchIn:
                v = itemDict.get(int(k))
                res = dut.RESULT_T.from_py({
                    "found": v is not None,
                    "value": v
                })
                resultsOut.append(res)

        self._test_python(dut, itemDict, searchIn)

        self._test_search(dut, model, searchIn,
                   OUT_CNT * 400, OUT_CNT * 400,
                   OUT_CNT * 400, (OUT_CNT * 8) + 2,
                   # runTestAfterEachPass=True
                   )


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AddMasked_TC('test_noUnroll')])
    suite = testLoader.loadTestsFromTestCase(BinaryTreePointerLessArraySearch_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
