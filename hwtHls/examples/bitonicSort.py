#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.hdl.constants import Time
from hwt.interfaces.utils import addClkRstn
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.logic.bitonicSorter import BitonicSorter, BitonicSorterTC


class BitonicSorterHLS(BitonicSorter):
    def _config(self):
        BitonicSorter._config(self)
        self.CLK_FREQ = int(100e6)

    def _declr(self):
        addClkRstn(self)
        BitonicSorter._declr(self)

    def _impl(self):
        with Hls(self, self.CLK_FREQ) as hls:
            outs = self.bitonic_sort(self.cmpFn,
                                     [hls.io(i) for i in self.inputs])
            for o, otmp in zip(self.outputs, outs):
                hls.io(o)(otmp)


class BitonicSorterHLS_large(BitonicSorterHLS):
    def _config(self):
        BitonicSorterHLS._config(self)
        self.CLK_FREQ = int(100e6)
        self.ITEMS = 16


class BitonicSorterHLS_TC(BitonicSorterTC):
    def createUnit(self):
        u = BitonicSorterHLS()
        self.prepareUnit(u, target_platform=VirtualHlsPlatform())
        return u


class BitonicSorterHLS_large_TC(BitonicSorterTC):
    SIM_TIME = 200 * Time.ns

    def createUnit(self):
        u = BitonicSorterHLS_large()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        return u


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str

    u = BitonicSorterHLS()
    u.ITEMS = 2
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(BitonicSorterHLS_large_TC('test_reversed'))
    suite.addTest(unittest.makeSuite(BitonicSorterHLS_TC))
    suite.addTest(unittest.makeSuite(BitonicSorterHLS_large_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
