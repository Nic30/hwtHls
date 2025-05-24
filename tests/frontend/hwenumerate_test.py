#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HdlType_to_HwIO
from hwt.hwIOs.std import HwIOClk
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.hwenumerate import hwenumerate
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.frontend.trivial import WriteOnce


class HlsPythonHwenumerate_romScalar(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(HwIOClk.DEFAULT_FREQ)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        t = HBits(8)
        self.o = HdlType_to_HwIO().apply(
            HStruct(
                (HBits(4), "i"),
                (t, "v"),
                )
        )._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        rom = HBits(8)[16].from_py(i % 3 for i in range(16))
        while b1:
            for i, v in hwenumerate(rom):
                tmp = self.o._dtype.from_py(None)
                tmp.i = i[4:]
                tmp.v = v
                hls.write(tmp, self.o)

    @override
    def hwImpl(self):
        WriteOnce.hwImpl(self)


class HlsPythonHwenumerate_TC(SimTestCase):

    def test_HlsPythonHwrange_fromInt0(self, cls=HlsPythonHwenumerate_romScalar):
        N = 16 + 2
        dut = HlsPythonHwenumerate_romScalar()
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        CLK_PERIOD = freq_to_period(dut.CLK_FREQ)
        self.runSim((N + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o.i._ag.data, [i % 16 for i in range(N)])
        self.assertValSequenceEqual(dut.o.v._ag.data, [(i % 16) % 3 for i in range(N)])


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.debugBundle import HlsDebugBundle
    # from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = HlsPythonHwenumerate_romScalar()
    print(to_rtl_str(m, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                                                     # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED, ]
                                                     )))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsPythonHwrange_TC('test_HlsPythonHwrange_fromInt1_breakBefore')])
    suite = testLoader.loadTestsFromTestCase(HlsPythonHwenumerate_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
