#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from functools import reduce

from hwt.hObjList import HObjList
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.arrayQuery import grouper, balanced_reduce
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class HlsMAC_example(HwModule):

    @override
    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(20e6))
        self.INPUT_CNT = HwParam(4)
        self.DATA_WIDTH = HwParam(32)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn = HObjList(HwIOVectSignal(self.DATA_WIDTH, signed=False)
                       for _ in range(int(self.INPUT_CNT)))

        self.dataOut = HwIOVectSignal(self.DATA_WIDTH, signed=False)._m()

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        # inputs has to be readed to enter hls scope
        # (without read() operation will not be schedueled by HLS
        #  instead they will be directly synthesized)
        # [NOTE] number of input is hardcoded by this
        a, b, c, d = [hls.read(hwIO).data for hwIO in self.dataIn]
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

    @override
    def hwConfig(self):
        super(HlsMAC_example2, self).hwConfig()
        self.INPUT_CNT = 16

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        # inputs has to be readed to enter hls scope
        # (without read() operation will not be schedueled by HLS
        #  instead they will be directly synthesized)
        # [NOTE] number of input is hardcoded by this
        dataIn = [hls.read(hwIO) for hwIO in self.dataIn]
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

    @override
    def hwConfig(self):
        super(HlsMAC_example_handshake, self).hwConfig()
        self.CLK_FREQ = int(20e6)
        self.INPUT_CNT = 4

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        assert int(self.INPUT_CNT) % 2 == 0

        self.dataIn = HObjList(
            HwIOStructRdVld()
            for _ in range(int(self.INPUT_CNT))
        )
        self.dataOut = HwIOStructRdVld()._m()
        for d in self.dataIn + [self.dataOut, ]:
            d.T = HBits(self.DATA_WIDTH, signed=False)


class HlsMAC_example_TC(SimTestCase):

    def test_simple(self, moduleCls=HlsMAC_example):
        dut = moduleCls()
        dut.INPUT_CNT = 4
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        for hwIO, d in zip(dut.dataIn, [3, 4, 5, 6]):
            hwIO._ag.data.append(d)

        self.runSim(int(4 * freq_to_period(dut.CLK_FREQ)))

        self.assertValEqual(dut.dataOut._ag.data[-1],
                            (3 * 4) + (5 * 6))

    def test_simple_handshaked(self):
        self.test_simple(moduleCls=HlsMAC_example_handshake)

    def test_2simple(self):
        self.test_simple(moduleCls=HlsMAC_example2)

    def test_2_16simple(self, moduleCls=HlsMAC_example2):
        dut = moduleCls()
        #dut.INPUT_CNT = 16
        # dut.CLK_FREQ = int(40e6)
        dut.INPUT_CNT = 16
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        inputs = [i for i in range(dut.INPUT_CNT)]
        for hwIO, d in zip(dut.dataIn, inputs):
            hwIO._ag.data.append(d)

        self.runSim(int(8 * freq_to_period(dut.CLK_FREQ)))

        res = dut.dataOut._ag.data[-1]
        expectedRes = reduce(lambda a, b: a + b,
                             map(lambda x: x[0] * x[1],
                                 grouper(2,
                                         inputs)))
        self.assertValEqual(res, expectedRes)

    def test_2_16simple_handshaked(self):
        self.test_2_16simple(HlsMAC_example_handshake)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    m = HlsMAC_example_handshake()
    m.DATA_WIDTH = 32
    m.CLK_FREQ = int(40e6)
    m.INPUT_CNT = 16
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsMAC_example_TC('test_2_16simple_handshaked')])
    suite = testLoader.loadTestsFromTestCase(HlsMAC_example_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
