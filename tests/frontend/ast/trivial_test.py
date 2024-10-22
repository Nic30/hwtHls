#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.constants import CLK_PERIOD
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.frontend.ast.trivial import WriteOnce, ReadWriteOnce0, ReadWriteOnce1, WhileTrueWrite, \
    WhileTrueReadWrite, ReadWriteOnce2, WhileTrueReadWriteExpr


class HlsAstTrivial_TC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def test_WriteOnce(self):
        dut = WriteOnce()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK = 4
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.dataOut._ag.data, [1, ])

    def test_ReadWriteOnce0(self, cls=ReadWriteOnce0):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK = 4
        for i in range(CLK):
            dut.dataIn._ag.data.append(i)

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertSequenceEqual(dut.dataIn._ag.data, [2, 3])
        self.assertValSequenceEqual(dut.dataOut._ag.data, [0, ])

    def test_ReadWriteOnce1(self):
        self.test_ReadWriteOnce0(ReadWriteOnce1)

    def test_ReadWriteOnce2(self, cls=ReadWriteOnce2):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK = 4
        for i in range(CLK):
            dut.dataIn._ag.data.append(i)

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertSequenceEqual(dut.dataIn._ag.data, [2, 3])
        self.assertValSequenceEqual(dut.dataOut._ag.data, [1, ])

    def test_WhileTrueWrite(self):
        dut = WhileTrueWrite()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK = 4
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.dataOut._ag.data, [10 for _ in range(CLK - 1) ])

    def test_WhileTrueReadWrite(self, cls=WhileTrueReadWrite, model=lambda x: x, CLK=4):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        for i in range(CLK):
            dut.dataIn._ag.data.append(i)

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.dataOut._ag.data,
                                    [model(i) for i in range(CLK - 1)])

    def test_WhileTrueReadWriteExpr(self):
        self.test_WhileTrueReadWrite(cls=WhileTrueReadWriteExpr, model=lambda x: int((uint8_t.from_py(x) * 8 + 2) * 3))


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = ReadWriteOnce0()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsAstTrivial_TC("test_ReadWriteOnce0")])
    suite = testLoader.loadTestsFromTestCase(HlsAstTrivial_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
