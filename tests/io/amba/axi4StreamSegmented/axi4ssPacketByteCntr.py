#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.code import zextToTy
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.statementsRead import HlsRead
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4StreamSegmented
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4StreamSegmented
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.types.ctypes import uint16_t
from hwtHls.frontend.pragmaLoop import PyBytecodeStreamSegmentLoopUnroll,\
    PyBytecodeStreamLoopUnroll


class Axi4SSPacketByteCntr_readBusWord(HwModule):
    """
    Counts a total number of bytes in any word seen.
    """

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.SEGMENT_DATA_WIDTH = HwParam(64)
        self.SEGMENT_CNT = HwParam(1)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        i = self.i = Axi4StreamSegmented()
        i.SEGMENT_DATA_WIDTH = self.SEGMENT_DATA_WIDTH
        i.SEGMENT_CNT = self.SEGMENT_CNT

        self.byte_cnt: HwIODataRdVld = HwIODataRdVld()._m()
        self.byte_cnt.DATA_WIDTH = 16

    @hwt_expr_producer
    def segmentByteCnt(self, segmentUser: HStructConstBase) -> AnyHBitsValue:
        src: Axi4StreamSegmented = self.i
        dataBytesCnt = src.SEGMENT_DATA_WIDTH // src.BYTE_WIDTH
        if src._hasEmpty(src.SEGMENT_DATA_WIDTH, src.BYTE_WIDTH, src.SUPPORT_ZLP):
            sizeT = HBits(segmentUser.empty._dtype.bit_length() + 1)
            # setHasNoUnsignedWrap
            size = sizeT.from_py(dataBytesCnt) - zextToTy(segmentUser.empty, sizeT)
        else:
            size = HBits(log2ceil(dataBytesCnt + 1)).from_py(dataBytesCnt)
        if src._hasEnable(src.SEGMENT_CNT):
            size = segmentUser.enable._ternary(size, size._dtype.from_py(0))

        return size

    def mainThread(self, hls: HlsScope, i: IoProxyScalar):
        """
        read each word manually and sum number of bytes from each segment 
        """
        byte_cnt = uint16_t.from_py(0)
        while b1:
            word: HlsRead = i.read()
            for segment in word.data.user:
                segmentByteCntVal = self.segmentByteCnt(segment)
                byte_cnt += zextToTy(segmentByteCntVal, byte_cnt._dtype)
                # delete to simplify translation to llvm ir (limit variable life) 
                del segmentByteCntVal
                del segment

            hls.write(byte_cnt, self.byte_cnt)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        i = IoProxyScalar(hls, self.i)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, i)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SSPacketByteCntr_readSegmentWord(Axi4SSPacketByteCntr_readBusWord):
    """
    Counts a total number of bytes in any word seen.
    """

    @override
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4StreamSegmented):
        byte_cnt = uint16_t.from_py(0)
        while b1:
            i.readStartOfFrame()
            wordTy = HBits(self.SEGMENT_DATA_WIDTH)
            while b1:
                word: HlsStmReadAxi4StreamSegmented = i.read(wordTy, reliable=False)
                byte_cnt += zextToTy(word.getSize(), byte_cnt._dtype)
                hls.write(byte_cnt, self.byte_cnt)
                if word._isEoF():
                    break
            i.readEndOfFrame()
            PyBytecodeStreamSegmentLoopUnroll(i.interface)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        i = IoProxyAxi4StreamSegmented(hls, self.i)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, i)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SSPacketByteCntr_readByte(Axi4SSPacketByteCntr_readSegmentWord):

    #@override
    #def mainThread(self, hls: HlsScope, i: IoProxyAxi4StreamSegmented):
    #    byteTy = HBits(self.i.BYTE_WIDTH)
    #    byte_cnt = uint16_t.from_py(0)
    #    while b1:
    #        i.readStartOfFrame()
    #        while b1:
    #            word: HlsStmReadAxi4StreamSegmented = i.read(byteTy, reliable=False)
    #            byte_cnt += zextToTy(word.getSize(), byte_cnt._dtype)
    #            PyBytecodeStreamLoopUnroll(i.interface)
    #            if word._isEoF():
    #                break
    #        hls.write(byte_cnt, self.byte_cnt)
    #        i.readEndOfFrame()
    #        PyBytecodeStreamSegmentLoopUnroll(i.interface)
    #
    @override
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4StreamSegmented):
        byteTy = HBits(self.i.BYTE_WIDTH)
        byte_cnt = uint16_t.from_py(0)
        while b1:
            i.readStartOfFrame()
            while b1:
                word: HlsStmReadAxi4StreamSegmented = i.read(byteTy)
                byte_cnt += 1
                PyBytecodeStreamLoopUnroll(i.interface)
                if word._isEoF():
                    break
            hls.write(byte_cnt, self.byte_cnt)
            i.readEndOfFrame()
            PyBytecodeStreamSegmentLoopUnroll(i.interface)


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = Axi4SSPacketByteCntr_readBusWord()
    m.SEGMENT_DATA_WIDTH = 16
    m.SEGMENT_CNT = 2
    m.CLK_FREQ = int(100e6)
    print(to_rtl_str(m, target_platform=Artix7Medium(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED]
    )))

    # import unittest
    # testLoader = unittest.TestLoader()
    # # suite = unittest.TestSuite([Axi4SPingResponderTC("test_reply1x")])
    # suite = testLoader.loadTestsFromTestCase(Axi4SPingResponder_256_TC)
    # runner = unittest.TextTestRunner(verbosity=3)
    # runner.run(suite)
