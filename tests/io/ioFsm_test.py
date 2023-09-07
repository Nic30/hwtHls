#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Type, List

from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.ioFsm import WriteFsm0Send123, WriteFsm0WhileTrue123, WriteFsm1WhileTrue123hs, WriteFsm1Send123hs, \
    ReadFsm0WhileTrueRead3TimesWriteConcat, ReadFsm0Read3TimesWriteConcat, ReadFsm1Read3TimesWriteConcatHs, \
    ReadFsm1WhileTrueRead3TimesWriteConcatHs


class IoFsm_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsAstTrivial_TC._test_no_comb_loops(self)

    def _test_Write(self, cls: Type[Unit], ref: List[Optional[int]], CLK):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)

    def test_WriteFsm0WhileTrue123(self, cls=WriteFsm0WhileTrue123, ref=[1, 2, 3, 1, 2, 3, 1], CLK=8):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsm0Send123(self, cls=WriteFsm0Send123, ref=[1, 2, 3, None, None, None, None], CLK=8):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsm1WhileTrue123hs(self):
        self.test_WriteFsm0WhileTrue123(cls=WriteFsm1WhileTrue123hs)

    def test_WriteFsm1Send123hs(self):
        self.test_WriteFsm0Send123(cls=WriteFsm1Send123hs, ref=[1, 2, 3])

    def make3(self, v0, v1, v2):
        u = self.u
        return (v2 << 2 * u.DATA_WIDTH) | (v1 << u.DATA_WIDTH) | v0

    def test_ReadFsm0WhileTrueRead3TimesWriteConcat(self):
        u = ReadFsm0WhileTrueRead3TimesWriteConcat()
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

    def test_ReadFsm0Read3TimesWriteConcat(self):
        u = ReadFsm0Read3TimesWriteConcat()

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

    def test_ReadFsm1WhileTrueRead3TimesWriteConcatHs(self):
        u = ReadFsm1WhileTrueRead3TimesWriteConcatHs()
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

    def test_ReadFsm1Read3TimesWriteConcatHs(self):
        u = ReadFsm1Read3TimesWriteConcatHs()

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
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    #
    # u = WriteFsm1()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IoFsm_TC("test_WriteFsm1")])
    suite = testLoader.loadTestsFromTestCase(IoFsm_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
