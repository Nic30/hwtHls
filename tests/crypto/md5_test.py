#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.crypto.md5 import md5_accumulator_t, md5ProcessChunk, \
    md5BuildDigist


class Md5(Unit):

    def _config(self):
        self.DATA_WIDTH = Param(32 * 16)
        self.FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        assert self.DATA_WIDTH > 0, self.DATA_WIDTH

        self.din = Handshaked()
        self.din.DATA_WIDTH = self.DATA_WIDTH

        self.dout = Handshaked()._m()
        self.dout.DATA_WIDTH = 4 * 32

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            chunk = hls.read(self.din)
            acc = md5_accumulator_t.from_py({"a0": 0, "b0": 0, "c0":0, "d0":0})
            PyBytecodeInline(md5ProcessChunk)(chunk, acc)
            hls.write(PyBytecodeInline(md5BuildDigist)(acc), self.dout)

    def _impl(self):
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
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    import cProfile
    pr = cProfile.Profile()
    pr.enable()
    u = Md5()
    #
    print(to_rtl_str(u, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    pr.disable()
    pr.dump_stats('profile.prof')

    #suite = unittest.TestSuite()
    ## suite.addTest(Md5_TC('test_split'))
    #runner = unittest.TextTestRunner(verbosity=3)
    #runner.run(suite)
