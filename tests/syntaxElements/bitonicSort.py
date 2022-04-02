#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.constants import Time
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.logic.bitonicSorter import BitonicSorter, BitonicSorterTC


class BitonicSorterHLS(BitonicSorter):

    def _config(self):
        BitonicSorter._config(self)
        self.CLK_FREQ = Param(int(50e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        BitonicSorter._declr(self)
        self.clk.FREQ = self.CLK_FREQ

    def bitonic_compare(self, cmpFn, x, layer, offset):
        dist = len(x) // 2
        _x = [self.hls.var(f"sort_tmp_{layer:d}_{offset:d}_{i:d}", x[0]._dtype) for i, _ in enumerate(x)]
        for i in range(dist):
            self.hls_code.append(
                self.hls.If(cmpFn(x[i], x[i + dist]),
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

    def _impl(self):
        hls = HlsStreamProc(self)
        self.hls = hls
        self.hls_code = []
        outs = self.bitonic_sort(self.cmpFn,
                                 [hls.read(i) for i in self.inputs])
        hls.thread(
            hls.While(True,
                *self.hls_code,
                *(
                    hls.write(otmp, o)
                    for otmp, o in zip(outs, self.outputs)
                )
            ))
        hls.compile()


class BitonicSorterHLS_TC(BitonicSorterTC):

    @classmethod
    def setUpClass(cls):
        cls.u = BitonicSorterHLS()
        cls.compileSim(cls.u, target_platform=VirtualHlsPlatform())


class BitonicSorterHLS_large_TC(BitonicSorterTC):
    SIM_TIME = 200 * Time.ns

    @classmethod
    def setUpClass(cls):
        cls.u = BitonicSorterHLS()
        cls.u.ITEMS = 16
        cls.compileSim(cls.u, target_platform=VirtualHlsPlatform())


BitonicSorterHLS_TCs = [
    BitonicSorterHLS_TC,
    BitonicSorterHLS_large_TC
]

if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses

    u = BitonicSorterHLS()
    u.ITEMS = 8
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))

    suite = unittest.TestSuite()
    # suite.addTest(BitonicSorterHLS_large_TC('test_reversed'))
    for tc in BitonicSorterHLS_TCs:
        suite.addTest(unittest.makeSuite(tc))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
