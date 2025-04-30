#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.math import log2ceil
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.architecture.componentGenerators.countBits import CountLeadingZeros, CountLeadingOnes
from hwtHls.code import ctlz, cttz
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask


class CountBitsTC(SimTestCase):

    def tearDown(self):
        self.rmSim()
        SimTestCase.tearDown(self)

    def test_CountLeadingZeros(self):
        dut = CountLeadingZeros()
        dut.T = HBits(4)
        dut.FREQ = int(1e6)
        # dut.OUT_CHANNEL_TYPE = dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        CLK_PERIOD = int(freq_to_period(dut.FREQ))
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        #dut.data_out._ag.presetBeforeClk = True
        #dut.data_in._ag.presetBeforeClk = True
        DATA_WIDTH = dut.T.bit_length()
        test_values = list(range(2 ** DATA_WIDTH))
        dut.data_in._ag.data.extend(test_values)

        ref = []
        for v in test_values:
            leading = DATA_WIDTH
            while v:
                v >>= 1
                leading -= 1
            ref.append(leading)

        self.runSim((len(ref) + 3) * CLK_PERIOD)
        #ref.append(0)

        self.assertValSequenceEqual(dut.data_out._ag.data, ref)

    def test_CountLeadingOnes(self):
        dut = CountLeadingOnes()
        dut.T = HBits(4)
        dut.FREQ = int(1e6)
        CLK_PERIOD = int(freq_to_period(dut.FREQ))
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        DATA_WIDTH = dut.T.bit_length()
        test_values = list(range(2 ** DATA_WIDTH))
        dut.data_in._ag.data.extend(test_values)

        ref = []
        for v in test_values:
            x = 1 << DATA_WIDTH - 1
            leading = 0
            while v & x:
                x >>= 1
                leading += 1

            ref.append(leading)

        self.runSim((len(ref) + 2) * CLK_PERIOD)
        #ref.append(4)

        self.assertValSequenceEqual(dut.data_out._ag.data, ref)

    def test_const_ctlz(self):
        for bit_length in range(1, 16):
            t = HBits(bit_length)
            m = mask(bit_length)
            for sh in range(bit_length + 1):
                v = m >> sh
                zc = ctlz(t.from_py(v))
                self.assertEqual(zc._dtype.bit_length(), log2ceil(bit_length + 1))
                self.assertEqual(int(zc), sh, (v, bit_length, sh))

    def test_const_cttz(self):
        for bit_length in range(1, 16):
            t = HBits(bit_length)
            m = mask(bit_length)
            for sh in range(bit_length + 1):
                v = (m << sh) & m
                zc = cttz(t.from_py(v))
                self.assertEqual(int(zc), sh, (v, bit_length, sh))


if __name__ == '__main__':
    import sys
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([CountBitsTC('test_CountLeadingZeros')])
    suite = testLoader.loadTestsFromTestCase(CountBitsTC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
