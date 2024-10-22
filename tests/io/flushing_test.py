#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.triggers import Timer
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.frontend.pyBytecode.stmWhile import TRUE


class ExampleFlushing0(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i0 = HwIODataRdVld()

            self.o0: HwIODataRdVld = HwIODataRdVld()._m()
            self.o1: HwIODataRdVld = HwIODataRdVld()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:
            i0 = hls.read(self.i0)
            hls.write(i0, self.o0)  # o0 should be able to write before o1 if o1 stalls
            hls.write(i0, self.o1)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class ExampleFlushing1OptionalLoop(ExampleFlushing0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:
            i0 = hls.read(self.i0).data
            tmp = HBits(self.DATA_WIDTH).from_py(0)
            while tmp != i0:
                hls.write(tmp, self.o0)
                tmp += 1

            hls.write(i0, self.o1)


class Flushing_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsAstTrivial_TC._test_no_comb_loops(self)

    def _test_ExampleFlushing0(self, enableO1=True,
                               randomizeI0=False, randomizeO0=False, randomizeO1=False,
                               N=4, timeMultiplier=1):
        dut = ExampleFlushing0()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.i0._ag.data.extend(range(1, N + 1))
        if randomizeI0:
            self.randomize(dut.i0)
        if randomizeO0:
            self.randomize(dut.o0)
        if randomizeO1:
            self.randomize(dut.o1)

        if not enableO1:

            def disableO1Proc():
                yield Timer(1)
                dut.o1._ag.setEnable(False)

            self.procs.append(disableO1Proc())

        self.runSim(2 * int(N * CLK_PERIOD * timeMultiplier))
        self._test_no_comb_loops()

        if enableO1:
            o0Ref = list(range(1, N + 1))
            o1Ref = o0Ref
        else:
            o0Ref = [1, ]
            o1Ref = []
        self.assertValSequenceEqual(dut.o0._ag.data, o0Ref)
        self.assertValSequenceEqual(dut.o1._ag.data, o1Ref)

    def test_ExampleFlushing0_allEn(self):
        self._test_ExampleFlushing0()

    def test_ExampleFlushing0_allEn_rand(self):
        self._test_ExampleFlushing0(randomizeI0=True, randomizeO0=True, randomizeO1=True,
                                    timeMultiplier=6)

    def test_ExampleFlushing0_o1Block(self):
        self._test_ExampleFlushing0(enableO1=False)

    def test_ExampleFlushing0_o1Block_rand(self):
        self._test_ExampleFlushing0(enableO1=False, randomizeI0=True, randomizeO0=True,
                                    timeMultiplier=3)

    def test_ExampleFlushing1OptionalLoop(self):
        dut = ExampleFlushing1OptionalLoop()

    # problem is that in triangle entry and bottom are joined and in same clk
    # write of inputs to right block can not happen because bottom part does not get ready as
    # loop in right does not exit yet

    # There are cases where flushing is required and can not be avoided by a different ArchElement allocation strategy:
    # * For nodes in same block we theoretically can cut element into multiple pieces with own validity flag.
    # * For 1CLK CFG triangle 0->1->2, 1->1, 0->2 we can not merge blocks and
    #   flush for channels on 0->1 is simply required because data on 1->2 won't be always present
    #   when data of 0->1 is provided and the loop on 1 would never had the chance to execute if
    #   we had to wait on data on 1->2.
    #   To avoid this obvious deadlock we can use flushing for channels on 0->1 edge.

    # Flushing:
    # * Flushing may be required for stalling pipelines/ArchElements to prevent deadlock.
    # * Flushing is relevant only for IO write nodes and channel write nodes of zero capacity.
    # * Node can flush if all predecessor IO have ack.
    # * Node should flush if it can flush, has ready and some successor IO does not have ack,
    # * Relevant node should be flushable if:
    #    * There are relevant successor nodes.
    #    * It is write to channel in ending in same HsSCC.


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = ExampleFlushing0()
    m.CLK_FREQ = int(1e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Flushing_TC("test_ExampleFlushing0_allEn")])
    suite = testLoader.loadTestsFromTestCase(Flushing_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

