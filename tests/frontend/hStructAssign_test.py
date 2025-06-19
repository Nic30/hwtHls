#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwt.hwParam import HwParam
from hwt.hwIOs.utils import addClkRstn
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hdl.types.bits import HBits
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from tests.frontend.trivial import WriteOnce
from hwt.hdl.types.struct import HStruct
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD


class HStructAssignHwModule(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(64)
        self.T = HwParam(
        HStruct(
            (HBits(8)[4], "dataArr"),
            (HBits(32), "dataBits"),
        ))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        o = self.dataOut = HwIOStructRdVld()._m()
        o.T = HBits(self.DATA_WIDTH, signed=False)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        v = self.T.from_py(None)

        v.dataArr[0] = 0
        v.dataArr[1] = 1
        v.dataArr[2] = 2
        v.dataArr[3] = 3

        v.dataArr[2] = 4

        v.dataBits = 0x99

        hls.write(v, self.dataOut)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class HStructAssign_TC(SimTestCase):

    def test_HStructAssignHwModule(self):
        dut = HStructAssignHwModule()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK = 4
        self.runSim(CLK * CLK_PERIOD)
        v = dut.T.from_py({
            "dataArr": (0, 1, 4, 3),
            "dataBits": 0x99,
        })
        refVal = int(v._reinterpret_cast(HBits(64)))
        self.assertValSequenceEqual(dut.dataOut._ag.data, [refVal, ])


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = HStructAssignHwModule()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
        #llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED],
        debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HStructAssign_TC("test_HStructAssignHwModule")])
    suite = testLoader.loadTestsFromTestCase(HStructAssign_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
