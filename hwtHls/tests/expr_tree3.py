#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.virtual import VirtualHlsPlatform


class HlsExprTree3_example(Unit):

    def _config(self):
        self.CLK_FREQ = Param(int(50e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)
        self.c = VectSignal(32, signed=False)
        self.d = VectSignal(32, signed=False)

        self.x = VectSignal(32, signed=False)
        self.y = VectSignal(32, signed=False)
        self.z = VectSignal(32, signed=False)
        self.w = VectSignal(32, signed=False)

        self.f1 = VectSignal(32, signed=False)._m()
        self.f2 = VectSignal(32, signed=False)._m()
        self.f3 = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self)
        a, b, c, d = self.a, self.b, self.c, self.d
        x, y, z, w = self.x, self.y, self.z, self.w

        r = hls.read
        f1 = (r(a) + r(b) + r(c)) * r(d)
        xy = r(x) + r(y)
        f2 = xy * r(z)
        f3 = xy * r(w)

        wr = hls.write
        hls.thread(
            hls.While(True,
                wr(f1, self.f1),
                wr(f2, self.f2),
                wr(f3, self.f3),
            )
        )


class HlsExprTree3_example_TC(SimTestCase):

    def test_simple(self):
        u = HlsExprTree3_example()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.a._ag.data.append(3)
        u.b._ag.data.append(4)
        u.c._ag.data.append(5)
        u.d._ag.data.append(6)
        u.x._ag.data.append(7)
        u.y._ag.data.append(8)
        u.z._ag.data.append(9)
        u.w._ag.data.append(10)

        self.runSim(40 * Time.ns)

        self.assertValEqual(u.f1._ag.data[-1], (3 + 4 + 5) * 6)
        self.assertValEqual(u.f2._ag.data[-1], (7 + 8) * 9)
        self.assertValEqual(u.f3._ag.data[-1], (7 + 8) * 10)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    u = HlsExprTree3_example()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsExprTree3_example_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
