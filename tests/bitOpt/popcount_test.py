from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.bitOpt.popcount import Popcount


class PopcountTC(SimTestCase):

    def tearDown(self):
        self.rmSim()
        SimTestCase.tearDown(self)

    def test_CountOnes(self):
        dut = Popcount()
        dut.DATA_WIDTH = 8
        dut.BITS_TO_LOOKUP_IN_ROM = 4
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        test_values = list(range(2 ** dut.DATA_WIDTH))
        dut.data_in._ag.data.extend(test_values)
        ref = []
        for v in test_values:
            ref.append(v.bit_count())
        self.runSim((len(ref) + 1) * CLK_PERIOD)

        self.assertValSequenceEqual(dut.data_out._ag.data, ref)


if __name__ == '__main__':
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    import sys

    sys.setrecursionlimit(int(1e6))
    m = Popcount()
    m.DATA_WIDTH = 8
    m.BITS_TO_LOOKUP_IN_ROM = 4

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
    
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PopcountTC("test_CountLeadingZeros")])
    suite = testLoader.loadTestsFromTestCase(PopcountTC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
