#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axis import axis_recieve_bytes
from hwtSimApi.constants import CLK_PERIOD
from tests.io.amba.axiStream.axisWriteByte import AxiSWriteByte


class AxiSWriteByteTC(SimTestCase):

    def _test_AxiSWriteByte(self, DATA_WIDTH:int, cls=AxiSWriteByte, N=3):
        u = cls()
        u.DATA_WIDTH = DATA_WIDTH
        if DATA_WIDTH != 8:
            u.USE_STRB = True
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        
        ref = [[1, ] for _ in range(N)]

        t = CLK_PERIOD * (N + 1) 
        self.runSim(t)

        for _ref  in ref:
            o, f = axis_recieve_bytes(u.dataOut)
            self.assertEqual(o, 0)
            self.assertValSequenceEqual(f, _ref)

        self.assertEmpty(u.dataOut._ag.data)
    
    def test_AxiSWriteByte_8b(self):
        self._test_AxiSWriteByte(8, cls=AxiSWriteByte)
        
    def test_AxiSWriteByte_32b(self):
        self._test_AxiSWriteByte(32, cls=AxiSWriteByte)


if __name__ == '__main__':

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AxiSWriteByteTC("test_AxiSParseStructManyInts1_48b")])
    suite = testLoader.loadTestsFromTestCase(AxiSWriteByteTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
