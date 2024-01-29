from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.bitOpt.countBits import CountLeadingZeros, CountLeadingOnes


class CountBitsTC(SimTestCase):

    def tearDown(self):
        self.rmSim()
        SimTestCase.tearDown(self)

    def test_CountLeadingZeros(self):
        u = CountLeadingZeros()
        u.DATA_WIDTH = 4
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        test_values = list(range(2 ** u.DATA_WIDTH))
        u.data_in._ag.data.extend(test_values)

        ref = []
        for v in test_values:
            leading = u.DATA_WIDTH
            while v:
                v >>= 1
                leading -= 1
            ref.append(leading)

        self.runSim((len(ref) + 2) * CLK_PERIOD)
        ref.append(0)

        self.assertValSequenceEqual(u.data_out._ag.data, ref)

    def test_CountLeadingOnes(self):
        u = CountLeadingOnes()
        u.DATA_WIDTH = 4
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        test_values = list(range(2 ** u.DATA_WIDTH))
        u.data_in._ag.data.extend(test_values)

        ref = []
        for v in test_values:
            x = 1 << u.DATA_WIDTH - 1
            leading = 0
            while v & x:
                x >>= 1
                leading += 1

            ref.append(leading)

        self.runSim((len(ref) + 2) * CLK_PERIOD)
        ref.append(4)

        self.assertValSequenceEqual(u.data_out._ag.data, ref)


if __name__ == '__main__':
    import sys
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([CountBitsTC('test_CountLeadingZeros')])
    suite = testLoader.loadTestsFromTestCase(CountBitsTC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
