#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import toRtl
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


class HlsMAC_example(Unit):
    def _config(self):
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)
        self.c = VectSignal(32, signed=False)
        self.d = VectSignal(32, signed=False)
        self.e = VectSignal(64, signed=False)

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as hls:
            # inputs has to be readed to enter hls scope
            # (without read() operation will not be schedueled by HLS
            #  but they will be directly synthesized)
            a, b, c, d = [hls.read(intf)
                          for intf in [self.a, self.b, self.c, self.d]]
            # depending on target platform this expresion
            # can be mapped to DPS, LUT, etc...
            # no constrains are specified => default strategy is
            # to achieve zero delay and minimum latency, for this CLK_FREQ
            e = a * b + c * d

            hls.write(e, self.e)


class HlsMAC_example_TC(SimTestCase):
    def test_simple(self):
        u = HlsMAC_example()
        self.prepareUnit(u, targetPlatform=VirtualHlsPlatform())
        u.a._ag.data.append(3)
        u.b._ag.data.append(4)
        u.c._ag.data.append(5)
        u.d._ag.data.append(6)

        self.doSim(40 * Time.ns)

        self.assertValEqual(u.e._ag.data[-1], (3 * 4) + (5 * 6))


if __name__ == "__main__":
    import unittest
    u = HlsMAC_example()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsMAC_example_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
