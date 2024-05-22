#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.platform.xilinx.artix7 import Artix7Slow
from hwtLib.logic.crcPoly import CRC_32
from tests.frontend.ast.crc import CrcCombHls
from tests.frontend.ast.ifstm import HlsSimpleIfStatement
from tests.frontend.ast.pid import PidControllerHls


class HlsSynthesisChecksTC(SimTestCase):

    def test_PidControllerHls(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # debug is enabled in order to test debug passes as well
            self.compileSimAndStart(PidControllerHls(),
                                    target_platform=VirtualHlsPlatform(debugDir=tmp_dir,
                                                                       debugFilter=HlsDebugBundle.ALL))

    def test_PidControllerHlsDebug(self):
        self._test(PidControllerHls())

    def test_PidControllerHls_unschedulable(self):
        m = PidControllerHls()
        m.CLK_FREQ = int(150e6)
        with self.assertRaises(TimeConstraintError):
            self._test(m)

    def test_HlsSimpleIfStatement(self):
        self._test(HlsSimpleIfStatement())
    
    def test_CrcCombHls_crc32_128b_200MHz(self):
        # :note: takes 6s
        m = CrcCombHls()
        m.setConfig(CRC_32)
        m.CLK_FREQ = int(200e6)
        m.DATA_WIDTH = 128
        self._test(m)

    def test_CrcCombHls_crc32_8b_100MHz(self):
        m = CrcCombHls()
        m.setConfig(CRC_32)
        m.CLK_FREQ = int(100e6)
        m.DATA_WIDTH = 8
        self._test(m)

    def test_CrcCombHls_crc32_128b_200MHz_XilinxAtrix7Slow(self):
        # takes 6s
        m = CrcCombHls()
        m.setConfig(CRC_32)
        m.CLK_FREQ = int(200e6)
        m.DATA_WIDTH = 128
        self.compileSimAndStart(m, target_platform=Artix7Slow())

    def _test(self, unit):
        self.compileSimAndStart(unit, target_platform=VirtualHlsPlatform())


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsSynthesisChecksTC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(HlsSynthesisChecksTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
