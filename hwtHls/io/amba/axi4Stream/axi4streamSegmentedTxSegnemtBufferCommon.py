from typing import Optional

from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented, \
    Axi4StreamSegmentedMockSegmentTy


class Axi4streamSegmentedTxSegnemtBufferCommon(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        Axi4StreamSegmented.hwConfig(self)
        self.MIN_SEGMENTS_PER_LANE = HwParam(1)
        self.MAX_SEGMENTS_PER_LANE = HwParam(1)
        self._DBG_IS_SIM = False
        self._segmentTy: Optional[HStruct] = None
        self._packedWordTy: Optional[HStruct] = None
        self._axi4ssWordTy: Optional[HStruct] = None
        self._outSegmentTy: Optional[HStruct] = None

    def getSegmentTy(self) -> HStruct:
        IN_SEGMENT_T = self._segmentTy
        if IN_SEGMENT_T is None:
            axi = Axi4StreamSegmented()
            axi._updateHwParamsFrom(self)
            axi.SEGMENT_CNT = self.SEGMENT_CNT * self.MAX_SEGMENTS_PER_LANE
            axi.resolveTypes()
            USER_T = axi.USER_SEGMENT_T
            IN_SEGMENT_T = HStruct(
                (HBits(self.SEGMENT_DATA_WIDTH), "data"),
                (USER_T, "user")
            )
            self._segmentTy = IN_SEGMENT_T

        return IN_SEGMENT_T

    def getPackedWordTy(self) -> HStruct:
        T = self._packedWordTy
        if T is None:
            IN_SEGMENT_CNT = self.SEGMENT_CNT * self.MAX_SEGMENTS_PER_LANE
            segmentT = self.getSegmentTy()
            wordSizeT = HBits(log2ceil(IN_SEGMENT_CNT + 1))
            T = HStruct(
                # data for indivisual segments
                (segmentT[IN_SEGMENT_CNT], "segments"),
                # how many segments of data has enable=1
                (wordSizeT, "segmentsValidCnt"),
                # how many segments have enable=1 and there is segment with eof=1 for this frame
                # (wordSizeT, "validCompleteItemCnt"),
                # if the frame ends with eof this is 0 else the number of segments until end of frame
                # (HBits(log2ceil(self.SEGMENT_CNT)), "segmentsRequiredForLastNonEoFEndingFrame"),
                # mask of flags which is 1 (for all segments of frame) if the frame ends exactly at the word boundary
                # (may or may not have eof)
                # (HBits(IN_SEGMENT_CNT), "frameEndsOnWordBoundary"),
                # mask of flags which is 1 (for all segments of frame) if the frame ends with eof
                # (HBits(IN_SEGMENT_CNT), "frameEndsWithEoF"),
                (wordSizeT, "segmentsEndingWithEoFCnt"),

            )
            self._packedWordTy = T

        return T

    def getOutSegmentTy(self) -> HStruct:
        OUT_SEGMENT_T = self._outSegmentTy
        if OUT_SEGMENT_T is None:
            axi = Axi4StreamSegmented()
            axi._updateHwParamsFrom(self)
            axi.SEGMENT_CNT = self.SEGMENT_CNT
            axi.resolveTypes()
            USER_T = axi.USER_SEGMENT_T
            OUT_SEGMENT_T = HStruct(
                (HBits(self.SEGMENT_DATA_WIDTH), "data"),
                (USER_T, "user")
            )
            self._outSegmentTy = OUT_SEGMENT_T

        return OUT_SEGMENT_T

    def getAxi4SSWordTy(self):
        AXI4SS_WORD_T = self._axi4ssWordTy
        if AXI4SS_WORD_T is None:
            OUT_SEGMENT_T = self.getOutSegmentTy()
            SEGMENT_CNT = self.SEGMENT_CNT
            AXI4SS_WORD_T = HStruct(
                (OUT_SEGMENT_T.field_by_name["data"].dtype[SEGMENT_CNT], "data"),
                (OUT_SEGMENT_T.field_by_name["user"].dtype[SEGMENT_CNT], "user"),
            )
            self._axi4ssWordTy = AXI4SS_WORD_T
        return AXI4SS_WORD_T

    @hwt_expr_producer
    def setBuffItem(self, src: Axi4StreamSegmentedMockSegmentTy, i: int, dstArr: list[Axi4StreamSegmentedMockSegmentTy]):
        """
        Utility function which copies struct fields in python way or construct assignment statements for conversion to HW
        :note: reason why this exit is that dst is placed in python list and direct assignment would just replace
            reference instead of generating store for LLVM
        """
        if self._DBG_IS_SIM:
            dstArr[i] = src
        else:
            return dstArr[i](src)
