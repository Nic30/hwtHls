#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.virtual import VirtualHlsPlatform
from pyMathBitPrecise.bit_utils import mask


class HlsConnection(Unit):

    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls.thread(
            hls.While(True,
                hls.write(hls.read(self.a), self.b)
            )
        )


class HlsSlice(Unit):

    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(16, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls.thread(
            hls.While(True,
                hls.write(hls.read(self.a)[16:], self.b)
            )
        )


class HlsSlice2(Unit):

    def _declr(self):
        self.a = VectSignal(16, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls.thread(
            hls.While(True,
                hls.write(hls.read(self.a), self.b[16:]),
                hls.write(16, self.b[:16]),
            )
        )



class HlsSlicingTC(SimTestCase):

    def _test(self, unit_cls, data_in, data_out):
        self.compileSimAndStart(unit_cls, target_platform=VirtualHlsPlatform())
        unit_cls.a._ag.data.extend(data_in)
        self.runSim(len(data_in) * 10 * Time.ns)
        self.assertValSequenceEqual(unit_cls.b._ag.data, data_out)

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
        u = cls()
        data_in = [0, 1, 2, 3]
        data_out = [d + (16 << 16) for d in data_in]
        self._test(u, data_in, data_out)

    def test_slice2(self):
        self._test_slice2(HlsSlice2)



if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(HlsSlicingTC('test_connection'))
    suite.addTest(unittest.makeSuite(HlsSlicingTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

    # from hwt.synthesizer.utils import to_rtl_str
    # u = HlsSlice2B()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform()) + "\n")
