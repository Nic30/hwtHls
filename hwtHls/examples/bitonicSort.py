#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.interfaces.utils import addClkRstn
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.logic.bitonicSorter import BitonicSorter, BitonicSorterTC
from hwt.hdl.constants import Time


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
                                     [hls.read(i) for i in self.inputs])
            for o, otmp in zip(self.outputs, outs):
                hls.write(otmp, o)


class BitonicSorterHLS_large(BitonicSorterHLS):
    def _config(self):
        BitonicSorterHLS._config(self)
        self.CLK_FREQ = int(100e6)
        self.ITEMS.set(16)


class BitonicSorterHLS_TC(BitonicSorterTC):
    def createUnit(self):
        u = BitonicSorterHLS()
        self.prepareUnit(u, targetPlatform=VirtualHlsPlatform())
        return u


class BitonicSorterHLS_large_TC(BitonicSorterTC):
    SIM_TIME = 200 * Time.ns

    def createUnit(self):
        u = BitonicSorterHLS_large()
        self.prepareUnit(u, targetPlatform=VirtualHlsPlatform())
        return u


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import toRtl

    u = BitonicSorterHLS()
    u.ITEMS.set(2)
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))

    suite = unittest.TestSuite()
    # suite.addTest(BitonicSorterHLS_large_TC('test_reversed'))
    suite.addTest(unittest.makeSuite(BitonicSorterHLS_TC))
    suite.addTest(unittest.makeSuite(BitonicSorterHLS_large_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
