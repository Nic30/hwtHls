#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.trivial import WriteOnce


class TwoTimesFiniteWhileInWhileTrue(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(50e6))

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.dataOut0: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut0.T = HBits(self.DATA_WIDTH, signed=False)
        self.dataOut1: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut1.T = HBits(self.DATA_WIDTH, signed=False)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i0, i1 = (hls.var(f"i{i}", uint8_t) for i in range(2))
        while b1:
            i0 = 0
            while i0 != 4:
                hls.write(4, self.dataOut0)
                i0 = i0 + 1

            i1 = 0
            while i1 != 5:
                hls.write(5, self.dataOut1)
                i1 = i1 + 1

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class WriteAfterFiniteWhileInWhileTrue(TwoTimesFiniteWhileInWhileTrue):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i0 = hls.var("i0", uint8_t)
        while b1:
            i0 = 0
            while i0 != 4:
                hls.write(4, self.dataOut0)
                i0 = i0 + 1
            hls.write(5, self.dataOut1)


class WriteBeforeFiniteWhileInWhileTrue(TwoTimesFiniteWhileInWhileTrue):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i0 = hls.var("i0", uint8_t)
        while b1:
            hls.write(5, self.dataOut1)
            i0 = 0
            while i0 != 4:
                hls.write(4, self.dataOut0)
                i0 = i0 + 1


class TwoTimesFiniteWhile(TwoTimesFiniteWhileInWhileTrue):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i0, i1 = (hls.var(f"i{i}", uint8_t) for i in range(2))

        i0 = 0
        while i0 != 4:
            hls.write(4, self.dataOut0)
            i0 = i0 + 1

        i1 = 0
        while i1 != 5:
            hls.write(5, self.dataOut1)
            i1 = i1 + 1


class LoopAfterLoop_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_TwoTimesFiniteWhileInWhileTrue(self):

        from hwtHls.platform.debugBundle import HlsDebugBundle
        dut = TwoTimesFiniteWhileInWhileTrue()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            # debugFilter={
            #     *HlsDebugBundle.ALL_RELIABLE,
            #     HlsDebugBundle.DBG_4_0_addSignalNamesToData,
            #     HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
            # }
            ))
        self.runSim(int(9 * freq_to_period(dut.CLK_FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5 for _ in range(5)])

    def test_TwoTimesFiniteWhile(self):
        dut = TwoTimesFiniteWhile()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(

            ))
        self.runSim(int(10 * freq_to_period(dut.CLK_FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5 for _ in range(5)])

    def test_WriteAfterFiniteWhileInWhileTrue(self):
        dut = WriteAfterFiniteWhileInWhileTrue()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            ))
        self.runSim(int(5 * freq_to_period(dut.CLK_FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5])

    def test_WriteBeforeFiniteWhileInWhileTrue(self):
        dut = WriteBeforeFiniteWhileInWhileTrue()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            ))
        self.runSim(int(9 * freq_to_period(dut.CLK_FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(8)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5, 5, 5])


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # 
    # m = TwoTimesFiniteWhile()
    # # m.CLK_FREQ = int(150e6)
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
    #     # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED],
    #     debugFilter={
    #         *HlsDebugBundle.ALL_RELIABLE,
    #         HlsDebugBundle.DBG_4_0_addSignalNamesToData,
    #         HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
    #         })
    #     ))
    # 
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LoopAfterLoop_TC('test_TwoTimesFiniteWhileInWhileTrue')])
    suite = testLoader.loadTestsFromTestCase(LoopAfterLoop_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
