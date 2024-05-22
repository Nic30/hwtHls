#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Type, List

from hwt.simulator.simTestCase import SimTestCase
from hwt.hwModule import HwModule
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.io.ioFsm import WriteFsm0Send123, WriteFsm0WhileTrue123, WriteFsm1WhileTrue123hs, WriteFsm1Send123hs, \
    ReadFsm0WhileTrueRead3TimesWriteConcat, ReadFsm0Read3TimesWriteConcat, ReadFsm1Read3TimesWriteConcatHs, \
    ReadFsm1WhileTrueRead3TimesWriteConcatHs
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC


class IoFsm_TC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def _test_Write(self, cls: Type[HwModule], ref: List[Optional[int]], CLK):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, ref)

    def test_WriteFsm0WhileTrue123(self, cls=WriteFsm0WhileTrue123, ref=[1, 2, 3, 1, 2, 3, 1], CLK=8):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsm0Send123(self, cls=WriteFsm0Send123, ref=[1, 2, 3, None, None, None, None], CLK=8):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsm1WhileTrue123hs(self):
        self.test_WriteFsm0WhileTrue123(cls=WriteFsm1WhileTrue123hs)

    def test_WriteFsm1Send123hs(self):
        self.test_WriteFsm0Send123(cls=WriteFsm1Send123hs, ref=[1, 2, 3])

    def make3(self, v0, v1, v2):
        dut = self.dut
        return (v2 << 2 * dut.DATA_WIDTH) | (v1 << dut.DATA_WIDTH) | v0

    def test_ReadFsm0WhileTrueRead3TimesWriteConcat(self):
        dut = ReadFsm0WhileTrueRead3TimesWriteConcat()
        CLK = 8

        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.i._ag.data.extend(i + 1 for i in range(CLK))

        ref = [
            None, None, self.make3(1, 2, 3),
            None, None, self.make3(4, 5, 6),
            None,
        ]

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, ref)

    def test_ReadFsm0Read3TimesWriteConcat(self):
        dut = ReadFsm0Read3TimesWriteConcat()

        CLK = 8

        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.i._ag.data.extend(i + 1 for i in range(CLK))
        ref = [
            None, None, self.make3(1, 2, 3),
            None, None, None,
            None
        ]
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, ref)

    def test_ReadFsm1WhileTrueRead3TimesWriteConcatHs(self):
        dut = ReadFsm1WhileTrueRead3TimesWriteConcatHs()
        CLK = 8
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dut.i._ag.data.extend(i + 1 for i in range(CLK))
        ref = [
            self.make3(1, 2, 3),
            self.make3(4, 5, 6),
        ]
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, ref)

    def test_ReadFsm1Read3TimesWriteConcatHs(self):
        dut = ReadFsm1Read3TimesWriteConcatHs()

        CLK = 8
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        ref = [
            self.make3(1, 2, 3),
        ]
        dut.i._ag.data.extend(i + 1 for i in range(CLK))

        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, ref)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    #
    # m = WriteFsm1()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IoFsm_TC("test_WriteFsm1")])
    suite = testLoader.loadTestsFromTestCase(IoFsm_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
