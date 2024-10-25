#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class VariableChain(HwModule):

    @override
    def hwConfig(self) -> None:
        self.LEN = HwParam(3)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        # :note: all variables are supposed to be reduced out and just direct connection should remain
        path = [hls.var(f"i{i:d}", self.i._dtype) for i in range(self.LEN)]
        while b1:
            for i, p in enumerate(path):
                if i == 0:
                    prev = hls.read(self.i).data
                else:
                    prev = path[i - 1]
                p(prev)

            hls.write(path[-1], self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class VariableChain_TC(SimTestCase):

    def test_VariableChain(self, cls=VariableChain):
        dut = VariableChain()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.i._ag.data.extend(range(1, 9))
        self.runSim((8 + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, list(range(1, 9)))


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = VariableChain()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyArrShift_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(VariableChain_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
