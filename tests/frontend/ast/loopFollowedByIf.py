#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.ast.exprTree3 import HlsAstExprTree3_example
from tests.frontend.ast.loopAfterLoop import TwoTimesFiniteWhileInWhileTrue


class FiniteWhileIf0(TwoTimesFiniteWhileInWhileTrue):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self) -> None:
        TwoTimesFiniteWhileInWhileTrue.hwDeclr(self)
        self.dataIn0: HwIOStructRdVld = HwIOStructRdVld()
        self.dataIn0.T = HBits(self.DATA_WIDTH, signed=False)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i0 = uint8_t.from_py(0)
        while i0 != 4:
            hls.write(4, self.dataOut0)
            i0 = i0 + 1

        if hls.read(self.dataIn0).data._eq(8):
            hls.write(7, self.dataOut1)

    @override
    def hwImpl(self) -> None:
        HlsAstExprTree3_example.hwImpl(self)


class FiniteWhileIf1(TwoTimesFiniteWhileInWhileTrue):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self) -> None:
        TwoTimesFiniteWhileInWhileTrue.hwDeclr(self)
        self.dataIn0: HwIOStructRdVld = HwIOStructRdVld()
        self.dataIn0.T = HBits(self.DATA_WIDTH, signed=False)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i0 = uint8_t.from_py(0)
        while i0 != 4:
            hls.write(4, self.dataOut0)
            i0 = i0 + 1
        din0 = hls.read(self.dataIn0).data
        if din0._eq(8):
            hls.write(7, self.dataOut1)
        elif din0._eq(7):
            hls.write(6, self.dataOut1)


class LoopFollowedByIf_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_FiniteWhileIf0(self):
        dut = FiniteWhileIf0()
        dut.FREQ = int(50e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            # debugFilter={
            #    *HlsDebugBundle.ALL_RELIABLE,
            #    HlsDebugBundle.DBG_20_addSignalNamesToSync,
            #    #HlsDebugBundle.DBG_20_addSignalNamesToData
            # }
            ))

        dut.dataIn0._ag.data.append(8)
        self.runSim(int(10 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [7, ])

    def test_FiniteWhileIf1(self):
        dut = FiniteWhileIf1()
        dut.FREQ = int(40e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        dut.dataIn0._ag.data.append(8)
        self.runSim(int(10 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [7, ])


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = FiniteWhileIf1()
    m.FREQ = int(40e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={
        *HlsDebugBundle.ALL_RELIABLE,
        HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
        # HlsDebugBundle.DBG_20_addSignalNamesToData
    })))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LoopFollowedByIf_TC('test_FiniteWhileIf0')])
    suite = testLoader.loadTestsFromTestCase(LoopFollowedByIf_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
