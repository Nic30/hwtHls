#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.bitOpt.divNonRestoring import divNonRestoring
from hwtHls.frontend.pyBytecode import hlsBytecode


class DivNonRestoring(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(4)
        self.FREQ = Param(int(50e6))
        self.UNROLL_FACTOR = Param(1)

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.data_in = HsStructIntf()
        t = Bits(self.DATA_WIDTH)
        self.data_in.T = HStruct(
            (t, "dividend"),
            (t, "divisor"),
            (BIT, "signed"),
        )
        self.data_out = HsStructIntf()._m()
        self.data_out.T = HStruct(
            (t, "quotient"),
            (t, "remainder")
        )

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            inp = hls.read(self.data_in)
            res = PyBytecodeInline(divNonRestoring)(inp.dividend, inp.divisor, inp.signed, self.UNROLL_FACTOR)
            resTmp = self.data_out.T.from_py(None)
            resTmp.quotient(res[0])
            resTmp.remainder(res[1])
            hls.write(resTmp, self.data_out)

    def _impl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


class DivNonRestoring_TC(SimTestCase):

    def test_div(self):
        u = DivNonRestoring()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        u.data_in._ag.data.extend([(1, 1, 0), (2, 2, 0), (4, 2, 0), (13, 3, 0), (3, 15, 0)])
        self.runSim((len(u.data_in._ag.data) * u.DATA_WIDTH + 10) * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.data_out._ag.data, [(1, 0), (1, 0), (1, 0), (2, 0), (4, 1), (0, 3)])


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    u = DivNonRestoring()
    u.DATA_WIDTH = 4

    print(to_rtl_str(u, target_platform=Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(RiscvExtM_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(DivNonRestoring_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
