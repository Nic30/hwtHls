#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.serializer.combLoopAnalyzer import CombLoopAnalyzer
from hwt.simulator.simTestCase import SimTestCase
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.examples.errors.combLoops import freeze_set_of_sets
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask


class AndShiftInLoop2(HwModule):

    def _config(self) -> None:
        self.FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t = self.i._dtype
        i0 = hls.var("i0", t)
        i1 = hls.var("i0", t)
        i0 = mask(8)
        i1 = mask(8)
        while BIT.from_py(1):
            i = hls.read(self.i).data
            i0 &= i
            i1 &= (i0 << 1)
            hls.write(i1, self.o)

    def _impl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class AndShiftInLoop3(HwModule):

    def _config(self) -> None:
        self.FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t = self.i._dtype
        i0, i1, i2 = (hls.var("i0", t) for _ in range(3))
        i0 = mask(8)
        i1 = mask(8)
        i2 = mask(8)
        while BIT.from_py(1):
            i = hls.read(self.i).data
            i0 &= i
            i1 &= (i0 << 1)
            i2 &= (i2 << 1)
            hls.write(i2, self.o)

    def _impl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class AndShiftInLoop_TC(SimTestCase):

    def _test_no_comb_loops(self):
        s = CombLoopAnalyzer()
        s.visit_HwModule(self.dut)
        comb_loops = freeze_set_of_sets(s.report())
        msg_buff = []
        for loop in comb_loops:
            msg_buff.append(10 * "-")
            for s in loop:
                msg_buff.append(str(s.resolve()[1:]))

        self.assertEqual(comb_loops, frozenset(), msg="\n".join(msg_buff))

    def test_AndShiftInLoop2(self):
        dut = AndShiftInLoop2()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = int(freq_to_period(dut.FREQ))
        CLK = 7

        expected = []
        all1 = mask(8)
        up1 = mask(7) << 1
        inputs = [all1, all1, all1, up1, up1, up1, up1, up1, up1]
        inIt = iter(inputs)

        def model():
            i0 = uint8_t.from_py(all1)
            i1 = uint8_t.from_py(all1)
            while True:
                i = next(inIt)
                i0 = i0 & i
                i1 = i1 & (i0 << 1)
                yield int(i1)

        m = model()
        for _ in range(CLK):
            expected.append(next(m))

        dut.i._ag.data.extend(inputs)
        self.runSim((CLK + 1) * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, expected)

    def test_AndShiftInLoop3(self):
        dut = AndShiftInLoop3()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = int(freq_to_period(dut.FREQ))
        CLK = 7

        expected = []
        all1 = mask(8)
        up1 = mask(7) << 1
        inputs = [all1, all1, all1, up1, up1, up1, up1, up1, up1]
        inIt = iter(inputs)

        def model():
            i0 = uint8_t.from_py(all1)
            i1 = uint8_t.from_py(all1)
            i2 = uint8_t.from_py(all1)
            while True:
                i = next(inIt)
                i0 = i0 & i
                i1 = i1 & (i0 << 1)
                i2 = i2 & (i2 << 1)
                yield int(i2)

        m = model()
        for _ in range(CLK):
            expected.append(next(m))

        dut.i._ag.data.extend(inputs)
        self.runSim((CLK + 1) * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, expected)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    dut = AndShiftInLoop3()
    print(to_rtl_str(dut, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AndShiftInLoop('test_AndShiftInLoop')])
    suite = testLoader.loadTestsFromTestCase(AndShiftInLoop_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
