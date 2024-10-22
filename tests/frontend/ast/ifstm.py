#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.examples.statements.ifStm import SimpleIfStatement
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import get_bit
from tests.baseSsaTest import BaseSsaTC


class HlsSimpleIfStatement(SimpleIfStatement):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        super(HlsSimpleIfStatement, self).hwDeclr()

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        r = hls.read
        a = r(self.a)
        b = r(self.b)
        c = r(self.c)
        tmp = hls.var("tmp", self.d._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                a, b, c,
                ast.If(a.data,
                    tmp(b.data),
                ).Elif(b.data,  # this elif is redundant
                    tmp(c.data),
                ).Else(
                    tmp(c.data)
                ),
                hls.write(tmp, self.d)
            ),
            self._name)
        )
        hls.compile()


class HlsSimpleIfStatement_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_simple(self):
        dut = HlsSimpleIfStatement()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        # test all combinations
        for i in range(1 << 3):
            dut.a._ag.data.append(get_bit(i, 0))
            dut.b._ag.data.append(get_bit(i, 1))
            dut.c._ag.data.append(get_bit(i, 2))

        def model(a, b, c):
            # b if a else c
            if a:
                return b
            elif b:
                return c
            else:
                return c

        d = [model(*args) for args in zip(dut.a._ag.data, dut.b._ag.data, dut.c._ag.data)]

        self.runSim(int((len(d) + 1) * freq_to_period(dut.CLK_FREQ)))

        self.assertValSequenceEqual(dut.d._ag.data, d)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = HlsSimpleIfStatement()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsSimpleIfStatement_TC('test_simple')])
    suite = testLoader.loadTestsFromTestCase(HlsSimpleIfStatement_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
