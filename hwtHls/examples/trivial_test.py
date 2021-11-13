from hwt.serializer.combLoopAnalyzer import CombLoopAnalyzer
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.examples.trivial import WriteOnce, ReadWriteOnce0, \
    ReadWriteOnce1, WhileTrueWrite, WhileTrueReadWrite, ReadWriteOnce2
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.examples.errors.combLoops import freeze_set_of_sets
from hwtSimApi.constants import CLK_PERIOD


class HlsStreamMachineTrivial_TC(SimTestCase):

    def _test_no_comb_loops(self):
        s = CombLoopAnalyzer()
        s.visit_Unit(self.u)
        comb_loops = freeze_set_of_sets(s.report())
        msg_buff = []
        for loop in comb_loops:
            msg_buff.append(10 * "-")
            for s in loop:
                msg_buff.append(str(s.resolve()[1:]))

        self.assertEqual(comb_loops, frozenset(), msg="\n".join(msg_buff))

    def test_WriteOnce(self):
        u = WriteOnce()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 4
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data, [1, ])

    def test_ReadWriteOnce0(self, cls=ReadWriteOnce0):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 4
        for i in range(CLK):
            u.dataIn._ag.data.append(i)

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertSequenceEqual(u.dataIn._ag.data, [2, 3])
        self.assertValSequenceEqual(u.dataOut._ag.data, [0, ])

    def test_ReadWriteOnce1(self):
        self.test_ReadWriteOnce0(ReadWriteOnce1)

    def test_ReadWriteOnce2(self, cls=ReadWriteOnce2):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 4
        for i in range(CLK):
            u.dataIn._ag.data.append(i)

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertSequenceEqual(u.dataIn._ag.data, [2, 3])
        self.assertValSequenceEqual(u.dataOut._ag.data, [1, ])

    def test_WhileTrueWrite(self):
        u = WhileTrueWrite()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 4
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data, [10 for _ in range(CLK - 1) ])

    def test_WhileTrueReadWrite(self):
        u = WhileTrueReadWrite()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK = 4
        for i in range(CLK):
            u.dataIn._ag.data.append(i)

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.dataOut._ag.data,
                                    [i for i in range(CLK - 1)])


if __name__ == "__main__":
    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(HlsStreamMachineTrivial_TC('test_WhileTrueWrite'))
    suite.addTest(unittest.makeSuite(HlsStreamMachineTrivial_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
