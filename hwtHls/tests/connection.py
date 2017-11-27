#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.bitmask import mask
from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


class HlsConnection(Unit):
    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.read(self.a)
            hls.write(a, self.b)


class HlsSlice(Unit):
    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(16, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.read(self.a)
            hls.write(a[16:], self.b)


class HlsSlice2(Unit):
    def _declr(self):
        self.a = VectSignal(16, signed=False)
        self.b = VectSignal(32, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.read(self.a)
            hls.write(a, self.b[16:])
            hls.write(16, self.b[:16])


class HlsSlicingTC(SimTestCase):
    def _test(self, unit, data_in, data_out):
        self.prepareUnit(unit, targetPlatform=VirtualHlsPlatform())
        unit.a._ag.data.extend(data_in)
        self.doSim(len(data_in) * 10 * Time.ns)
        self.assertValSequenceEqual(unit.b._ag.data, data_out)

    def test_connection(self):
        u = HlsConnection()
        data = [0, 1, 2, 3, 1 << 16]
        self._test(u, data, data)

    def test_slice(self):
        u = HlsSlice()
        data_in = [0, 1, 2, 3, 1 << 16, 768 << 20]
        data_out = [d & mask(16) for d in data_in]
        self._test(u, data_in, data_out)

    def test_slice2(self):
        u = HlsSlice2()
        data_in = [0, 1, 2, 3]
        data_out = [d + (16 << 16) for d in data_in]
        self._test(u, data_in, data_out)


if __name__ == "__main__":
    import unittest

    from hwt.synthesizer.utils import toRtl

    u = HlsConnection()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()) + "\n")

    u = HlsSlice()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))

    u = HlsSlice2()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()) + "\n")

    suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsSlicingTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
