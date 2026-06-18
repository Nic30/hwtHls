
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from tests.adt.collections.binarySearchTreePointerLess import _ExampleBinaryTreePointerLessArraySearchROM0, \
    binaryTreePointerLessArraySearch, _computeTreeLayersLayoutInMemories
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIoStruct import PassTestIoOutStruct


class BinaryTreePointerLessArraySearch_TC(BaseIrMirRtl_TC):

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

        def model(dataIn, dataOut):
            assert not dataOut
            for k in dataIn:
                v = itemDict.get(int(k))
                res = dut.RESULT_T.from_py({
                    "found": v is not None,
                    "value": v
                })
                dataOut.append(res)

        self._test_python(dut, itemDict, searchIn)
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setTimeLimits(wallTimeIr=OUT_CNT * 400, wallTimeMir=OUT_CNT * 400, wallTimeRtl=(OUT_CNT * 8) + 2)
        passTests.test_allInOne_withModel((searchIn,), (PassTestIoOutStruct(dut.RESULT_T, [], name="dataOut"),), model=model)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AddMasked_TC('test_noUnroll')])
    suite = testLoader.loadTestsFromTestCase(BinaryTreePointerLessArraySearch_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
