#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.logic.bcdToBin_test import bin_to_bcd
from hwtLib.logic.binToBcd_test import BinToBcdTC as HwtLibBinToBcdTC
from hwtSimApi.utils import freq_to_period
from tests.frontend.pyBytecode.binToBcd import BinToBcd


class BinToBcd_TC(HwtLibBinToBcdTC):

    @classmethod
    def setUpClass(cls):
        cls.u = BinToBcd()
        cls.u.DATA_WIDTH = 10
        cls.CLK_PERIOD = int(freq_to_period(cls.u.FREQ))
        cls.compileSim(cls.u, target_platform=Artix7Medium(debugFilter={HlsDebugBundle.DBG_3_mir}))

    def test_MIR(self):

        with open(Path(self.DEFAULT_LOG_DIR) / "BinToBcd.mainThread" / "03.mir.ll") as f:
            refData = [0, 1, 2, 3, 4, 5, 6, 7, 99, 127, 255]
            args = [iter(refData), []]
            LlvmMirInterpret.runMirStr(f.read(), "BinToBcd.mainThread", args)
            self.assertValSequenceEqual(args[1], tuple(bin_to_bcd(d, 3) for d in refData))


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str

    u = BinToBcd()
    u.DATA_WIDTH = 10
    print(to_rtl_str(u, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BinToBcd_TC("test_MIR")])
    suite = testLoader.loadTestsFromTestCase(BinToBcd_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
