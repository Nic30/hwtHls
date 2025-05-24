#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from hwt.hdl.types.bits import HBits
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.architecture.componentGenerators.ctpop import Ctpop
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period


class Ctpop_TC(SimTestCase):

    def tearDown(self):
        self.rmSim()
        SimTestCase.tearDown(self)

    def test_CountOnes_pyListRom(self, FREQ=100e6):
        self.test_CountOnes(FREQ=FREQ, DBG_ROM_IN_PYLIST=True)

    def test_CountOnes(self, FREQ=100e6, DATA_WIDTH=8, BITS_TO_LOOKUP_IN_ROM=4, DBG_ROM_IN_PYLIST=False):
        dut = Ctpop()
        dut.CLK_FREQ = int(FREQ)
        dut.T = HBits(DATA_WIDTH)
        dut.BITS_TO_LOOKUP_IN_ROM = BITS_TO_LOOKUP_IN_ROM
        dut.DBG_ROM_IN_PYLIST = DBG_ROM_IN_PYLIST
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        test_values = list(range(2 ** dut.T.bit_length()))
        dut.data_in._ag.data.extend(test_values)
        ref = []
        for v in test_values:
            ref.append(v.bit_count())
        self.runSim((len(ref) + 1) * int(freq_to_period(dut.CLK_FREQ)))

        self.assertValSequenceEqual(dut.data_out._ag.data, ref)


if __name__ == '__main__':
    import sys
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    sys.setrecursionlimit(int(1e6))

    m = Ctpop()
    m.CLK_FREQ = int(100e6)
    m.T = HBits(8)
    m.BITS_TO_LOOKUP_IN_ROM = 4
    m.DBG_ROM_IN_PYLIST = True

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[("print-after-all", 0, "", "true"), ]
    )))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Ctpop_TC("test_CountOnes_pyListRom")])
    suite = testLoader.loadTestsFromTestCase(Ctpop_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
