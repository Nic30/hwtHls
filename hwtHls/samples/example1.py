import unittest

from hwt.hdl.constants import Time
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.interfaceLevel.unit import Unit
from hwt.synthesizer.shortcuts import toRtl
from hwtHls.hls import Hls


class HlsMAC_example(Unit):
    def _declr(self):
        addClkRstn(self)
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)
        self.c = VectSignal(32, signed=False)
        self.d = VectSignal(32, signed=False)
        self.e = VectSignal(32, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            r = hls.read
            e = (r(self.a) * r(self.b)) + (r(self.c) * r(self.d))
            hls.write(e, self.e)


class HlsMAC_example_TC(SimTestCase):
    def test_simple(self):
        u = HlsMAC_example()
        self.prepareUnit(u)
        u.a._ag.data.append(3)
        u.b._ag.data.append(4)
        u.c._ag.data.append(5)
        u.d._ag.data.append(6)

        self.doSim(40 * Time.ns)

        self.assertValEqual(u.e._ag.data[-1], (3 * 4) + (5 * 6))


if __name__ == "__main__":
    u = HlsMAC_example()
    print(toRtl(u))

    suite = unittest.TestSuite()
    # suite.addTest(FrameTmplTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsMAC_example_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
