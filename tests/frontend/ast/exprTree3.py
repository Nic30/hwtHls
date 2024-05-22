#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.baseSsaTest import BaseSsaTC


class HlsAstExprTree3_example(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(40e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.a = HwIOVectSignal(32, signed=False)
        self.b = HwIOVectSignal(32, signed=False)
        self.c = HwIOVectSignal(32, signed=False)
        self.d = HwIOVectSignal(32, signed=False)

        self.x = HwIOVectSignal(32, signed=False)
        self.y = HwIOVectSignal(32, signed=False)
        self.z = HwIOVectSignal(32, signed=False)
        self.w = HwIOVectSignal(32, signed=False)

        self.f1 = HwIOVectSignal(32, signed=False)._m()
        self.f2 = HwIOVectSignal(32, signed=False)._m()
        self.f3 = HwIOVectSignal(32, signed=False)._m()

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        r = hls.read
        _a, _b, _c, _d = r(self.a), r(self.b), r(self.c), r(self.d)
        # x, y, z, w are happending after f1 was written
        x, y, z, w = r(self.x).data, r(self.y).data, r(self.z).data, r(self.w).data
        a, b, c, d = _a.data, _b.data, _c.data, _d.data
        f1 = (a + b + c) * d
        xy = x + y
        f2 = xy * z
        f3 = xy * w

        wr = hls.write
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                _a, _b, _c, _d,
                wr(f1, self.f1),
                wr(f2, self.f2),
                wr(f3, self.f3),
            ),
            self._name)
        )
        hls.compile()



class HlsAstExprTree3_example_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_ll(self):
        self._test_ll(HlsAstExprTree3_example)

    def test_simple(self):
        dut = HlsAstExprTree3_example()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.a._ag.data.append(3)
        dut.b._ag.data.append(4)
        dut.c._ag.data.append(5)
        dut.d._ag.data.append(6)
        dut.x._ag.data.append(7)
        dut.y._ag.data.append(8)
        dut.z._ag.data.append(9)
        dut.w._ag.data.append(10)

        self.runSim(int(7 * freq_to_period(dut.CLK_FREQ)))

        self.assertValEqual(dut.f1._ag.data[-1], (3 + 4 + 5) * 6)
        self.assertValEqual(dut.f2._ag.data[-1], (7 + 8) * 9)
        self.assertValEqual(dut.f3._ag.data[-1], (7 + 8) * 10)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = HlsAstExprTree3_example()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsAstExprTree3_example_TC("test_simple")])
    suite = testLoader.loadTestsFromTestCase(HlsAstExprTree3_example_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
