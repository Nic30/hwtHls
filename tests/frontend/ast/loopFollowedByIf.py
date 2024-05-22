#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwParam import HwParam
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.ast.loopAfterLoop import TwoTimesFiniteWhileInWhileTrue


class FiniteWhileIf0(TwoTimesFiniteWhileInWhileTrue):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    def _declr(self) -> None:
        TwoTimesFiniteWhileInWhileTrue._declr(self)
        self.dataIn0: HwIOStructRdVld = HwIOStructRdVld()
        self.dataIn0.T = HBits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i0 = hls.var("i0", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i0(0),
                ast.While(i0 != 4,
                    hls.write(4, self.dataOut0),
                    i0(i0 + 1)
                ),
                ast.If(hls.read(self.dataIn0).data._eq(8),
                    hls.write(7, self.dataOut1),
                ),
            ],
            self._name)
        )
        hls.compile()


class FiniteWhileIf1(TwoTimesFiniteWhileInWhileTrue):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    def _declr(self) -> None:
        TwoTimesFiniteWhileInWhileTrue._declr(self)
        self.dataIn0: HwIOStructRdVld = HwIOStructRdVld()
        self.dataIn0.T = HBits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i0 = hls.var("i0", uint8_t)
        din0 = hls.read(self.dataIn0).data
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i0(0),
                ast.While(i0 != 4,
                    hls.write(4, self.dataOut0),
                    i0(i0 + 1)
                ),
                ast.If(din0._eq(8),
                    hls.write(7, self.dataOut1),
                ).Elif(din0._eq(7),
                    hls.write(6, self.dataOut1),
                ),
            ],
            self._name)
        )
        hls.compile()


class LoopFollowedByIf_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_FiniteWhileIf0(self):
        dut = FiniteWhileIf0()
        dut.FREQ = int(50e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        dut.dataIn0._ag.data.append(8)
        self.runSim(int(10 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [7, ])

    def test_FiniteWhileIf1(self):
        dut = FiniteWhileIf1()
        dut.FREQ = int(50e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        
        dut.dataIn0._ag.data.append(8)
        self.runSim(int(10 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [7, ])


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = FiniteWhileIf1()
    m.FREQ = int(50e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LoopFollowedByIf_TC('test_FiniteWhileIf0')])
    suite = testLoader.loadTestsFromTestCase(LoopFollowedByIf_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)