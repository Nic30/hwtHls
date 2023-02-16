#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from functools import reduce

from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.pyUtils.arrayQuery import grouper, balanced_reduce
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.hObjList import HObjList
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class HlsMAC_example(Unit):

    def _config(self):
        self.CLK_FREQ = Param(int(20e6))
        self.INPUT_CNT = Param(4)
        self.DATA_WIDTH = Param(32)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn = HObjList(VectSignal(self.DATA_WIDTH, signed=False)
                       for _ in range(int(self.INPUT_CNT)))

        self.dataOut = VectSignal(self.DATA_WIDTH, signed=False)._m()

    def _impl(self):
        hls = HlsScope(self)
        # inputs has to be readed to enter hls scope
        # (without read() operation will not be schedueled by HLS
        #  instead they will be directly synthesized)
        # [NOTE] number of input is hardcoded by this
        a, b, c, d = [hls.read(intf).data for intf in self.dataIn]
        # depending on target platform this expresion
        # can be mapped to DPS, LUT, etc...
        # no constrains are specified => default strategy is
        # to achieve zero delay and minimum latency, for this CLK_FREQ
        e = a * b + c * d
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(e, self.dataOut),
            ),
            self._name)
        )
        hls.compile()



class HlsMAC_example2(HlsMAC_example):

    def _config(self):
        super(HlsMAC_example2, self)._config()
        self.INPUT_CNT = 16

    def _impl(self):
        hls = HlsScope(self)
        # inputs has to be readed to enter hls scope
        # (without read() operation will not be schedueled by HLS
        #  instead they will be directly synthesized)
        # [NOTE] number of input is hardcoded by this
        dataIn = [hls.read(intf) for intf in self.dataIn]
        # depending on target platform this expresion
        # can be mapped to DPS, LUT, etc...
        # no constrains are specified => default strategy is
        # to achieve zero delay and minimum latency, for this CLK_FREQ
        muls = []
        for a, b in grouper(2, dataIn):
            muls.append(a.data * b.data)

        adds = balanced_reduce(muls, lambda a, b: a + b)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                      *dataIn,
                      hls.write(adds, self.dataOut),
            ),
            self._name)
        )
        hls.compile()



class HlsMAC_example_handshake(HlsMAC_example2):

    def _config(self):
        super(HlsMAC_example_handshake, self)._config()
        self.CLK_FREQ = int(20e6)
        self.INPUT_CNT = 4

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn = HObjList(
            HsStructIntf()
            for _ in range(int(self.INPUT_CNT))
        )
        self.dataOut = HsStructIntf()._m()
        for d in self.dataIn + [self.dataOut, ]:
            d.T = Bits(self.DATA_WIDTH, signed=False)


class HlsMAC_example_TC(SimTestCase):

    def test_simple(self, u_cls=HlsMAC_example):
        u = u_cls()
        u.INPUT_CNT = 4
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        for intf, d in zip(u.dataIn, [3, 4, 5, 6]):
            intf._ag.data.append(d)

        self.runSim(int(4 * freq_to_period(u.CLK_FREQ)))

        self.assertValEqual(u.dataOut._ag.data[-1],
                            (3 * 4) + (5 * 6))

    def test_simple_handshaked(self):
        self.test_simple(u_cls=HlsMAC_example_handshake)

    def test_2simple(self):
        self.test_simple(u_cls=HlsMAC_example2)

    def test_2_16simple(self, u_cls=HlsMAC_example2):
        u = u_cls()
        #u.INPUT_CNT = 16
        # u.CLK_FREQ = int(40e6)
        u.INPUT_CNT = 16
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        inputs = [i for i in range(u.INPUT_CNT)]
        for intf, d in zip(u.dataIn, inputs):
            intf._ag.data.append(d)

        self.runSim(int(8 * freq_to_period(u.CLK_FREQ)))

        res = u.dataOut._ag.data[-1]
        expectedRes = reduce(lambda a, b: a + b,
                             map(lambda x: x[0] * x[1],
                                 grouper(2,
                                         inputs)))
        self.assertValEqual(res, expectedRes)

    def test_2_16simple_handshaked(self):
        self.test_2_16simple(HlsMAC_example_handshake)


if __name__ == "__main__":
    import unittest
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = HlsMAC_example_handshake()
    u.DATA_WIDTH = 32
    u.CLK_FREQ = int(40e6)
    u.INPUT_CNT = 16
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    suite = unittest.TestSuite()
    #suite.addTest(HlsMAC_example_TC('test_2_16simple_handshaked'))
    suite.addTest(unittest.makeSuite(HlsMAC_example_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
