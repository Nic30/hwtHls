from hwt.simulator.simTestCase import SimTestCase
from hwtHls.examples.trivial_test import HlsStreamMachineTrivial_TC
from hwtHls.examples.while_if import WhileAndIf0, WhileAndIf2
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.utils import freq_to_period


class HlsStreamMachineWhileIf_TC(SimTestCase):

    def test_WhileAndIf0(self):
        u = WhileAndIf0()
        u.FREQ = int(10e6)
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 8
        clk_period = freq_to_period(u.FREQ)

        self.runSim((CLK + 10) * int(clk_period))
        HlsStreamMachineTrivial_TC._test_no_comb_loops(self)

        expected = []
        for _ in range(CLK):
            x = 10
            while x:
                if x < 3:
                    x = x - 1
                else:
                    x = x - 3
                expected.append(x)

        self.assertValSequenceEqual(u.dataOut._ag.data, expected)

    def test_WhileAndIf2(self):
        u = WhileAndIf2()
        u.FREQ = int(10e6)

        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        clk_period = freq_to_period(u.FREQ)
        inputs = [6, 4, 0, 3, 3, 3, 1]
        CLK = len(inputs)
        expected = []
        in_iter = iter(inputs)
        clk_it = iter(range(CLK))
        try:
            while True:
                x = 10
                while x:
                    x = x - next(in_iter)
                    expected.append(x)
                    next(clk_it)
        except StopIteration:
            pass

        u.dataIn._ag.data.extend(inputs)
        self.runSim((CLK + 10) * int(clk_period))
        HlsStreamMachineTrivial_TC._test_no_comb_loops(self)
        self.assertValSequenceEqual(u.dataOut._ag.data, expected)


if __name__ == "__main__":
    import unittest
    suite = unittest.TestSuite()
    suite.addTest(HlsStreamMachineWhileIf_TC('test_WhileAndIf0'))
    # suite.addTest(unittest.makeSuite(HlsStreamMachineWhileIf_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
