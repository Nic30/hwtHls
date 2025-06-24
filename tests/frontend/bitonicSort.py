#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.constants import Time
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.logic.bitonicSorter import BitonicSorter, BitonicSorterTC
from tests.frontend.trivial import WriteOnce


class BitonicSorterHLS0(BitonicSorter):
    """
    :note: This is an example of bad codestyle, each input and output has
        independent synchronization, which makes circuit synchronization
        exponentially more complex and compilation slower.
        This is implemented in exactly this way because it is a test of exactly that.
    """

    @override
    def hwConfig(self):
        BitonicSorter.hwConfig(self)
        self.CLK_FREQ = HwParam(int(50e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        BitonicSorter.hwDeclr(self)

    @hwt_expr_producer
    def bitonic_compare(self, cmpFn, x, layer, offset):
        dist = len(x) // 2
        _x = [None for _ in range(len(x))]
        for i in range(dist):
            cmpRes = cmpFn(x[i], x[i + dist])
            # cmpRes ? keep : swap
            _x[i] = cmpRes._ternary(x[i], x[i + dist])
            _x[i + dist] = cmpRes._ternary(x[i + dist], x[i])

        for i, _x_i in enumerate(_x):
            _x_i._name = f"sort_tmp_{layer:d}_{offset:d}_{i:d}"

        return _x

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            reads = [hls.read(i).data for i in self.inputs]
            outs = self.bitonic_sort(self.cmpFn, reads)
            for otmp, o in zip(outs, self.outputs):
                hls.write(otmp, o)

    @override
    def hwImpl(self) -> None:
       WriteOnce.hwImpl(self)


class BitonicSorterHLS1(BitonicSorterHLS0):
    """
    :see: note about codestyle in :class:`BitonicSorterHLS0`
    """
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            reads = []
            for i in self.inputs:
                d = hls.read(i).data
                reads.append(d)
                del d

            outs = self.bitonic_sort(self.cmpFn, reads)
            for otmp, o in zip(outs, self.outputs):
                hls.write(otmp, o)


class BitonicSorterHLS0_TC(BitonicSorterTC):

    @classmethod
    @override
    def setUpClass(cls):
        cls.dut = BitonicSorterHLS0()
        cls.compileSim(cls.dut, target_platform=VirtualHlsPlatform())


class BitonicSorterHLS1_TC(BitonicSorterTC):

    @classmethod
    @override
    def setUpClass(cls):
        cls.dut = BitonicSorterHLS1()
        cls.compileSim(cls.dut, target_platform=VirtualHlsPlatform())


class BitonicSorterHLS_large_TC(BitonicSorterTC):
    SIM_TIME = 220 * Time.ns

    @classmethod
    @override
    def setUpClass(cls):
        cls.dut = BitonicSorterHLS0()
        cls.dut.ITEMS = 16
        cls.compileSim(cls.dut, target_platform=VirtualHlsPlatform())


BitonicSorterHLS_TCs = [
    BitonicSorterHLS0_TC,
    BitonicSorterHLS1_TC,
    BitonicSorterHLS_large_TC
]

if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = BitonicSorterHLS0()
    m.ITEMS = 4
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BitonicSorterHLS_large_TC('test_reversed')])
    suite = unittest.TestSuite(testLoader.loadTestsFromTestCase(tc)
                               for tc in BitonicSorterHLS_TCs)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
