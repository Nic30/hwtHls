#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform
from pyMathBitPrecise.bit_utils import mask


class HlsConnection(Unit):

    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.io(self.a)
            hls.io(self.b)(a)


class HlsSlice(Unit):

    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(16, signed=False)._m()

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.io(self.a)
            hls.io(self.b)(a[16:])


class HlsSlice2(Unit):

    def _declr(self):
        self.a = VectSignal(16, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.io(self.a)
            hls.io(self.b[16:])(a)
            hls.io(self.b[:16])(16)


class HlsSlice2B(HlsSlice2):

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.io(self.a)
            hls.io(self.b)[16:](a)
            hls.io(self.b)[:16](16)


class HlsSlice2C(HlsSlice2):

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.io(self.a)
            b = hls.io(self.b)
            b[16:](a)
            b[:16](16)


class HlsSlicingTC(SimTestCase):

    def _test(self, unit, data_in, data_out):
        self.compileSimAndStart(unit, target_platform=VirtualHlsPlatform())
        unit.a._ag.data.extend(data_in)
        self.runSim(len(data_in) * 10 * Time.ns)
        self.assertValSequenceEqual(unit.b._ag.data, data_out)

    def test_connection(self):
        u = HlsConnection()
        data = [0, 1, 2, 3, 1 << 16]
        self._test(u, data, data)

    def _test_slice(self, cls):
        u = cls()
        data_in = [0, 1, 2, 3, 1 << 16, 768 << 20]
        data_out = [d & mask(16) for d in data_in]
        self._test(u, data_in, data_out)

    def test_slice(self):
        self._test_slice(HlsSlice)

    def _test_slice2(self, cls):
        u = HlsSlice2()
        data_in = [0, 1, 2, 3]
        data_out = [d + (16 << 16) for d in data_in]
        self._test(u, data_in, data_out)

    def test_slice2(self):
        self._test_slice2(HlsSlice2)

    def test_slice2B(self):
        self._test_slice2(HlsSlice2B)

    def test_slice2C(self):
        self._test_slice2(HlsSlice2C)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str

    #suite = unittest.TestSuite()
    ## suite.addTest(FrameTmplTC('test_frameHeader'))
    #suite.addTest(unittest.makeSuite(HlsSlicingTC))
    #runner = unittest.TextTestRunner(verbosity=3)
    #runner.run(suite)

    u = HlsSlice()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()) + "\n")
