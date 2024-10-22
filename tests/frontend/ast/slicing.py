#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.constants import Time
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from pyMathBitPrecise.bit_utils import mask
from tests.baseSsaTest import BaseSsaTC


class HlsConnection(HwModule):

    @override
    def hwDeclr(self):
        self.a = HwIOVectSignal(32, signed=False)
        self.b = HwIOVectSignal(32, signed=False)._m()

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(hls.read(self.a).data, self.b)
            ),
            self._name)
        )
        hls.compile()



class HlsSlice(HwModule):

    @override
    def hwDeclr(self):
        self.a = HwIOVectSignal(32, signed=False)
        self.b = HwIOVectSignal(16, signed=False)._m()

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(hls.read(self.a).data[16:], self.b)
            ),
            self._name)
        )
        hls.compile()



class HlsSlice2TmpHlsVarConcat(HwModule):

    @override
    def hwDeclr(self):
        self.a = HwIOVectSignal(16, signed=False)
        self.b = HwIOVectSignal(32, signed=False)._m()

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        tmp = hls.var("tmp", self.b._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                tmp(Concat(HBits(16).from_py(16), hls.read(self.a).data)),
                hls.write(tmp, self.b)
            ),
            self._name)
        )
        hls.compile()


# class HlsSlice2(HlsSlice2TmpHlsVarConcat):
#
#    @override
#    def hwImpl(self):
#        hls = HlsScope(self, freq=int(100e6))
#        ast = HlsAstBuilder(hls)
#        hls.addThread(HlsThreadFromAst(hls,
#            ast.While(True,
#                hls.write(hls.read(self.a).data, self.b[16:]),
#                hls.write(16, self.b[:16]),
#            ),
#            self._name)
#        )


class HlsSlice2TmpHlsVarSlice(HlsSlice2TmpHlsVarConcat):

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        tmp = hls.var("tmp", self.b._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                tmp[:16](HBits(16).from_py(16)),
                tmp[16:](hls.read(self.a).data),
                hls.write(tmp, self.b)
            ),
            self._name)
        )
        hls.compile()



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

    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # m = HlsSlice()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
