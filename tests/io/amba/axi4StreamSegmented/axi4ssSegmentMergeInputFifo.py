#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HdlType_to_HwIO, HwIOStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented


@serializeParamsUniq
class _Axi4ssSegmentMergeInputFifo(HwModule):
    """
    This FIFO allows to read just some selected segments from current read word and previous one.
    It is used to pop specific segments of data in :class:`Axi4SSStreamMerge`
    """

    @override
    def hwConfig(self) -> None:
        self.SEGMENT_CNT = HwParam(1)
        self.SEGMENT_DATA_WIDTH = HwParam(64)
        self.CLK_FREQ = HwParam(int(100e6))
        self.DEPTH = HwParam(4)

    @override
    def hwDeclr(self):
        assert self.DEPTH >= 2
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = Axi4StreamSegmented()
        self.rx.resolveTypes()
        SEGMENT_CNT = self.SEGMENT_CNT
        self.loadedSegments = HdlType_to_HwIO().apply(
            HStruct(
                (self.rx.USER_SEGMENT_T[2 * SEGMENT_CNT], "user"),
            )
        )._m()
        self.popRequest = HdlType_to_HwIO().apply(
            HStruct(
               (HBits(self.SEGMENT_CNT), "wordOffset"),
               (HBits(self.SEGMENT_CNT), "enable"),
            )
         )
        self.popData = HdlType_to_HwIO().apply(
            HStruct(
                (HBits(self.SEGMENT_DATA_WIDTH)[SEGMENT_CNT], "data"),
                (self.rx.USER_SEGMENT_T[SEGMENT_CNT], "user"),
            )
        )._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope,
                   rxIn: Axi4StreamSegmented,
                   loadedSegmentsOut: HwIOStruct,
                   popRequestIn: HwIOStruct,
                   popDataOut: HwIOStruct):
        # based on https://vhdlguru.blogspot.com/2010/03/basic-model-of-fifo-queue-in-vhdl.html
        DEPTH = self.DEPTH
        SEGMENT_CNT = self.SEGMENT_CNT
        fifoPtr_t = HBits(log2ceil(DEPTH + 1))

        # reader position, writer position fifo pointers + elementCnt for better timing
        rdPos = fifoPtr_t.from_py(0)
        rdPosPlus1 = fifoPtr_t.from_py(1)

        wrPos = fifoPtr_t.from_py(0)
        elementCnt = fifoPtr_t.from_py(0)
        # holds info about which segments from word at rdPos
        curWordConsumedSegments = HBits(SEGMENT_CNT).from_py(0)

        # empty/full fifo flags with support for read of data from 2 words in FIFO
        emptyForReadOf1w = b1
        emptyForReadOf2w = b1
        full = b0

        # memory for data and user segment from segmented interface
        # the data/user is split as user requres 2 or 3 read ports while data just 1 (and is much wider)
        # the memories are split to segments because each segment  can be read from rdPos or rdPos+1 word
        dataRams = [
            hls.var(f"memSegment{segI:d}Data", HBits(self.SEGMENT_DATA_WIDTH)[DEPTH])
            for segI in range(SEGMENT_CNT)
        ]

        userRams = [
            hls.var(f"memSegment{segI:d}User", rxIn.USER_SEGMENT_T[DEPTH])
            for segI in range(SEGMENT_CNT)
        ]
        DEPTH_MAX = DEPTH - 1
        while b1:
            PyBytecodeBlockLabel("bb.mainLoop")

            # output loaded segments
            loadedSegmentsTmp = self.loadedSegments._dtype.from_py(None)
            for segmentI in range(SEGMENT_CNT):
                PyBytecodeBlockLabel(f"bb.loadedSegmentsTmp{segmentI:d}")
                user = userRams[segmentI][rdPos]
                user.enable &= curWordConsumedSegments[segmentI] & ~emptyForReadOf1w
                loadedSegmentsTmp.user[segmentI] = user
                del user
                user = userRams[segmentI][rdPosPlus1]
                user.enable &= ~emptyForReadOf2w
                loadedSegmentsTmp.user[SEGMENT_CNT + segmentI] = user
                del user
            hls.write(loadedSegmentsTmp, loadedSegmentsOut, mayBecomeFlushable=False)

            popRequest = hls.read(popRequestIn).data
            # read part
            outWordTmp = self.popData._dtype.from_py(None)
            for segmentI in range(SEGMENT_CNT):
                PyBytecodeBlockLabel(f"bb.outWordTmp{segmentI:d}")
                segOff = popRequest.wordOffset[segmentI]
                assert segOff._dtype.bit_length() == 1
                rdPtr = segOff._ternary(rdPosPlus1, rdPos)
                outWordTmp.data[segmentI] = dataRams[segmentI][rdPtr]
                user = userRams[segmentI][rdPtr]
                # user  = _user._reinterpret_cast(rxIn.USER_SEGMENT_T)
                # print(user, dir(user))
                user.enable &= segOff | ~curWordConsumedSegments[segmentI]
                outWordTmp.user[segmentI] = user
                # del _user
                del user
                del rdPtr
                del segOff

            # [todo] update curWordConsumedSegments
            # read position update part

            PyBytecodeBlockLabel(f"bb.rdPosUpdate")
            isReadEn = popRequest.enable != 0
            isReadOf2w = isReadEn & (popRequest.wordOffset != 0)
            if isReadOf2w:
                # read of 2 words
                if rdPos._eq(DEPTH_MAX - 1):
                    rdPos = 1
                    rdPosPlus1 = 2 % DEPTH_MAX
                elif rdPos._eq(DEPTH_MAX - 2):
                    rdPos = 0
                    rdPosPlus1 = 1
                else:
                    rdPos += 2
                    if rdPos._eq(DEPTH_MAX - 3):
                        rdPosPlus1 = 0
                    else:
                        rdPosPlus1 += 2
                elementCnt -= 2

            elif isReadEn:
                # read of 1 word
                if rdPos._eq(DEPTH_MAX - 1):
                    rdPos = 0
                else:
                    rdPos += 1
                elementCnt -= 1
            del isReadEn
            del isReadOf2w

            # write part
            rxData = hls.read(rxIn, dtype=rxIn.WORD_T, blocking=False)
            if rxData.valid & ~full:
                PyBytecodeBlockLabel("bb.write")
                # copy the data from rx to dataRams/userRams as is
                for segmentI in range(SEGMENT_CNT):
                    PyBytecodeBlockLabel(f"bb.dataStoreLoop{segmentI:d}")

                    dataRams[segmentI][wrPos] = rxData.data.data[segmentI]
                    userRams[segmentI][wrPos] = rxData.data.user[segmentI]

                PyBytecodeBlockLabel("bb.wrPosUpdate")
                if wrPos._eq(DEPTH_MAX - 1):
                    wrPos = 0
                else:
                    wrPos += 1

                elementCnt += 1

            PyBytecodeBlockLabel("bb.flagUpdate")
            # setting empty and full flags.
            emptyForReadOf1w = elementCnt._eq(0)
            emptyForReadOf2w = elementCnt < 1
            full = elementCnt._eq(DEPTH)

            # write manually sinked at bottom for more simple compilation
            hls.write(outWordTmp, popDataOut, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, self.rx, self.loadedSegments, self.popRequest, self.popData))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    m = _Axi4ssSegmentMergeInputFifo()
    m.SEGMENT_DATA_WIDTH = 128
    m.SEGMENT_CNT = 4
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
         llvmCliArgs=[
             # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
             # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        ])
    # SEGMENT_CNT  LUT  FF  time[s]
    #          16  2216  6  6.42
    #           8  1103 15  3.41
    #           4  1008 21  2.16
    #           2  293  15  1.61
    import time
    start_time = time.time()
    # import cProfile
    # pr = cProfile.Profile()
    # pr.enable()
    print(to_rtl_str(m, target_platform=p))
    # pr.disable()
    # pr.dump_stats('profile.prof')

    print("--- %s seconds ---" % (time.time() - start_time))
