#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from hwtLib.avalon.st import AvalonST
from hwt.pyUtils.typingFuture import override
from tests.io.amba.axi4Stream.axi4sParseLinear import Axi4SParseStructManyInts0, \
    Axi4SParseStructManyInts1, Axi4SParse2fields
from hwtHls.scope import HlsScope
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.avalon.avalonSt.proxy import IoProxyAvalonSt
from tests.io.amba.axi4Stream.axi4sParseLinear_test import Axi4SParseLinearTC
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtLib.avalon.stSimFrameUtils import AvalonStSimFrameUtils


class AvalonStStructManyInts0(Axi4SParseStructManyInts0):
    AXI_CLS = AvalonST

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        i = IoProxyAvalonSt(hls, self.i)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, i))
        hls.compile()


class AvalonStParseStructManyInts1(Axi4SParseStructManyInts1):
    AXI_CLS = AvalonST

    @override
    def hwImpl(self) -> None:
        AvalonStStructManyInts0.hwImpl(self)


class AvalonStParse2fields(Axi4SParse2fields):
    AXI_CLS = AvalonST

    @override
    def hwImpl(self) -> None:
        AvalonStStructManyInts0.hwImpl(self)


class AvalonStParseLinearTC(Axi4SParseLinearTC):

    def _test_parse(self, DATA_WIDTH:int, cls=Axi4SParseStructManyInts0, N=3, T=structManyInts):
        cls = {
            Axi4SParseStructManyInts0: AvalonStStructManyInts0,
            Axi4SParseStructManyInts1: AvalonStParseStructManyInts1,
            Axi4SParse2fields: AvalonStParse2fields,
        }[cls]
        dut = cls()
        dut.DATA_WIDTH = DATA_WIDTH
        self._run_test_parse(dut, AvalonStSimFrameUtils, N, T)


if __name__ == "__main__":
    import unittest
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = AvalonStStructManyInts0()
    m.DATA_WIDTH = 512
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    p._debugExpandCompositeNodes = True
    # print(to_rtl_str(m, target_platform=p))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AvalonStParseLinearTC("test_Axi4SParseStructManyInts0_8b")])
    suite = testLoader.loadTestsFromTestCase(AvalonStParseLinearTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
