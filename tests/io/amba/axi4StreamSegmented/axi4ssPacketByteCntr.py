#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.code import zextToTy
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4StreamSegmented
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4StreamSegmented
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.types.ctypes import uint16_t


class Axi4SSPacketByteCntr_readWord(HwModule):
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

    def mainThread(self, hls: HlsScope, i: IoProxyAxi4StreamSegmented):
        byte_cnt = uint16_t.from_py(0)
        i.readStartOfFrame()
        wordTy = HBits(self.SEGMENT_DATA_WIDTH)
        while b1:
            # end of frame is ignored
            word = i.read(wordTy, reliable=False)
            byte_cnt += zextToTy(word.getSize(), byte_cnt._dtype)
            hls.write(byte_cnt, self.byte_cnt)

        i.readEndOfFrame()

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        i = IoProxyAxi4StreamSegmented(hls, self.i)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, i)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SSPacketByteCntr_readByte(Axi4SSPacketByteCntr_readWord):
    """
    Counts a total number of bytes in any word seen.
    """

    @override
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4StreamSegmented):
        byte_cnt = uint16_t.from_py(0)
        i.readStartOfFrame()
        wordTy = HBits(self.SEGMENT_DATA_WIDTH)
        while b1:
            # end of frame is ignored
            word: HlsStmReadAxi4StreamSegmented = i.read(wordTy)
            byte_cnt += zextToTy(word.getSize(), byte_cnt._dtype)
            hls.write(byte_cnt, self.byte_cnt)

        i.readEndOfFrame()


if __name__ == "__main__":
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = Axi4SSPacketByteCntr_readByte()
    m.SEGMENT_DATA_WIDTH = 24
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
