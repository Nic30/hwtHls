#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Optional

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerators.prefixSum import prefixSum1bPerResultBinTreeBased
from hwtHls.code import ctpop, ctlz, lshr
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.axi4streamSegmentedTxSegnemtBufferCommon import Axi4streamSegmentedTxSegnemtBufferCommon
from hwtHls.io.amba.axi4Stream.selectUsingCasesWithCondition import selectUsingCasesWithCondition
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmentedMockSegmentTy
from pyMathBitPrecise.bit_utils import mask
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


@dataclass
class Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy():
    segments: list[Axi4StreamSegmentedMockSegmentTy]
    segmentsValidCnt: AnyHBitsValue
    # frameEndsWithEoF: AnyHBitsValue
    segmentsEndingWithEoFCnt: AnyHBitsValue


class Axi4streamSegmentedTxSegnemtBuffer_inWordPacking(Axi4streamSegmentedTxSegnemtBufferCommon):
    """
    This component takes array of segments for Axi4streamSegmented interface
    and packs it so all valid items are packed at the beginning of the array.
    """

    @override
    def hwDeclr(self) -> None:
        assert self.MIN_SEGMENTS_PER_LANE >= 0, self.MIN_SEGMENTS_PER_LANE
        assert self.MIN_SEGMENTS_PER_LANE <= self.MAX_SEGMENTS_PER_LANE, (self.MIN_SEGMENTS_PER_LANE, self.MAX_SEGMENTS_PER_LANE)
        addClkRstn(self)

        # dataIn is a vector of segments which is subject to packing
        self.dataIn = HwIOStructRdVld()
        self.dataIn.T = self.getSegmentTy()[self.IN_SEGMENT_CNT]
        # self.MAX_LATCHED_SEGMENTS = self.SEGMENT_CNT - 1
        self.dataOut = HwIOStructRdVld()._m()
        self.dataOut.T = self.getPackedWordTy()
    
    @property
    def IN_SEGMENT_CNT(self):
        return self.SEGMENT_CNT * self.MAX_SEGMENTS_PER_LANE
    
    @staticmethod
    def _modelAddPaddingSegments(word: list[Axi4StreamSegmentedMockSegmentTy], newItemCnt: int, segmentT: Optional[HStruct]=None):
        for _ in range(newItemCnt - len(word)):
            seg = {"data": None, "user": {"eof": None, "empty": None, "enable": 0}}
            if segmentT is not None:
                seg = segmentT.from_py(seg)
            word.append(seg)

    @hlsModelProps(returnsPyValue=False, returnsOutValue=False, inputArgsAreStructMembers=False)
    def model(self,
              dataIn: list[[Axi4StreamSegmentedMockSegmentTy]],
              dataOut: list[Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy]) \
                ->Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy:
        IN_SEGMENT_CNT = self.IN_SEGMENT_CNT
        for inWord in dataIn:
            assert len(inWord) == IN_SEGMENT_CNT
            outSegments = []
            lastEoFIndex = -1
            for seg in inWord:
                seg: Axi4StreamSegmentedMockSegmentTy
                if not seg.user.enable:
                    continue
                outSegments.append(seg)
                if seg.user.eof:
                    lastEoFIndex = len(outSegments) - 1

            segmentsValidCnt = len(outSegments)
            self._modelAddPaddingSegments(outSegments, IN_SEGMENT_CNT)

            outWord = self.getPackedWordTy().from_py({
                "segments": outSegments,
                "segmentsValidCnt": segmentsValidCnt,
                "segmentsEndingWithEoFCnt": lastEoFIndex + 1 if lastEoFIndex >= 0 else 0,
                # "frameEndsWithEoF": 0 if lastEoFPosition < 0 else mask(lastEoFPosition + 1),
            })
            dataOut.append(outWord)

    # @hwt_expr_producer
    # @staticmethod
    # def frameEndsOnWordBoundaryOrWithEoF(beginI: int, buffer: list[HStruct]):
    #    """
    #    Check if frame beggining at index beginI in buffer ends
    #    """
    #    anyEoF = b0
    #    enabledUntilWordEnd = b1
    #    for b in buffer[beginI:]:
    #        # any eof or all valid until the end
    #        anyEoF = anyEoF | (b.user.enable & b.user.eof)
    #        enabledUntilWordEnd = enabledUntilWordEnd & b.user.enable
    #    return (enabledUntilWordEnd, anyEoF)

    # @hwt_expr_producer
    # def getFrameEndsOnWordBoundaryOrWithEoFFlags(self, buffer: list[HStruct]):
    #     frameEndsOnWordBoundary = []
    #     frameEndsWithEoF = []
    #     for i in range(self.IN_SEGMENT_CNT):
    #         allEn, anyEoF = self.frameEndsOnWordBoundaryOrWithEoF(i, buffer)
    #         frameEndsOnWordBoundary.append(allEn & ~anyEoF)
    #         frameEndsWithEoF.append(anyEoF)
    #
    #     return frameEndsOnWordBoundary, frameEndsWithEoF

    @hwt_expr_producer
    def buildSegmentPackingMux(self, prefixSum: list[AnyHBitsValue], buffer: list[HStruct], i: int):
        # :note: iterate prefix prefixSum and search for value i+1
        selectCases = [
            (prefixSumVal._eq(i + 1), nextBuffItem)
            for prefixSumVal, nextBuffItem in zip(prefixSum[i:], buffer[i:])  # select from segments at this index an every after
        ]
        IN_SEGMENT_T = self.getSegmentTy()
        selectRes = selectUsingCasesWithCondition(selectCases,
                                                  defaultVal=IN_SEGMENT_T.from_py({"user": {"enable": 0}}))
        return selectRes

    # @hwt_expr_producer
    # def buildSegmentPackingMux(self, itemInvalidPrefixSum: list[AnyHBitsValue], buffer: list[HStruct], i: int):
    #    """
    #    For a given destination index i construct a mux logic which will select the item from buffer based on prefix sum
    #    :note: if itemValidPrefixSum == n for segment on index i it means that there are n valid segments before
    #           if itemInvalidPrefixSum it means
    #    """
    #    # :note: iterate prefix prefixSum and search for value i+1
    #    selectCases = [
    #        (prefixSumVal._eq(i + 1), nextBuffItem)
    #        for prefixSumVal, nextBuffItem in zip(prefixSum[i:], buffer[i:])
    #    ]
    #    # the src item is on index where prefix sum ==
    #    srcSegmentIndex = i +
    #
    #    IN_SEGMENT_T = self.dataIn.T.element_t
    #    selectRes = selectUsingCasesWithCondition(selectCases,
    #                                              defaultVal=IN_SEGMENT_T.from_py({"user": {"enable": 0}}))
    #    return selectRes
    #
    @hlsBytecode
    def packSegmentsInBuffer(self, buffer: list[Axi4StreamSegmentedMockSegmentTy], itemValid: list[AnyHBitsValue]):
        # pack items in buffer (move all valid records to begin of the array)
        # itemInvalidPrefixSum = HwIOArray(prefixSum1bPerResultBinTreeBased(~itemValid, inclusive=False))
        itemValidPrefixSum = HwIOArray(prefixSum1bPerResultBinTreeBased(itemValid, inclusive=True))

        for i in range(len(buffer)):
            PyBytecodeBlockLabel(f"bb.setBuff{i:d}")
            # only items on index >= i may be shifted in to item on index i

            # e.g. itemValid     [ 0, 1, 1, 0, 1 ]
            #      prefixSum     [ 0, 1, 2, 2, 3 ]
            #      buffItemSrc   [ 1, 2, 4, -, - ] # :note: the index of the first item of prefixSumVal which has value of index + 1
            # :note: the src item can not be on possition less than i because that would imply that some new
            #    item appeared before this item during packing which is simply not possible
            selectRes = self.buildSegmentPackingMux(itemValidPrefixSum, buffer, i)
            self.setBuffItem(selectRes, i, buffer)
    
    @hlsBytecode
    def packSegmentsInWord(self, wordT: HStruct, inWord: list[Axi4StreamSegmentedMockSegmentTy]):
        IN_SEGMENT_CNT = self.IN_SEGMENT_CNT
        assert isinstance(wordT, HStruct), wordT
        # wordIndexT = HBits(log2ceil(IN_SEGMENT_CNT + 1))
        itemValid = [b.user.enable for b in inWord]
        _itemValid = Concat(*reversed(itemValid))
        itemEoF = Concat(*reversed([b.user.enable & b.user.eof for b in inWord]))

        segmentsValidCnt = ctpop(Concat(*reversed(itemValid)))  # :attention: must be done before packSegmentsInBuffer updates b.user.enable
        packedWord: Axi4streamSegmentedTxSegnemtBuffer_inWordPacking_outWordMockTy = wordT.from_py(None)
        sizeT = packedWord.segmentsEndingWithEoFCnt._dtype
        maskT = HBits(IN_SEGMENT_CNT)
        indexOfLastEoF = ctlz(itemEoF, is_zero_poison=False)
        maskForItemsBeforeEoF = lshr(maskT.from_py(mask(IN_SEGMENT_CNT)), indexOfLastEoF)
        packedWord.segmentsEndingWithEoFCnt = itemEoF._eq(0)._ternary(
            sizeT.from_py(0),
            ctpop(_itemValid & maskForItemsBeforeEoF)
        )
        # itemEoF._eq(0)._ternary(
        #    sizeT.from_py(0),
        #    (wordIndexT.from_py(self.IN_SEGMENT_CNT)  # MAX
        #     -ctpop(~_itemValid)  #  number of invalid
        #     -ctlz(itemEoF, is_zero_poison=False)  # the number of non-eof from the end 
        #     +ctlz(_itemValid, is_zero_poison=False)  # compensation for invalid at the end
        #    )
        # )
        PyBytecodeInline(self.packSegmentsInBuffer)(inWord, itemValid)

        # precompute values required for packing to final output word
        # _, frameEndsWithEoF = self.getFrameEndsOnWordBoundaryOrWithEoFFlags(inWord)
        packedWord.segments = HwIOArray(inWord)
        packedWord.segmentsValidCnt = segmentsValidCnt
        # packedWord.frameEndsOnWordBoundary = Concat(*reversed(frameEndsOnWordBoundary))
        # packedWord.frameEndsWithEoF = Concat(*reversed(frameEndsWithEoF))
        # segmentsEndingWithEofOrWordBoundary = cttz(packedWord.frameEndsOnWordBoundary | packedWord.frameEndsWithEoF)
        # packedWord.segmentsRequiredForLastNonEoFEndingFrame = segmentsEndingWithEofOrWordBoundary._dtype.from_py(len(inWord)) - segmentsEndingWithEofOrWordBoundary
        # packedWord.validCompleteItemCnt =
        return packedWord

    @hlsBytecode
    def thread_packSegmentsInWord(self, dataIn: IoProxyScalar, outWordIoOut: IoProxyScalar):
        """
        Pack segments in words before further processing
        so output word producing logic is as simple as possible.
        """
        wordT = outWordIoOut.interface.T
        assert isinstance(wordT, HStruct), wordT
        while b1:
            newD = dataIn.read()
            inWord: list[Axi4StreamSegmentedMockSegmentTy] = newD.data
            packedWord = PyBytecodeInline(self.packSegmentsInWord)(wordT, inWord)
            outWordIoOut.write(packedWord, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        t0 = HlsThreadFromPy(hls, self.thread_packSegmentsInWord, IoProxyScalar(hls, self.dataIn),
                                                                  IoProxyScalar(hls, self.dataOut))
        hls.addThread(t0)
        hls.compile()


if __name__ == "__main__":
    import sys
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtBuildsystem.vivado.part import XilinxPart
    from hwtHls.platform.xilinx.fromVitisDB import HlsPlatformFromVitisDB

    sys.setrecursionlimit(int(1e6))
    m = Axi4streamSegmentedTxSegnemtBuffer_inWordPacking()
    # m.SEGMENT_CNT = 2
    # m.SEGMENT_DATA_WIDTH = 128
    # m.CLK_FREQ = int(250e6)
    # m.USE_SOF = True
    # m.MAX_SEGMENTS_PER_LANE = 2
    # m.MIN_SEGMENTS_PER_LANE = 0

    m.SEGMENT_CNT = 16
    m.PACK_SEGMENT_DATA = True
    m.MAX_SEGMENTS_PER_LANE = 2
    m.MIN_SEGMENTS_PER_LANE = 0
    m.USE_SOF = True
    m.SEGMENT_DATA_WIDTH = 128
    m.CLK_FREQ = int(1e6)

    # p = XilinxPart
    # part = XilinxPart(
    #    p.Family.versalHbm,
    #    p.Size._1542,
    #    p.Package.lsva4737,
    #    p.Speedgrade._1LP)

    # targetPlatform = HlsPlatformFromVitisDB.getForPart(part,
    targetPlatform = VirtualHlsPlatform(
        llvmCliArgs=[
             # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
             # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        ],
        debugFilter=HlsDebugBundle.ALL_RELIABLE
    )

    print(to_rtl_str(m, target_platform=targetPlatform))
