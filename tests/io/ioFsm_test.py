#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Type, List

from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.ast.trivial_test import HlsStreamMachineTrivial_TC
from tests.io.ioFsm import WriteFsm0, WriteFsm0Once, WriteFsm1, WriteFsm1Once, \
    ReadFsm0, ReadFsm0Once, ReadFsm1, ReadFsm1Once


class IoFsm_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsStreamMachineTrivial_TC._test_no_comb_loops(self)

    def _test_Write(self, cls: Type[Unit], ref: List[Optional[int]], CLK):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)

    def test_WriteFsm0(self, cls=WriteFsm0, ref=[1, 2, 3, 1, 2, 3, 1], CLK=8):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsm0Once(self, cls=WriteFsm0Once, ref=[1, 2, 3, None, None, None, None], CLK=8):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsm1(self):
        self.test_WriteFsm0(cls=WriteFsm1)

    def test_WriteFsm1Once(self):
        self.test_WriteFsm0Once(cls=WriteFsm1Once, ref=[1, 2, 3])

    def make3(self, v0, v1, v2):
        u = self.u
        return (v2 << 2 * u.DATA_WIDTH) | (v1 << u.DATA_WIDTH) | v0
 
    def test_ReadFsm0(self):
        u = ReadFsm0()
        CLK = 8

        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.i._ag.data.extend(i + 1 for i in range(CLK))
        
        ref = [
            None, None, self.make3(1, 2, 3),
            None, None, self.make3(4, 5, 6),
            None,
        ]

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)
        
    def test_ReadFsm0Once(self):
        u = ReadFsm0Once()

        CLK = 8

        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.i._ag.data.extend(i + 1 for i in range(CLK))
        ref = [
            None, None, self.make3(1, 2, 3),
            None, None, None,
            None
        ]
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)

    def test_ReadFsm1(self):
        u = ReadFsm1()
        CLK = 8
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.i._ag.data.extend(i + 1 for i in range(CLK))
        ref = [
            self.make3(1, 2, 3),
            self.make3(4, 5, 6),
        ]
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)

    def test_ReadFsm1Once(self):
        u = ReadFsm1Once()

        CLK = 8
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        ref = [
            self.make3(1, 2, 3),
        ]
        u.i._ag.data.extend(i + 1 for i in range(CLK))

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)


if __name__ == "__main__":
    import unittest
    suite = unittest.TestSuite()
    #suite.addTest(IoFsm_TC('test_ReadFsm1Once'))
    suite.addTest(unittest.makeSuite(IoFsm_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
