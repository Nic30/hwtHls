#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.constants import Time
from hwt.interfaces.utils import addClkRstn
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.logic.bitonicSorter import BitonicSorter, BitonicSorterTC
from hwt.synthesizer.param import Param


class BitonicSorterHLS(BitonicSorter):

    def _config(self):
        BitonicSorter._config(self)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        BitonicSorter._declr(self)
        self.clk.FREQ = self.CLK_FREQ

    def _impl(self):
        with HlsPipeline(self, self.CLK_FREQ) as hls:
            outs = self.bitonic_sort(self.cmpFn,
                                     [hls.io(i) for i in self.inputs])
            for o, otmp in zip(self.outputs, outs):
                hls.io(o)(otmp)


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
    # from hwt.synthesizer.utils import to_rtl_str
    #
    # u = BitonicSorterHLS()
    # u.ITEMS = 4
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(BitonicSorterHLS_large_TC('test_reversed'))
    for tc in BitonicSorterHLS_TCs:
        suite.addTest(unittest.makeSuite(tc))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
