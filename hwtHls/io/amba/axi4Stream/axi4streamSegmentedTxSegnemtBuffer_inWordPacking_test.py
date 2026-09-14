#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from copy import copy
import unittest

from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structUtils import HStruct_tuple_to_dict
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.pyUtils.typingFuture import override
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBuffer_inWordPacking import Axi4streamSegmentedTxSegnemtBuffer_inWordPacking
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmentedMockSegmentTy
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIoStruct import PassTestIoInStruct, PassTestIoOutStruct


class PassTestIoOutSegmentedStruct(PassTestIoOutStruct):

    @override
    def checkForLlvmIr(self, dataSim: list[HBitsConst]):
        T = self.T
        tc = self.passTests.tc
        assert self.useDictForData
        dataOut = [self.setAllDataToNoneForDisabledSegment(d._reinterpret_cast(T).to_py())
                   for d in dataSim]
        # print("ref:")
        # for d in self.dataRef:
        #    print(d)
        #
        # print("out:")
        # for d in dataOut:
        #    print(d)
            
        tc.assertValSequenceEqual(dataOut, self.dataRef, msg=self.errMsgFormatter(self, dataSim, self.dataRef))

    @override
    def checkForRtl(self):
        oPort = self._getRtlDutPort()
        dataSim = oPort._ag.data
        tc = self.passTests.tc
        dataSimAsDict = [HStruct_tuple_to_dict(self.T, d) for d in dataSim] 
        dataSimAsDict = [self.setAllDataToNoneForDisabledSegment(d) for d in dataSimAsDict]
        tc.assertValSequenceEqual(dataSimAsDict, self.dataRef, msg=self.errMsgFormatter(self, dataSim, self.dataRef))

    @staticmethod
    def setAllDataToNoneForDisabledSegment(outWord: dict):
        """
        set all values (except enable) for disabled segments to undef
        (some optimizations e.g. hwtHls::BitwidthReductionPass can remove explicit set to undef and value is typically connected to some input
         e.g. in last item there can be only last item from input or undef, so it is reduced to just last input item and select is removed)
        the explicit clean is necessary for assertSequenceEqual because the reference value contains None and the value itself does not matter
        as it is disabled by enable flag
        """
        for seg in outWord["segments"]:
            u = seg["user"]
            if not u["enable"]:
                if "sof" in u:
                    u["sof"] = None
                u["eof"] = None
                u["empty"] = None
                seg["data"] = None

        return outWord


# from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
class Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_TC(BaseIrMirRtl_TC):

    def _generateDataFromFrameSizes(self, dut: Axi4streamSegmentedTxSegnemtBuffer_inWordPacking,
                                    inWordT: HStruct,
                                    TOTAL_SEGMENT_CNT:int,
                                    PACKET_SIZES: list[int]) -> list[list[HStructConstBase]]:
        dataIn: list[list[Axi4StreamSegmentedMockSegmentTy]] = []
        word: list[Axi4StreamSegmentedMockSegmentTy] = []
        for size in PACKET_SIZES:
            if size == 0:
                # 0 means that there is 1 segment with enable=0
                seg = {"user": {"enable": 0}}
                word.append(seg)
                if len(word) == TOTAL_SEGMENT_CNT:
                    dataIn.append(inWordT.from_py(word))
                    word = []
            else:
                for i in range(size):
                    # "sof": i == 0,
                    seg = {"user": {"enable": 1, "eof": i == size - 1, "empty": 0}, "data": i + 1}
                    word.append(seg)
                    if len(word) == TOTAL_SEGMENT_CNT:
                        dataIn.append(inWordT.from_py(word))
                        word = []
        if word:
            # add padding to finish the word
            dut._modelAddPaddingSegments(word, TOTAL_SEGMENT_CNT)
            dataIn.append(inWordT.from_py(word))
            word = []

        return dataIn

    def _testBuff(self, SEGMENT_DATA_WIDTH:int, SEGMENT_CNT: int,
                  MAX_SEGMENTS_PER_LANE:int,
                  PACKET_SIZES=[0, 1, 0, 2, ],
                  # wallTimeIr: Optional[int]=None,
                  # wallTimeOptIr: Optional[int]=None,
                  # wallTimeOptMir: Optional[int]=None,
                  # wallTimeRtlClks: Optional[int]=None,
                  # debugFilter: Optional[set[DebugId]]=HlsDebugBundle.DEFAULT,
                  # freq=int(1e6),
                  ):
        dut = Axi4streamSegmentedTxSegnemtBuffer_inWordPacking()
        dut.SEGMENT_DATA_WIDTH = SEGMENT_DATA_WIDTH
        dut.SEGMENT_CNT = SEGMENT_CNT
        dut.MAX_SEGMENTS_PER_LANE = MAX_SEGMENTS_PER_LANE
        dut.CLK_FREQ = int(1e6)

        TOTAL_SEGMENT_CNT = SEGMENT_CNT * MAX_SEGMENTS_PER_LANE
        IN_SEGMENT_T = dut.getSegmentTy()
        IN_T = IN_SEGMENT_T[TOTAL_SEGMENT_CNT]
        dataIn = self._generateDataFromFrameSizes(dut, IN_T, TOTAL_SEGMENT_CNT, PACKET_SIZES)
        OUT_T = dut.getPackedWordTy()

        passTest = PassTestInjectorForDInDOutHwModule(dut, self)
        passTest.initTestOutDataRefUsingModel(IN_DATA=(PassTestIoInStruct(IN_T, dataIn, name="dataIn"),),
                                              OUT_DATA_REF=(PassTestIoOutSegmentedStruct(OUT_T, [], name="dataOut", useDictForData=True),))
        dut._DBG_IS_SIM = True
        for i, (dIn, dOutRef) in enumerate(zip(dataIn, passTest.TEST_IO[1].dataRef)):
            # print(i)
            # print(dIn.to_py())
            # print(dOutRef)
            # copy is important there because the input is modified and we can not break reference input data
            dOut = dut.packSegmentsInWord(OUT_T, copy(dIn))
            dOutDict = dOut.to_py()
            PassTestIoOutSegmentedStruct.setAllDataToNoneForDisabledSegment(dOutDict)
            # print(dOutDict)
            self.assertDictEqual(dOutDict, dOutRef, i)

        dut._DBG_IS_SIM = False

        passTest.test_allInOne()

    def test_o1lane_0upto2seg_perLane(self):
        self._testBuff(32, 1, 2)

    def test_o2lane_0upto2seg_perLane(self):
        self._testBuff(32, 2, 2)

    def test_3lane_0upto2seg_perLane(self):
        self._testBuff(32, 3, 2)

    def test_o4lane_0upto2seg_perLane(self):
        self._testBuff(32, 4, 2)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_TC)
    # suite = unittest.TestSuite([Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_TC("test_o2lane_0upto2seg_perLane")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
