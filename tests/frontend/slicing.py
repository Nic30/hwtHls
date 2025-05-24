#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.constants import Time
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from pyMathBitPrecise.bit_utils import mask
from tests.baseSsaTest import BaseSsaTC


# [todo] duplication with WhileTrueReadWrite
class HlsConnection(HwModule):

    @override
    def hwDeclr(self):
        self.a = HwIOVectSignal(32, signed=False)
        self.b = HwIOVectSignal(32, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            hls.write(hls.read(self.a).data, self.b)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, freq=int(100e6), namePrefix="")
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class HlsSlice(HwModule):

    @override
    def hwDeclr(self):
        self.a = HwIOVectSignal(32, signed=False)
        self.b = HwIOVectSignal(16, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            hls.write(hls.read(self.a).data[16:], self.b)

    @override
    def hwImpl(self):
        HlsConnection.hwImpl(self)


class HlsSlice2TmpHlsVarConcat(HwModule):

    @override
    def hwDeclr(self):
        self.a = HwIOVectSignal(16, signed=False)
        self.b = HwIOVectSignal(32, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            tmp = Concat(HBits(16).from_py(16), hls.read(self.a).data)
            hls.write(tmp, self.b)

    @override
    def hwImpl(self):
        HlsConnection.hwImpl(self)


class HlsSlice2(HlsSlice2TmpHlsVarConcat):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            hls.write(hls.read(self.a).data, self.b[16:])
            hls.write(16, self.b[:16])


class HlsSlice2TmpHlsVarSlice(HlsSlice2TmpHlsVarConcat):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            tmp = self.b._dtype.from_py(None)
            tmp[:16] = HBits(16).from_py(16)
            tmp[16:] = hls.read(self.a).data
            hls.write(tmp, self.b)


class HlsSlicingTC(BaseSsaTC):
    __FILE__ = __file__
    TEST_BLOCK_SYNC = False

    def _test(self, unit_constructor, data_in, data_out):
        self._test_ll(unit_constructor)

        unit = unit_constructor()
        self.compileSimAndStart(unit, target_platform=VirtualHlsPlatform())
        unit.a._ag.data.extend(data_in)
        self.runSim(len(data_in) * 10 * Time.ns)
        self.assertValSequenceEqual(unit.b._ag.data, data_out)

    def test_connection(self):
        data = [0, 1, 2, 3, 1 << 16]
        self._test(HlsConnection, data, data)

    def _test_slice(self, cls):
        data_in = [0, 1, 2, 3, 1 << 16, 768 << 20]
        data_out = [d & mask(16) for d in data_in]
        self._test(cls, data_in, data_out)

    def test_slice(self):
        self._test_slice(HlsSlice)

    def _test_slice2(self, cls):
        data_in = [0, 1, 2, 3]
        data_out = [d + (16 << 16) for d in data_in]
        self._test(cls, data_in, data_out)

    # def test_slice2(self):
    #    self._test_slice2(HlsSlice2)

    def test_HlsSlice2TmpHlsVarConcat(self):
        self._test_slice2(HlsSlice2TmpHlsVarConcat)

    def test_HlsSlice2TmpHlsVarSlice(self):
        self._test_slice2(HlsSlice2TmpHlsVarSlice)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsSlicingTC('test_HlsSlice2TmpHlsVarSlice')])
    suite = testLoader.loadTestsFromTestCase(HlsSlicingTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

    #from hwt.synth import to_rtl_str
    #from hwtHls.platform.debugBundle import HlsDebugBundle
    #m = HlsSlice2TmpHlsVarSlice()
    #print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
