#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Literal

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pragmaInstruction import ThreadSplitSection
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.triggers import WaitWriteOnly
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.frontend.trivial import WriteOnce


class ExampleThreadSplitNoDeps(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)
        self.ASYNC_BEGIN = HwParam(False)
        self.ASYNC_END = HwParam(False)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        # self.dataIn0 = HwIOStructRdVld()
        self.dataOut0 = HwIOStructRdVld()._m()
        # self.dataIn1 = HwIOStructRdVld()
        self.dataOut1 = HwIOStructRdVld()._m()

        t = HBits(self.DATA_WIDTH, signed=False)
        for io in (# self.dataIn0,
                   self.dataOut0,
                   # self.dataIn1,
                   self.dataOut1):
            io: HwIOStructRdVld
            io.T = t

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("bb.mainEntry")
        while b1:
            PyBytecodeBlockLabel("bb.mainLoop")
            hls.write(0, self.dataOut0, mayBecomeFlushable=False)

            t1 = ThreadSplitSection("t1", asyncBegin=self.ASYNC_BEGIN, asyncEnd=self.ASYNC_END)
            t1.begin()
            # this section is extracted as new llvm::Function it will have
            # * 1 input (1b sync from extracted part)
            # * 2 outputs (dataOut1 and 1b sync back to extracted part)
            hls.write(1, self.dataOut1, mayBecomeFlushable=False)
            t1.end()

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class ExampleThreadSplitFirstHasCounter0(ExampleThreadSplitNoDeps):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = self.dataOut0.T.from_py(0)
        while b1:
            hls.write(i, self.dataOut0)
            t1 = ThreadSplitSection("t1", asyncBegin=self.ASYNC_BEGIN, asyncEnd=self.ASYNC_END)
            t1.begin()
            # i is passed trough thread 1
            hls.write(1, self.dataOut1)
            i += 1
            t1.end()


class ExampleThreadSplitFirstHasCounter1(ExampleThreadSplitNoDeps):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = self.dataOut0.T.from_py(0)
        while b1:
            hls.write(i, self.dataOut0)
            t1 = ThreadSplitSection("t1", asyncBegin=self.ASYNC_BEGIN, asyncEnd=self.ASYNC_END)
            t1.begin()
            # i is not an input of thread 1
            hls.write(1, self.dataOut1)
            t1.end()
            i += 1


class ExampleThreadSplitSecondHasCounter(ExampleThreadSplitNoDeps):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = self.dataOut0.T.from_py(0)
        while b1:
            hls.write(0, self.dataOut0)
            t1 = ThreadSplitSection("t1", asyncBegin=self.ASYNC_BEGIN, asyncEnd=self.ASYNC_END)
            t1.begin()
            # i is private to thread 1
            hls.write(i, self.dataOut1)
            i += 1
            t1.end()


class ThreadExtractPassTC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def _test_ExampleThreadSplitNoDeps(self, dut: ExampleThreadSplitNoDeps, enableO0:bool, enableO1:bool, ref0: list[Literal[1]], ref1: list[Literal[1]], N=4):
        # must be enabled at the beginning to reset state of ready properly
        dut.dataOut0._ag.setEnable(True)
        dut.dataOut1._ag.setEnable(True)

        def sim_init():
            yield WaitWriteOnly()
            dut.dataOut0._ag.setEnable(enableO0)
            dut.dataOut1._ag.setEnable(enableO1)

        self.procs.extend([sim_init(), ])
        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))

        self.runSim((N + 1) * CLK_PERIOD)
        self._test_no_comb_loops()
        self.assertValSequenceEqual(dut.dataOut0._ag.data, ref0, (enableO0, enableO1))
        self.assertValSequenceEqual(dut.dataOut1._ag.data, ref1, (enableO0, enableO1))
        self.restartSim()

    def test_ExampleThreadSplitNoDeps_aBegin_aEnd(self, N=4):
        dut = ExampleThreadSplitNoDeps()
        dut.ASYNC_BEGIN = True
        dut.ASYNC_END = True
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [1 for _ in range(N)], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [0 for _ in range(N)], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [0 for _ in range(N)], [1 for _ in range(N)], N=N)

    def test_ExampleThreadSplitNoDeps_aBegin(self, N=4):
        dut = ExampleThreadSplitNoDeps()
        dut.ASYNC_BEGIN = True
        dut.ASYNC_END = False
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [0 for _ in range(N)], [1 for _ in range(N)], N=N)

    def test_ExampleThreadSplitNoDeps_aEnd(self, N=4):
        dut = ExampleThreadSplitNoDeps()
        dut.ASYNC_BEGIN = True
        dut.ASYNC_END = False
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [0 for _ in range(N)], [1 for _ in range(N)], N=N)

    def test_ExampleThreadSplitNoDeps(self, N=4):
        dut = ExampleThreadSplitNoDeps()
        dut.ASYNC_BEGIN = False
        dut.ASYNC_END = False
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [0 for _ in range(N)], [1 for _ in range(N)], N=N)

    def test_ExampleThreadSplitFirstHasCounter0_aBegin_aEnd(self, N=4):
        dut = ExampleThreadSplitFirstHasCounter0()
        dut.ASYNC_BEGIN = True
        dut.ASYNC_END = True
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [1 for _ in range(N)], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [i for i in range(N)], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [i for i in range(N)], [1 for _ in range(N)], N=N)

    def test_ExampleThreadSplitFirstHasCounter0_aBegin(self, N=4):
        dut = ExampleThreadSplitFirstHasCounter0()
        dut.ASYNC_BEGIN = True
        dut.ASYNC_END = False
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [1], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [0], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [i for i in range(N)], [1 for _ in range(N)], N=N)

    def test_ExampleThreadSplitFirstHasCounter0_aEnd(self, N=4):
        dut = ExampleThreadSplitFirstHasCounter0()
        dut.ASYNC_BEGIN = True
        dut.ASYNC_END = False
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [1], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [0], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [i for i in range(N)], [1 for _ in range(N)], N=N)

    def test_ExampleThreadSplitFirstHasCounter0(self, N=4):
        dut = ExampleThreadSplitFirstHasCounter0()
        dut.ASYNC_BEGIN = False
        dut.ASYNC_END = False
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self._test_ExampleThreadSplitNoDeps(dut, False, False, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, False, True, [], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, False, [0], [], N=N)
        self._test_ExampleThreadSplitNoDeps(dut, True, True, [i for i in range(N)], [1 for _ in range(N)], N=N)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
    m = ExampleThreadSplitFirstHasCounter1()
    m.ASYNC_BEGIN = False
    m.ASYNC_END = False
    m.CLK_FREQ = int(1e6)

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED, ]
    )))

    import unittest
    import sys
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(ThreadExtractPassTC)
    # suite = unittest.TestSuite([ThreadExtractPassTC('test_ExampleThreadSplitNoDeps_aEnd')])
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
