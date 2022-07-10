#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.constants import Time
from hwt.hdl.types.bits import Bits
from hwt.interfaces.std import VectSignal
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from pyMathBitPrecise.bit_utils import mask
from tests.baseSsaTest import BaseSsaTC


class HlsConnection(Unit):

    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(hls.read(self.a), self.b)
            ),
            self._name)
        )
        hls.compile()



class HlsSlice(Unit):

    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(16, signed=False)._m()

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(hls.read(self.a)[16:], self.b)
            ),
            self._name)
        )
        hls.compile()



class HlsSlice2TmpHlsVarConcat(Unit):

    def _declr(self):
        self.a = VectSignal(16, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        tmp = hls.var("tmp", self.b._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                tmp(Concat(Bits(16).from_py(16), hls.read(self.a))),
                hls.write(tmp, self.b)
            ),
            self._name)
        )
        hls.compile()


# class HlsSlice2(HlsSlice2TmpHlsVarConcat):
#
#    def _impl(self):
#        hls = HlsScope(self, freq=int(100e6))
#        ast = HlsAstBuilder(hls)
#        hls.addThread(HlsThreadFromAst(hls,
#            ast.While(True,
#                hls.write(hls.read(self.a), self.b[16:]),
#                hls.write(16, self.b[:16]),
#            ),
#            self._name)
#        )


class HlsSlice2TmpHlsVarSlice(HlsSlice2TmpHlsVarConcat):

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        tmp = hls.var("tmp", self.b._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                tmp[:16](Bits(16).from_py(16)),
                tmp[16:](hls.read(self.a)),
                hls.write(tmp, self.b)
            ),
            self._name)
        )
        hls.compile()



class HlsSlicingTC(BaseSsaTC):
    __FILE__ = __file__

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

    suite = unittest.TestSuite()
    # suite.addTest(HlsSlicingTC('test_HlsSlice2TmpHlsVarSlice'))
    suite.addTest(unittest.makeSuite(HlsSlicingTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

    #from hwt.synthesizer.utils import to_rtl_str
    #u = HlsSlice2TmpHlsVarSlice()
    #print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
