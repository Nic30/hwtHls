from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.bitOpt.popcount import Popcount


class PopcountTC(SimTestCase):

    def tearDown(self):
        self.rmSim()
        SimTestCase.tearDown(self)

    def test_CountOnes(self):
        u = Popcount()
        u.DATA_WIDTH = 8
        u.BITS_TO_LOOKUP_IN_ROM = 4
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        test_values = list(range(2 ** u.DATA_WIDTH))
        u.data_in._ag.data.extend(test_values)
        ref = []
        for v in test_values:
            ref.append(v.bit_count())
        self.runSim((len(ref) + 1) * CLK_PERIOD)

        self.assertValSequenceEqual(u.data_out._ag.data, ref)


if __name__ == '__main__':
    import sys
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PopcountTC("test_CountLeadingZeros")])
    suite = testLoader.loadTestsFromTestCase(PopcountTC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
