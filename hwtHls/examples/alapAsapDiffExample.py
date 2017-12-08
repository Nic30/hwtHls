#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import toRtl
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


class AlapAsapDiffExample(Unit):
    def _config(self):
        self.CLK_FREQ = int(3e9)

    def _declr(self):
        addClkRstn(self)
        self.a = VectSignal(8)
        self.b = VectSignal(8)
        self.c = VectSignal(8)
        self.d = VectSignal(8)

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as hls:
            # inputs has to be readed to enter hls scope
            # (without read() operation will not be schedueled by HLS
            #  but they will be directly synthesized)
            a, b, c = [hls.read(intf)
                       for intf in [self.a, self.b, self.c]]
            # depending on target platform this expresion
            # can be mapped to DPS, LUT, etc...
            # no constrains are specified => default strategy is
            # to achieve zero delay and minimum latency, for this CLK_FREQ
            d = ~(~a & ~b) & ~c

            hls.write(d, self.d)


if __name__ == "__main__":
    import unittest
    u = AlapAsapDiffExample()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))

    #suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    # suite.addTest(unittest.makeSuite(HlsMAC_example_TC))
    #runner = unittest.TextTestRunner(verbosity=3)
    # runner.run(suite)
