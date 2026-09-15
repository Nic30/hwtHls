#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Union

from hwt.code import Or, Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hObjList import HObjList
from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStruct, HdlType_to_HwIO
from hwt.hwIOs.utils import addClkRstn, propagateClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.code import ctpop, ctlz
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel, \
    PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from tests.io.amba.axi4StreamSegmented.axi4ssSegmentMergeInputFifo import _Axi4ssSegmentMergeInputFifo


class Axi4SSStreamMerge(HwModule):
    """
    Merge multiple segmented streams into a a single one.
    
    Case 1: The frames are guaranteed to be non-overlaping
    * this is the most simple case as we can just take data as is and put it to output
    * this is often the case if frames were originiating from segmented stream and latency on all paths is the same
     and the fames were not extended.
    
    Case 2: The frames may overlap
    * this is the case if frames were originating from the same stream and were extended,
      or paths have different latency so some frames may have been swapped
      Case 2.1: The frames on input interfaces have fixed position of SoF
      * this may limit of troughput if frame size increase generates additional word because next frame had
        to be stalled as the data of frame reaches the segment where next frame was supposed to start
      * In this case we know the inititial possition of segment with SoF in stream this means that if packing
        data to output stream only 1 segment must be checked SoF and only shift happening is when putting data
        tx.
      Case 2.2: The rx frames may have SoF with any segment
      * All rx data must be shifted to start at segment 0, then shifted again when packing to tx 
    """
    AXI_CLS = Axi4StreamSegmented

    @override
    def hwConfig(self) -> None:
        self.INPUT_CNT = HwParam(2)
        self.INPUT_DATA_MAY_OVERPLAP = HwParam(True)
        self.SEGMENT_CNT = HwParam(1)
        self.SEGMENT_DATA_WIDTH = HwParam(64)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = HwIOArray(self.AXI_CLS() for _ in range(self.INPUT_CNT))
            self.tx = self.AXI_CLS()._m()
            if self.INPUT_DATA_MAY_OVERPLAP:
                self.rxBuffers = HObjList(_Axi4ssSegmentMergeInputFifo() for _ in range(self.INPUT_CNT))

    @hlsBytecode
    @classmethod
    def collectSegmentsFromInputBuffer(cls, SEGMENT_CNT: int,
                                       segmentsAlreadyFilledCnt: Union[int, HBitsRtlSignal],
                                       inIndex: int,
                                       inAvailable: tuple[HwIOStruct],
                                       dstSegmentMap: HObjList[HwIOStruct],
                                       popRequestTmpOut: HwIOStruct,
                                       ):
        # if there is not enough data nor EoF we have to stall everything
        hasEoF = Or(*(segUser.enable & segUser.eof for segUser in inAvailable))
        # if there is an eof, copy leftover unconditionally
        # :note: the data does not necessary start at the first segment
        # :note: len(inAvailable) == 2*SEGMENT_CNT
        availableCnt = ctpop(Concat(*(segUser.enable for segUser in inAvailable)))
        segmentIndexWidth = log2ceil(SEGMENT_CNT)
        segmentSizeWidth = log2ceil(SEGMENT_CNT + 1)
        segmentSizeT = HBits(segmentSizeWidth)
        segmentToFillCnt = segmentSizeT.from_py(SEGMENT_CNT) - (
            segmentsAlreadyFilledCnt
            if isinstance(segmentsAlreadyFilledCnt, int) else
            segmentsAlreadyFilledCnt._zext(segmentSizeWidth)
            )

        notEnoughData = ~hasEoF & (availableCnt < segmentToFillCnt._zext(availableCnt._dtype.bit_length()))
        emptySegmentsPrefixCnt = ctlz(Concat(*(segUser.enable for segUser in reversed(inAvailable))))  # reversed because of downto notation
        nonEoFSegmentPrefixCnt = ctlz(Concat(*(segUser.enable & ~segUser.eof for segUser in reversed(inAvailable))))
        frameSegmentCnt = nonEoFSegmentPrefixCnt - emptySegmentsPrefixCnt

        for segI in range(SEGMENT_CNT):
            if (frameSegmentCnt._dtype.from_py(segI) < frameSegmentCnt) & (segmentsAlreadyFilledCnt <= segI):
                dstSegmentMap[segI].inputI = inIndex
                # :note: truncat is required because the type was extended to avoid overflows
                # :note: 2 segment 2 inputs = 12 cases in dstSegmentMap[segI].segmentI mux
                #        3 segment 3 inputs = 48 cases
                #        4 segment 4 inputs = 96 cases
                beginSegmentIndex = emptySegmentsPrefixCnt + segI
                beginSegmentIndex = (beginSegmentIndex < SEGMENT_CNT)._ternary(beginSegmentIndex,
                                                                               beginSegmentIndex - SEGMENT_CNT)
                dstSegmentMap[segI].segmentI = beginSegmentIndex._trunc(segmentIndexWidth)
                del beginSegmentIndex

        @hwt_expr_producer
        def segmentIsSelected(segI: int):
            enForW0Segments = (emptySegmentsPrefixCnt <= segI) & \
                              (emptySegmentsPrefixCnt + availableCnt > segI)
            return enForW0Segments

        popRequestTmpOut.enable = Concat(*(
            ~notEnoughData & (segmentIsSelected(segI) | segmentIsSelected(segI + SEGMENT_CNT))
            for segI in reversed(range(SEGMENT_CNT))
        ))

        popRequestTmpOut.wordIndex = Concat(*(
            segmentIsSelected(segI + SEGMENT_CNT)
            for segI in reversed(range(SEGMENT_CNT))
        ))

        return frameSegmentCnt._trunc(frameSegmentCnt._dtype.bit_length() - 1), notEnoughData

    @hlsBytecode
    @classmethod
    def resolveWhichSegmentsToPopFromAllInputs(cls, hls: HlsScope,
                                               INPUT_CNT: int,
                                               SEGMENT_CNT: int,
                                               availableSegmentTy: HStruct,
                                               available: tuple[tuple[HStruct, ...]],
                                               popRequestT: HStruct,
                                               pendingFrameInIndex: HBitsRtlSignal,
                                               pendingFrameInIndexVld:HBitsRtlSignal):
        """
        decide which bytes to take from which input
        * = for each output segment decide from which input segment it should take the data
        * if last word ended without EoF the remaining data of frame must be put first
        * the rest of data can be build from complete frames from any input and from beginning of the frame
          if we have enough segments to fill output word.
        """
        inline = PyBytecodeInline

        # :note: popRequestTmp is used to consume data from stream
        popRequestTmp = hls.var("popRequestTmp", popRequestT[INPUT_CNT], arrayPartitionComplete=True)
        for tmp in popRequestTmp:
            tmp.enable = 0
            del tmp
        # :note: dstSegmentMap is used to pack segments which were just received from input buffer into output word
        dstSegmentMap = hls.var("dstSegmentMap",
            HStruct(
                (HBits(log2ceil(INPUT_CNT)), "inputI"),
                (HBits(log2ceil(SEGMENT_CNT)), "segmentI"),
            )[SEGMENT_CNT],
            arrayPartitionComplete=True)

        curSegmentsCollected = HBits(log2ceil(SEGMENT_CNT + 1)).from_py(0)
        pendigFrameDataNotAvailable = b0

        if pendingFrameInIndexVld:
            PyBytecodeBlockLabel("bb.resolveWhichSegmentsToPopFromAllInputs.pendingVld")
            inAvailableTmp = [[] for _ in range(2 * SEGMENT_CNT)]
            for segmentsOfInput in available.user:
                for segI, seg in enumerate(segmentsOfInput):
                    inAvailableTmp[segI].append(seg)
                    del seg

            inAvailable = hls.var("inAvailable", availableSegmentTy[2 * SEGMENT_CNT], arrayPartitionComplete=True)
            for i, segNForInputs in enumerate(inAvailableTmp):
                inAvailable[i](segNForInputs[pendingFrameInIndex])
                del segNForInputs
            # inAvailable = available[pendingFrameInIndex]
            curSegmentsCollected, pendigFrameDataNotAvailable = inline(cls.collectSegmentsFromInputBuffer)(
                SEGMENT_CNT, 0, pendingFrameInIndex, inAvailable, dstSegmentMap, popRequestTmp[pendingFrameInIndex])
            del inAvailable

        if ~pendigFrameDataNotAvailable:
            PyBytecodeBlockLabel("bb.resolveWhichSegmentsToPopFromAllInputs.hasData")
            # [todo] round-robin duplicate available 2x and then use arbiter state to skip first iterations which are
            #        not prioritized and skip tail iterations which were already performed on beginning if arbiter
            #        state was low enough
            # [todo] support for read of more than just leftover+ 1 frame from each input in a single step
            inAvailable = None
            for inI, inAvailable in enumerate(available.user):
                if ~(pendingFrameInIndexVld & pendingFrameInIndex._eq(inI)):
                    PyBytecodeBlockLabel(f"bb.resolveWhichSegmentsToPopFromAllInputs.consume{inI:d}")
                    curSegmentsCollected, pendigFrameDataNotAvailable = inline(cls.collectSegmentsFromInputBuffer)(
                        SEGMENT_CNT, curSegmentsCollected, inI, inAvailable, dstSegmentMap, popRequestTmp[inI])
                del inAvailable
        del curSegmentsCollected

        return popRequestTmp, dstSegmentMap

    @hlsBytecode
    def mergeOverlappingThread(self, hls: HlsScope,
                               availableSegmentTy: HStruct,
                               loadedSegmentsIn: HwIOStruct,
                               popRequestOut: HwIOStruct,
                               popDataIn: HwIOStruct,
                               tx: Axi4StreamSegmented):
        inline = PyBytecodeInline
        popRequestT = self.rxBuffers[0].popRequest._dtype
        INPUT_CNT = self.INPUT_CNT
        SEGMENT_CNT = self.SEGMENT_CNT

        # index of the input which have unfinished frame from previous word
        # the data from this input must be put at the begining of the output word
        pendingFrameInIndex = HBits(log2ceil(INPUT_CNT)).from_py(None)
        pendingFrameInIndexVld = b0
        while b1:
            PyBytecodeBlockLabel("bb.mergeOverlappingThreadLoop")
            # read available segments (:note: see availableSegmentsTy)
            available = hls.read(loadedSegmentsIn).data

            # available: list[list[HStruct]] = [
            #    hls.read(rxBuff.loadedSegments).data
            #    for rxBuff in rxBuffers
            # ]

            # From each input we received up to 1 full word
            #   eg |0|1|2|
            # * this word may have some shift (as there was word starting on some offset and the rest was taken from second word)
            #   eg shift=1 |2|0|1|
            # * it is not necessary for all segments to be occupied
            #   eg shift=1 |x|0|1|
            # * the frame from input must end with eof or there must be enough data to fill output word until the end
            popRequestTmp, dstSegmentMap = inline(self.resolveWhichSegmentsToPopFromAllInputs)(
                hls, INPUT_CNT, SEGMENT_CNT, availableSegmentTy, available, popRequestT, pendingFrameInIndex, pendingFrameInIndexVld)
            # for inI, rxBuff in enumerate(rxBuffers):
            #    rxBuff: _Axi4ssSegmentMergeInputFifo
            #    PyBytecodeBlockLabel(f"bb.rxBuff{inI:d}.popRequest.wr")
            #    hls.write(popRequestTmp[inI], rxBuff.popRequest, mayBecomeFlushable=False)
            hls.write(HwIOArray(popRequestTmp), popRequestOut, mayBecomeFlushable=False)

            PyBytecodeBlockLabel("bb.rxBuff.popData.rd")
            # inputData = [hls.read(rxBuff.popData).data for rxBuff in rxBuffers]
            inputData = hls.read(popDataIn).data

            txWordTmp = tx.WORD_T.from_py(None)
            for segI, segInputSel in enumerate(dstSegmentMap):
                PyBytecodeBlockLabel(f"bb.txWordSeg{segI:d}")
                inputSegments = inputData.data[segInputSel.inputI]
                txWordTmp.data[segI] = inputSegments.data[segInputSel.segmentI]
                txWordTmp.user[segI] = inputSegments.user[segInputSel.segmentI]
                del inputSegments

            allEnableBits = []
            for inputDataWord in inputData.data:
                allEnableBits.extend(user.enable for user in inputDataWord.user)

            hasAnyDataToSend = Concat(*reversed(allEnableBits)) != 0
            if hasAnyDataToSend:
                PyBytecodeBlockLabel("bb.txWrite")
                # [todo] loop multiple backedges (something conditional at the end int this case)
                #   and some simple variable to split the loops (pendingFrameInIndexVld)
                #   will be split by llvm separateNestedLoop which introduces overhead later
                hls.write(txWordTmp, tx, mayBecomeFlushable=True)
                lastSegment = txWordTmp.user[SEGMENT_CNT - 1]
                pendingFrameInIndexVld = lastSegment.enable & ~lastSegment.eof
                pendingFrameInIndex = dstSegmentMap[SEGMENT_CNT - 1].inputI

            PyBytecodeBlockLabel("bb.mergeOverlappingThreadLoop.latch")

    def mergeNonOverplappingThread(self, hls: HlsScope):
        while b1:
            inputWords = [hls.read(rx, dtype=rx.WORD_T, blocking=False) for rx in self.rx]
            txWordTmp = self.tx.WORD_T.from_py(None)
            for segI in range(self.SEGMENT_CNT):
                segUserTmp = txWordTmp.user[0]._dtype.from_py({"enable": 0})
                segDataTmp = txWordTmp.data[0]._dtype.from_py(None)
                for inputWord in inputWords:
                    segUser = inputWord.data.user[segI]
                    if inputWord.valid & segUser.enable:
                        segUserTmp = segUser
                        segDataTmp = inputWord.data.data[segI]
                txWordTmp.user[segI] = segUserTmp
                txWordTmp.data[segI] = segDataTmp
            if Concat(*(inpWord.valid for inpWord in inputWords)) != 0:
                hls.write(txWordTmp, self.tx, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        propagateClkRstn(self)
        hls = HlsScope(self, namePrefix="")
        if self.INPUT_DATA_MAY_OVERPLAP:
            for rx, buff in zip(self.rx, self.rxBuffers):
                buff.rx(rx)
            # input buff used as container of configuration
            refRxBuff: _Axi4ssSegmentMergeInputFifo = self.rxBuffers[0]
            # aggregate ports of rxBuffers into wide vectorized ports
            # to reduce number of IO to simplify scheduling and buffer opt.
            availableSegmentTy = refRxBuff.rx.USER_SEGMENT_T
            availableSegmentsTy = HStruct(
                (availableSegmentTy[2 * self.SEGMENT_CNT][self.INPUT_CNT], "user")
            )
            loadedSegmentsIn: HwIOStruct = HdlType_to_HwIO().apply(availableSegmentsTy)
            self.loadedSegmentsIn = loadedSegmentsIn
            for rxBuff, loadedSegmentsInForIn in zip(self.rxBuffers, loadedSegmentsIn.user):
                assert len(rxBuff.loadedSegments.user) == len(loadedSegmentsInForIn)
                for (segmentUser, segmentUserIn) in zip(rxBuff.loadedSegments.user, loadedSegmentsInForIn):
                    segmentUserIn(segmentUser)

            popRequestTy = refRxBuff.popRequest._dtype
            popRequestOut: HwIOStruct = HdlType_to_HwIO().apply(
                HStruct((popRequestTy[self.INPUT_CNT], "req"))
            )
            self.popRequestOut = popRequestOut
            for rxBuff, popRequestOutForIn in zip(self.rxBuffers, popRequestOut.req):
                rxBuff.popRequest(popRequestOutForIn)

            popDataTy = refRxBuff.popData._dtype
            popDataIn: HwIOStruct = HdlType_to_HwIO().apply(
                HStruct((popDataTy[self.INPUT_CNT], "data"))
            )
            self.popDataIn = popDataIn
            for rxBuff, popDataInForIn in zip(self.rxBuffers, popDataIn.data):
                popDataInForIn(rxBuff.popData)

            hls.addThread(HlsThreadFromPy(hls, self.mergeOverlappingThread, hls, availableSegmentTy, loadedSegmentsIn, popRequestOut, popDataIn, self.tx))
        else:
            hls.addThread(HlsThreadFromPy(hls, self.mergeNonOverplappingThread, hls))

        hls.compile()


# import sqlite3
# import os
# import datetime
# from hwtBuildsystem.vivado.executor import VivadoExecutor
# from hwtBuildsystem.vivado.part import XilinxPart
# from hwtBuildsystem.examples.synthetizeHwModule import buildHwModule, \
#   store_vivado_report_in_db
# from multiprocessing import Pool
# from hwtHls.platform.xilinx.fromVitisDB import HlsPlatformFromVitisDB
# 
# 
# def runCompilation(args):
#     INPUT_CNT, SEGMENT_CNT, INPUT_DATA_MAY_OVERPLAP = args
#     conn = sqlite3.connect('build_report.db')
#     c = conn.cursor()
#     name = f"Axi4SSStreamMerge_100M_{INPUT_CNT}inp_{SEGMENT_CNT:d}s_sw128_mayOverlap{int(INPUT_DATA_MAY_OVERPLAP):d}"
#     try:
#        if is_vivado_report_build(conn, name):
#            print(f"{name}: already build")
#            return                 return
#     except sqlite3.OperationalError:
#         pass  # "no such table" on the first run
# 
#     logComunication = False
#     m = Axi4SSStreamMerge()
#     m.SEGMENT_DATA_WIDTH = 128
#     m.SEGMENT_CNT = SEGMENT_CNT
#     m.INPUT_CNT = INPUT_CNT
#     m.INPUT_DATA_MAY_OVERPLAP = INPUT_DATA_MAY_OVERPLAP
#     m.CLK_FREQ = int(1e6)
# 
#     start = datetime.datetime.now()
#     with VivadoExecutor(logComunication=logComunication) as executor:
#         p = XilinxPart
#         # part = XilinxPart(
#         #        __pb.Family.kintex7,
#         #        __pb.Size._160t,
#         #        __pb.Package.ffg676,
#         #        __pb.Speedgrade._2)
#         part = XilinxPart(
#            p.Family.versalHbm,
#            p.Size._1542,
#            p.Package.lsva4737,
#            p.Speedgrade._1LP)
#         
#         targetPlatform = HlsPlatformFromVitisDB.getForPart(part, f"tmp/hls_{name:s}")
#         try:
#             project, hwt_build_start, hwt_build_end = buildHwModule(
#                 executor, m, f"tmp/vivado_{name:s}", part,
#                 targetPlatform=targetPlatform,
#                 synthesize=True,
#                 implement=False,
#                 writeBitstream=False,
#                 # openGui=True,
#                 )
#         except Exception as e:
#             print(name, "failed", e)
#             return
# 
#         store_vivado_report_in_db(c, start, hwt_build_start, hwt_build_end, project, name)
#         conn.commit()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    import sys
    sys.setrecursionlimit(int(1e4))

    m = Axi4SSStreamMerge()
    m.SEGMENT_DATA_WIDTH = 128
    m.INPUT_DATA_MAY_OVERPLAP = True
    m.SEGMENT_CNT = 4
    m.INPUT_CNT = 4
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(
         # debugFilter=HlsDebugBundle.ALL_RELIABLE,
         llvmCliArgs=[
             # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
             # LLVM_CLI_COMMON_OPTS.TIME_PASSES,
             # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
             # LLVM_CLI_COMMON_OPTS.filterPrintFuncs(["Axi4SSStreamMerge.mergeOverlappingThread"]),
             LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        ])
    # seg inp   lut  ff  time[s]
    #  10  10 60383 175 1016.50
    #   9   9 43629 150  276.25
    #   8   8 28894 137  124.79
    #   6   6 16988  85   18.60
    #   4   4  7336  74    8.90
    #   2   2   882  32    2.00

    # seg inp   lut  ff time[s]
    #   8   8
    #   8   7
    #   8   6
    #   8   5
    #   8   4
    #   8   3
    #   8   2

    # # tasks = #[(8, inpCnt, True) for inpCnt in range(2, 16 + 1)]
    # tasks = [(3, 3, True), (5, 5, True), (8, 8, True), 
    #          (3, 3, False), (5, 5, False), (8, 8, False),]
    # # tasks = [(8, 2, True) ]
    # # for t in tasks:
    # #    runCompilation(t)
    # with Pool(6) as p:
    #     print(p.map(runCompilation, tasks))

    import time
    start_time = time.time()
    # import cProfile
    # pr = cProfile.Profile()
    # pr.enable()
    print(to_rtl_str(m, target_platform=p))
    # pr.disable()
    # pr.dump_stats('profile.prof')

    print("--- %s seconds ---" % (time.time() - start_time))
