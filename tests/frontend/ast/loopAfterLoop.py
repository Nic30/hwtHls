#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC


class TwoTimesFiniteWhileInWhileTrue(HwModule):

    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(50e6))

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataOut0: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut0.T = HBits(self.DATA_WIDTH, signed=False)
        self.dataOut1: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut1.T = HBits(self.DATA_WIDTH, signed=False)

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        i0, i1 = (hls.var(f"i{i}", uint8_t) for i in range(2))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                ast.While(True,
                    i0(0),
                    ast.While(i0 != 4,
                        hls.write(4, self.dataOut0),
                        i0(i0 + 1)
                    ),
                    i1(0),
                    ast.While(i1 != 5,
                        hls.write(5, self.dataOut1),
                        i1(i1 + 1)
                    ),
                )
            ],
            self._name)
        )
        hls.compile()


class WriteAfterFiniteWhileInWhileTrue(TwoTimesFiniteWhileInWhileTrue):

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        i0 = hls.var("i0", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                ast.While(True,
                    i0(0),
                    ast.While(i0 != 4,
                        hls.write(4, self.dataOut0),
                        i0(i0 + 1)
                    ),
                    hls.write(5, self.dataOut1),
                )
            ],
            self._name)
        )
        hls.compile()

class WriteBeforeFiniteWhileInWhileTrue(TwoTimesFiniteWhileInWhileTrue):

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        i0 = hls.var("i0", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                ast.While(True,
                    hls.write(5, self.dataOut1),
                    i0(0),
                    ast.While(i0 != 4,
                        hls.write(4, self.dataOut0),
                        i0(i0 + 1)
                    ),
                )
            ],
            self._name)
        )
        hls.compile()

class TwoTimesFiniteWhile(TwoTimesFiniteWhileInWhileTrue):

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        i0, i1 = (hls.var(f"i{i}", uint8_t) for i in range(2))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i0(0),
                ast.While(i0 != 4,
                    hls.write(4, self.dataOut0),
                    i0(i0 + 1)
                ),
                i1(0),
                ast.While(i1 != 5,
                    hls.write(5, self.dataOut1),
                    i1(i1 + 1)
                ),
            ],
            self._name)
        )
        hls.compile()


class LoopAfterLoop_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_TwoTimesFiniteWhileInWhileTrue(self):

        from hwtHls.platform.platform import HlsDebugBundle
        dut = TwoTimesFiniteWhileInWhileTrue()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            debugFilter={
                *HlsDebugBundle.ALL_RELIABLE,
                HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
            }
            ))
        self.runSim(int(10 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5 for _ in range(5)])

    def test_TwoTimesFiniteWhile(self):
        dut = TwoTimesFiniteWhile()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(

            ))
        self.runSim(int(10 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5 for _ in range(5)])

    def test_WriteAfterFiniteWhileInWhileTrue(self):
        dut = WriteAfterFiniteWhileInWhileTrue()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            ))
        self.runSim(int(6 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(4)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5])

    def test_WriteBeforeFiniteWhileInWhileTrue(self):
        dut = WriteBeforeFiniteWhileInWhileTrue()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            ))
        self.runSim(int(10 * freq_to_period(dut.FREQ)))

        self.assertValSequenceEqual(dut.dataOut0._ag.data, [4 for _ in range(8)])
        self.assertValSequenceEqual(dut.dataOut1._ag.data, [5, 5, 5])


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = TwoTimesFiniteWhile()
    #m.FREQ = int(150e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter={
        *HlsDebugBundle.ALL_RELIABLE,
        HlsDebugBundle.DBG_4_0_addSignalNamesToData,
        HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
    })))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([LoopAfterLoop_TC('test_TwoTimesFiniteWhileInWhileTrue')])
    suite = testLoader.loadTestsFromTestCase(LoopAfterLoop_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
