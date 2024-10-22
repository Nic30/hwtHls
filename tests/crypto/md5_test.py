#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.crypto.md5 import md5_accumulator_t, md5ProcessChunk, \
    md5BuildDigist


class Md5(HwModule):

    def hwConfig(self):
        self.DATA_WIDTH = HwParam(32 * 16)
        self.FREQ = HwParam(int(100e6))

    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        assert self.DATA_WIDTH > 0, self.DATA_WIDTH

        self.din = HwIODataRdVld()
        self.din.DATA_WIDTH = self.DATA_WIDTH

        self.dout = HwIODataRdVld()._m()
        self.dout.DATA_WIDTH = 4 * 32

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            chunk = hls.read(self.din)
            acc = md5_accumulator_t.from_py({"a0": 0, "b0": 0, "c0":0, "d0":0})
            PyBytecodeInline(md5ProcessChunk)(chunk, acc)
            hls.write(PyBytecodeInline(md5BuildDigist)(acc), self.dout)

    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class Md5_TC(SimTestCase):

    def test_fullUnroll(self):
        u = Md5()
        self.compileSimAndStart(u, target_platform=Artix7Medium())
        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        s = (''.join(f'{i%16:x}' for i in range(64))).encode()
        u.din._ag.data.append(int.from_bytes(s, byteorder="little"))

        self.runSim(100 * int(CLK_PERIOD))
        h = hashlib.md5(s)
        hAsInt = int.from_bytes(h.digest(), byteorder="little")

        self.assertValSequenceEqual(u.dout._ag.data, [hAsInt])


if __name__ == "__main__":
    import unittest
    import sys
    sys.setrecursionlimit(int(1e6))
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    import cProfile
    pr = cProfile.Profile()
    pr.enable()
    u = Md5()
    try:
        print(to_rtl_str(u, target_platform=Artix7Medium())) # debugFilter=HlsDebugBundle.ALL_RELIABLE
    finally:
        pr.disable()
        pr.dump_stats('profile.prof')

    #suite = unittest.TestSuite()
    ## suite.addTest(Md5_TC('test_split'))
    #runner = unittest.TextTestRunner(verbosity=3)
    #runner.run(suite)
