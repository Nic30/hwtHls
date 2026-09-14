#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.types.struct import HStruct
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBuffer_inWordPacking import Axi4streamSegmentedTxSegnemtBuffer_inWordPacking, \
    Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBuffer_inWordPacking_test import PassTestIoOutSegmentedStruct
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBuffer_outWordPacking import Axi4streamSegmentedTxSegnemtBuffer_outWordPacking
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS, DebugId, \
    HlsDebugBundle
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmentedMockSegmentTy
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIoStruct import PassTestIoInStruct


class PassTestIoOutSegmentedOutStruct(PassTestIoOutSegmentedStruct):

    @staticmethod
    def setAllDataToNoneForDisabledSegment(outWord: dict):
        """
        set all values (except enable) for disabled segments to undef
        (some optimizations e.g. hwtHls::BitwidthReductionPass can remove explicit set to undef and value is typically connected to some input
         e.g. in last item there can be only last item from input or undef, so it is reduced to just last input item and select is removed)
        the eplicit clean is necessary for assertSequenceEqual because the reference value contains None and the value itself does not matter
        as it is disabled by enable flag
        """
        for i, u in enumerate(outWord["user"]):
            if not u.get("enable", True):  # :note: can not use u["enable"] because if out has just 1 segment enable is not present
                if "sof" in u:
                    u["sof"] = None
                u["eof"] = None
                u["empty"] = None
                outWord["data"][i] = None
        return outWord


# from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
class Axi4streamSegmentedTxSegnemtBuffer_outWordPacking_TC(BaseIrMirRtl_TC):

    def _generateInWordFromSegments(self, IN_T: HStruct, TOTAL_SEGMENT_CNT: int, segments: list[Axi4StreamSegmentedMockSegmentTy]):
        Axi4streamSegmentedTxSegnemtBuffer_inWordPacking._modelAddPaddingSegments(segments, TOTAL_SEGMENT_CNT)
        segmentsValidCnt = 0
        lastEoFPosition = -1
        for i, seg in enumerate(segments):
            u = seg["user"]
            if u["enable"]:
                segmentsValidCnt += 1
                if u["eof"]:
                    lastEoFPosition = i

        return IN_T.from_py({
            "segments": segments,
            "segmentsValidCnt": segmentsValidCnt,
            "segmentsEndingWithEoFCnt": 0 if lastEoFPosition < 0 else lastEoFPosition + 1,
        })

    def _generateDataFromFrameSizes(self, IN_T: HStruct, IN_SEGMENT_T: HStruct, TOTAL_SEGMENT_CNT:int, PACKET_SIZES: list[int]):
        dataIn: list[Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy] = []
        segments: list[Axi4StreamSegmentedMockSegmentTy] = []
        paddingSegmentCnt = 0
        for size in PACKET_SIZES:
            if size == 0:
                paddingSegmentCnt += 1
                if len(segments) + paddingSegmentCnt == TOTAL_SEGMENT_CNT:
                    dataIn.append(self._generateInWordFromSegments(IN_T, TOTAL_SEGMENT_CNT, IN_SEGMENT_T, segments))
                    paddingSegmentCnt = 0
                    segments = []
            else:
                for i in range(size):
                    # "sof": i == 0,
                    seg = {"user": {"enable": 1, "eof": int(i == size - 1), "empty": 0}, "data": i + 1}
                    segments.append(seg)
                    if len(segments) + paddingSegmentCnt == TOTAL_SEGMENT_CNT:
                        dataIn.append(self._generateInWordFromSegments(IN_T, TOTAL_SEGMENT_CNT, segments))
                        paddingSegmentCnt = 0
                        segments = []

        if segments or paddingSegmentCnt != 0:
            # add padding to finish the word
            dataIn.append(self._generateInWordFromSegments(IN_T, TOTAL_SEGMENT_CNT, segments))

        return dataIn

    def _testBuff(self, SEGMENT_DATA_WIDTH:int, SEGMENT_CNT: int,
                  MAX_SEGMENTS_PER_LANE:int,
                  PACKET_SIZES=[0, 1, 0, 2, ],
                  freq=int(1e6),
                    ):
        dut = Axi4streamSegmentedTxSegnemtBuffer_outWordPacking()
        dut.SEGMENT_DATA_WIDTH = SEGMENT_DATA_WIDTH
        dut.SEGMENT_CNT = SEGMENT_CNT
        dut.MAX_SEGMENTS_PER_LANE = MAX_SEGMENTS_PER_LANE
        dut.CLK_FREQ = freq
        TOTAL_SEGMENT_CNT = SEGMENT_CNT * MAX_SEGMENTS_PER_LANE
        IN_SEGMENT_T = dut.getSegmentTy()
        IN_T = dut.getPackedWordTy()
        dataIn = self._generateDataFromFrameSizes(IN_T, IN_SEGMENT_T, TOTAL_SEGMENT_CNT, PACKET_SIZES)
        OUT_T = dut.getAxi4SSWordTy()
        passTest = PassTestInjectorForDInDOutHwModule(dut, self)
        passTest.initTestOutDataRefUsingModel(IN_DATA=(PassTestIoInStruct(IN_T, dataIn, name="dataIn"),),
                                              OUT_DATA_REF=(PassTestIoOutSegmentedOutStruct(OUT_T, [], name="dataOut", useDictForData=True),))
        passTest.setTimeLimits(wallTimeRtlDefaultAddAfter=1)
        passTest.test_allInOne(
            #platformKwArgs=dict(
            #    debugFilter={
            #        *HlsDebugBundle.ALL_RELIABLE,
            #    # HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
            #    # HlsDebugBundle.DBG_4_0_addSignalNamesToData,
            #    },
            #    # llvmCliArgs=[
            #    #    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            #    #    # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
            #    #    # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
            #    # ],
            #),
        )

    def test_1seg_0to2(self):
        self._testBuff(32, 1, 2)

    def test_2seg_0to2(self):
        self._testBuff(32, 2, 2)

    def test_3seg_0to2(self):
        self._testBuff(32, 3, 2)

    def test_4seg_0to2(self):
        self._testBuff(32, 4, 2)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4streamSegmentedTxSegnemtBuffer_outWordPacking_TC)
    # suite = unittest.TestSuite([Axi4streamSegmentedTxSegnemtBuffer_outWordPacking_TC("test_1seg_0to2")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
