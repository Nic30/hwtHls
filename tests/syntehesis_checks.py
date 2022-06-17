#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.platform.xilinx.artix7 import Artix7Slow
from hwtLib.logic.crcPoly import CRC_32
from tests.frontend.ast.crc import CrcCombHls
from tests.frontend.ast.ifstm import HlsSimpleIfStatement
from tests.frontend.ast.pid import PidControllerHls


class HlsSynthesisChecksTC(SimTestCase):

    def test_PidControllerHls(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.compileSimAndStart(PidControllerHls(),
                                    target_platform=VirtualHlsPlatform(debugDir=tmp_dir))

    def test_PidControllerHlsDebug(self):
        self._test(PidControllerHls())

    def test_PidControllerHls_unschedulable(self):
        u = PidControllerHls()
        u.CLK_FREQ = int(150e6)
        with self.assertRaises(TimeConstraintError):
            self._test(u)

    def test_HlsSimpleIfStatement(self):
        self._test(HlsSimpleIfStatement())

    def test_CrcCombHls_crc32_128b_200MHz(self):
        u = CrcCombHls()
        u.setConfig(CRC_32)
        u.CLK_FREQ = int(200e6)
        u.DATA_WIDTH = 128
        self._test(u)

    def test_CrcCombHls_crc32_8b_100MHz(self):
        u = CrcCombHls()
        u.setConfig(CRC_32)
        u.CLK_FREQ = int(100e6)
        u.DATA_WIDTH = 8
        self._test(u)

    def test_CrcCombHls_crc32_128b_200MHz_XilinxAtrix7(self):
        u = CrcCombHls()
        u.setConfig(CRC_32)
        u.CLK_FREQ = int(200e6)
        u.DATA_WIDTH = 128
        self.compileSimAndStart(u, target_platform=Artix7Slow())

    def _test(self, unit):
        self.compileSimAndStart(unit, target_platform=VirtualHlsPlatform())


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(HlsSynthesisChecksTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsSynthesisChecksTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
