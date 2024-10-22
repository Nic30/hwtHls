from hwt.hdl.types.bits import HBits
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.architecture.transformation._operatorToHwtLowering.operatorHwImplementations.countBits import CountLeadingZeros, CountLeadingOnes
from hwtHls.code import ctlz, cttz
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from pyMathBitPrecise.bit_utils import mask


class CountBitsTC(SimTestCase):

    def tearDown(self):
        self.rmSim()
        SimTestCase.tearDown(self)

    def test_CountLeadingZeros(self):
        dut = CountLeadingZeros()
        dut.DATA_WIDTH = 4
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        test_values = list(range(2 ** dut.DATA_WIDTH))
        dut.data_in._ag.data.extend(test_values)

        ref = []
        for v in test_values:
            leading = dut.DATA_WIDTH
            while v:
                v >>= 1
                leading -= 1
            ref.append(leading)

        self.runSim((len(ref) + 2) * CLK_PERIOD)
        ref.append(0)

        self.assertValSequenceEqual(dut.data_out._ag.data, ref)

    def test_CountLeadingOnes(self):
        dut = CountLeadingOnes()
        dut.DATA_WIDTH = 4
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        test_values = list(range(2 ** dut.DATA_WIDTH))
        dut.data_in._ag.data.extend(test_values)

        ref = []
        for v in test_values:
            x = 1 << dut.DATA_WIDTH - 1
            leading = 0
            while v & x:
                x >>= 1
                leading += 1

            ref.append(leading)

        self.runSim((len(ref) + 2) * CLK_PERIOD)
        ref.append(4)

        self.assertValSequenceEqual(dut.data_out._ag.data, ref)

    def test_const_ctlz(self):
        for bit_length in range(1, 16):
            t = HBits(bit_length)
            m = mask(bit_length)
            for sh in range(bit_length + 1):
                zc = ctlz(t.from_py(m >> sh))
                self.assertEqual(int(zc), sh, (bit_length, sh))

    def test_const_cttz(self):
        for bit_length in range(1, 16):
            t = HBits(bit_length)
            m = mask(bit_length)
            for sh in range(bit_length + 1):
                zc = cttz(t.from_py((m << sh) & m))
                self.assertEqual(int(zc), sh, (bit_length, sh))


if __name__ == '__main__':
    import sys
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([CountBitsTC('test_CountLeadingZeros')])
    suite = testLoader.loadTestsFromTestCase(CountBitsTC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
