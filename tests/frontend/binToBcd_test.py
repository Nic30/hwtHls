#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.logic.bcdToBin_test import bin_to_bcd
from hwtLib.logic.binToBcd_test import BinToBcdTC as HwtLibBinToBcdTC
from hwtSimApi.utils import freq_to_period
from hwtHls.llvm.llvmIr import LLVMStringContext, LlvmCompilationBundle
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.frontend.binToBcd import BinToBcd
from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS


class BinToBcd_TC(HwtLibBinToBcdTC):

    @classmethod
    def setUpClass(cls):
        cls.dut = BinToBcd()
        cls.dut.DATA_WIDTH = 8
        cls.CLK_PERIOD = int(freq_to_period(cls.dut.CLK_FREQ))
        cls.compileSim(cls.dut, target_platform=Artix7Medium(debugFilter={HlsDebugBundle.DBG_2_0_mir,
                                                                          HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                                                                          HlsDebugBundle.DBG_4_0_addSignalNamesToData}))

    def test_0to127(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)
        HwtLibBinToBcdTC.test_0to127(self)

    def test_MIR(self):
        # :attention: MIR is loaded to file to test MIR loading, in other tests mir object should be used directly
        # and dump to file is not required
        with open(Path(self.DEFAULT_LOG_DIR) / "BinToBcd_BinToBcd.mainThread" / "BinToBcd.mainThread" / "02.00.mir.ll") as f:
            refData = [0, 1, 2, 3, 4, 5, 6, 7, 99, 127, 255]
            args = [iter(refData), []]
            nameOfMain = "BinToBcd.mainThread"
            llvm = LlvmCompilationBundle(nameOfMain, [])
            p = Artix7Medium()
            LlvmMirInterpret.runMirStr(llvm, [], p._componentGenerators, nameOfMain, f.read(), args)
            self.assertValSequenceEqual(args[1], tuple(bin_to_bcd(d, 3) for d in refData))


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = BinToBcd()
    m.DATA_WIDTH = 10
    print(to_rtl_str(m, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
        HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
        HlsDebugBundle.DBG_4_0_addSignalNamesToData
    }),  # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED],
    )))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BinToBcd_TC("test_MIR")])
    suite = testLoader.loadTestsFromTestCase(BinToBcd_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
