#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from _functools import reduce

from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.pyUtils.arrayQuery import grouper, balanced_reduce
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import toRtl
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


class HlsMAC_example(Unit):
    def _config(self):
        self.CLK_FREQ = Param(int(25e6))
        self.INPUT_CNT = Param(4)

    def _declr(self):
        addClkRstn(self)
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn = [VectSignal(32, signed=False)
                       for _ in range(int(self.INPUT_CNT))]
        self._registerArray("dataIn", self.dataIn)

        self.dataOut = VectSignal(64, signed=False)

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as hls:
            # inputs has to be readed to enter hls scope
            # (without read() operation will not be schedueled by HLS
            #  instead they will be directly synthesized)
            # [NOTE] number of input is hardcoded by this
            a, b, c, d = [hls.read(intf)
                          for intf in self.dataIn]
            # depending on target platform this expresion
            # can be mapped to DPS, LUT, etc...
            # no constrains are specified => default strategy is
            # to achieve zero delay and minimum latency, for this CLK_FREQ
            e = a * b + c * d

            hls.write(e, self.dataOut)


class HlsMAC_example2(HlsMAC_example):
    def _config(self):
        super(HlsMAC_example2, self)._config()
        self.INPUT_CNT.set(16)

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as hls:
            # inputs has to be readed to enter hls scope
            # (without read() operation will not be schedueled by HLS
            #  instead they will be directly synthesized)
            # [NOTE] number of input is hardcoded by this
            dataIn = [hls.read(intf) for intf in self.dataIn]
            # depending on target platform this expresion
            # can be mapped to DPS, LUT, etc...
            # no constrains are specified => default strategy is
            # to achieve zero delay and minimum latency, for this CLK_FREQ
            muls = []
            for a, b in grouper(2, dataIn):
                muls.append(a * b)

            adds = balanced_reduce(muls, lambda a, b: a + b)
            hls.write(adds, self.dataOut)


class HlsMAC_example_TC(SimTestCase):
    def test_simple(self):
        u = HlsMAC_example()
        self.prepareUnit(u, targetPlatform=VirtualHlsPlatform())
        for intf, d in zip(u.dataIn, [3, 4, 5, 6]):
            intf._ag.data.append(d)

        self.doSim(40 * Time.ns)

        self.assertValEqual(u.dataOut._ag.data[-1],
                            (3 * 4) + (5 * 6))

    def test_2simple(self):
        u = HlsMAC_example2()
        u.INPUT_CNT.set(4)
        self.prepareUnit(u, targetPlatform=VirtualHlsPlatform())
        for intf, d in zip(u.dataIn, [3, 4, 5, 6]):
            intf._ag.data.append(d)

        self.doSim(40 * Time.ns)

        self.assertValEqual(u.dataOut._ag.data[-1],
                            (3 * 4) + (5 * 6))

    def test_2_16simple(self):
        u = HlsMAC_example2()
        u.INPUT_CNT.set(16)
        self.prepareUnit(u, targetPlatform=VirtualHlsPlatform())

        inputs = [i for i in range(16)]
        for intf, d in zip(u.dataIn, inputs):
            intf._ag.data.append(d)

        self.doSim(80 * Time.ns)

        res = u.dataOut._ag.data[-1]
        expectedRes = reduce(lambda a, b: a + b,
                             map(lambda x: x[0] * x[1],
                                 grouper(2,
                                         inputs)))
        self.assertValEqual(res, expectedRes)


if __name__ == "__main__":
    import unittest
    u = HlsMAC_example()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsMAC_example_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
