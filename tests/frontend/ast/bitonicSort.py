#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.constants import Time
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.logic.bitonicSorter import BitonicSorter, BitonicSorterTC
from hwt.pyUtils.typingFuture import override


class BitonicSorterHLS(BitonicSorter):

    @override
    def hwConfig(self):
        BitonicSorter.hwConfig(self)
        self.CLK_FREQ = HwParam(int(50e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        BitonicSorter.hwDeclr(self)
        self.clk.FREQ = self.CLK_FREQ

    def bitonic_compare(self, cmpFn, x, layer, offset):
        dist = len(x) // 2
        _x = [self.hls.var(f"sort_tmp_{layer:d}_{offset:d}_{i:d}", x[0]._dtype) for i, _ in enumerate(x)]
        for i in range(dist):
            self.hls_code.append(
                 self.astBuilder.If(cmpFn(x[i], x[i + dist]),
                    # keep
                    _x[i](x[i]),
                    _x[i + dist](x[i + dist])
                ).Else(
                    # swap
                    _x[i](x[i + dist]),
                    _x[i + dist](x[i]),
                )
            )
        return _x

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        self.hls = hls
        self.astBuilder = HlsAstBuilder(self.hls)
        self.hls_code = []
        outs = self.bitonic_sort(self.cmpFn,
                                 [hls.read(i).data for i in self.inputs])
        hls.addThread(HlsThreadFromAst(hls,
            self.astBuilder.While(True,
                *self.hls_code,
                *(
                    hls.write(otmp, o)
                    for otmp, o in zip(outs, self.outputs)
                )
            ),
            self._name)
        )
        hls.compile()


class BitonicSorterHLS_TC(BitonicSorterTC):

    @classmethod
    @override
    def setUpClass(cls):
        cls.dut = BitonicSorterHLS()
        cls.compileSim(cls.dut, target_platform=VirtualHlsPlatform())


class BitonicSorterHLS_large_TC(BitonicSorterTC):
    SIM_TIME = 220 * Time.ns

    @classmethod
    @override
    def setUpClass(cls):
        cls.dut = BitonicSorterHLS()
        cls.dut.ITEMS = 16
        cls.compileSim(cls.dut, target_platform=VirtualHlsPlatform())


BitonicSorterHLS_TCs = [
    BitonicSorterHLS_TC,
    BitonicSorterHLS_large_TC
]

if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = BitonicSorterHLS()
    m.ITEMS = 4
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BitonicSorterHLS_large_TC('test_reversed')])
    suite = unittest.TestSuite(testLoader.loadTestsFromTestCase(tc)
                               for tc in BitonicSorterHLS_TCs)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
