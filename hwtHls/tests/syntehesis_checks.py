#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.examples.crc import CrcCombHls
from hwtHls.examples.pid import PidControllerHls
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scheduler.scheduler import TimeConstraintError
from hwtHls.tests.ifstm import SimpleIfStatementHls
from hwtLib.logic.crcPoly import CRC_32


class HlsSynthesisChecksTC(SimTestCase):

    def test_PidControllerHls(self):
        self._test(PidControllerHls())

    def test_PidControllerHls_unschedulable(self):
        u = PidControllerHls()
        u.CLK_FREQ = int(150e6)
        with self.assertRaises(TimeConstraintError):
            self._test(u)

    def test_SimpleIfStatementHls(self):
        self._test(SimpleIfStatementHls())

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

    def _test(self, unit):
        self.compileSimAndStart(unit, target_platform=VirtualHlsPlatform())


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(HlsSynthesisChecksTC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsSynthesisChecksTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
