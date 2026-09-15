#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from itertools import islice

from hwt.hObjList import HObjList
from hwt.hdl.commonConstants import b1, b0
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.frontend.pragmaPreproc import PyBytecodePreprocHwCopy, \
    PyBytecodeBlockLabel


class Axi4SSStreamUnmerge(HwModule):
    """
    Split segmented stream into multiple stream each having same number of segments,
    but the new frame starting only in a single segment defined by index of output stream.
    This means that each word will typically have data from only a single frame,
    and the last/first word having potentially data from 1 previous and 1 new frame. 

    :note: Segment data is never shifted as the input frames may never ovelap with itself.
        If two frames are using same bytes of the segment they must have arrived in the different times
        so there must be enough time to tranmit them as they are without any shift.
    """
    AXI_CLS = Axi4StreamSegmented

    @override
    def hwConfig(self) -> None:
        self.SEGMENT_CNT = HwParam(4)
        self.SEGMENT_DATA_WIDTH = HwParam(128)
        self.USE_SOF = HwParam(True)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = self.AXI_CLS()
            self.tx = HObjList(self.AXI_CLS()._m() for _ in range(self.SEGMENT_CNT))

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: Axi4StreamSegmented, tx: tuple[Axi4StreamSegmented, ...]):
        # load rx word, distribute it to tx outputs
        SEGMENT_CNT = self.SEGMENT_CNT
        wordTy = rx.WORD_T

        # variables to assert that data is always forwarded to correct output if frame overlaps to next word
        hasAnyPendingPacket = b0
        pendingTxIndex = HBits(log2ceil(len(tx))).from_py(None)
        while b1:
            PyBytecodeBlockLabel(f"bb.rxLoop")
            rxSegments = hls.read(rx, dtype=wordTy).data

            for segmentIndex in range(SEGMENT_CNT):
                PyBytecodeBlockLabel(f"bb.tx{segmentIndex:d}Loop")
                # each output tx channel frame is bound to start at segmentIndex
                # the prefix may be continuation of the frame from previous word
                # or it may be invalid otherwise
                # The data for segmentIndex-th segment and later may also be from previous frame or there
                # may be a a new frame starting exactly at segmentIndex
                txWordTmp = wordTy.from_py(None)
                for i in range(SEGMENT_CNT):
                    PyBytecodeBlockLabel(f"bb.tx{segmentIndex:d}.segment{i:d}")
                    # copy all data as is
                    txWordTmp.data[i] = PyBytecodePreprocHwCopy(rxSegments.data[i])
                    txWordTmp.user[i] = PyBytecodePreprocHwCopy(rxSegments.user[i])
                    extraEn = BIT.from_py(None)
                    if i < segmentIndex:
                        # enabled if it is leftover
                        extraEn = hasAnyPendingPacket & pendingTxIndex._eq(segmentIndex)
                    else:
                        # enabled if new frame is starting at segmentIndex and no eof is between
                        # or previous frame which started on segmentIndex is continuing to this segment
                        hasEoFBefore = b0
                        for rxSegPred in islice(rxSegments.user, 0, segmentIndex):
                            hasEoFBefore |= rxSegPred.enable & rxSegPred.eof
                        hasEoFBetween = b0
                        for rxSegSuc in islice(rxSegments.user, segmentIndex + 1, None):
                            hasEoFBefore |= rxSegSuc.enable & rxSegSuc.eof

                        extraEn = (hasAnyPendingPacket & pendingTxIndex._eq(segmentIndex) & ~hasEoFBefore) | \
                            (rxSegments.user[segmentIndex].enable & rxSegments.user[segmentIndex].sof & hasEoFBetween)

                    txWordTmp.user[i].enable &= extraEn

                PyBytecodeBlockLabel("bb.txWrite")
                hls.write(txWordTmp, tx[segmentIndex], mayBecomeFlushable=False)

            # there is pending frame data if last word segment contains data, but is is not last data of frame
            PyBytecodeBlockLabel("bb.pktOverlapResovle")
            lastSegmentUser = rxSegments.user[SEGMENT_CNT - 1]
            hasAnyPendingPacket = lastSegmentUser.enable & ~lastSegmentUser.eof

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, self.rx, self.tx))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    m = Axi4SSStreamUnmerge()
    m.SEGMENT_DATA_WIDTH = 128
    m.SEGMENT_CNT = 4
    
    p = VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
         llvmCliArgs=[
             #LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
             #LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        ])
    print(to_rtl_str(m, target_platform=p))
