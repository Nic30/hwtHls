#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axi4s import axi4s_recieve_bytes
from hwtSimApi.constants import CLK_PERIOD
from tests.io.amba.axi4Stream.axi4sWriteByte import Axi4SWriteByte


class Axi4SWriteByteTC(SimTestCase):

    def _test_Axi4SWriteByte(self, DATA_WIDTH:int, cls=Axi4SWriteByte, N=3):
        dut = cls()
        dut.DATA_WIDTH = DATA_WIDTH
        if DATA_WIDTH != 8:
            dut.USE_STRB = True
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        ref = [[1, ] for _ in range(N)]

        t = CLK_PERIOD * (N + 1)
        self.runSim(t)

        for _ref  in ref:
            o, f = axi4s_recieve_bytes(dut.dataOut)
            self.assertEqual(o, 0)
            self.assertValSequenceEqual(f, _ref)

        self.assertEmpty(dut.dataOut._ag.data)

    def test_Axi4SWriteByte_8b(self):
        self._test_Axi4SWriteByte(8, cls=Axi4SWriteByte)

    def test_Axi4SWriteByte_32b(self):
        self._test_Axi4SWriteByte(32, cls=Axi4SWriteByte)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SWriteByteTC("test_Axi4SWriteByte_32b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SWriteByteTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
