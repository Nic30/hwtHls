#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask
from tests.bitOpt.divNonRestoring import divNonRestoring
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class DivNonRestoring(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(4)
        self.FREQ = Param(int(20e6))
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
        hls.addThread(mainThread)
        hls.compile()


class DivNonRestoring_TC(SimTestCase):
    GOLDEN_DATA = [
        [(1, 1, 0), (2, 2, 0), (4, 2, 0),], #(13, 3, 0), (3, 15, 0), (9, 3, 0)],  # dividend, divisor, isSigned
        [(1, 0), (1, 0), (2, 0), ], #(4, 1), (0, 3), (3, 0)],  # quotient, remainder
    ]

    def test_div_py(self):
        T = Bits(4)
        for (dividend, divisor, isSigned), (quotient, remainder) in zip(self.GOLDEN_DATA[0], self.GOLDEN_DATA[1]):
            _dividend = T.from_py(dividend)
            _divisor = T.from_py(divisor)
            _isSigned = BIT.from_py(isSigned)
            _quotient, _remainder = divNonRestoring(_dividend, _divisor, _isSigned, 1)
            self.assertValSequenceEqual([_quotient, _remainder], (quotient, remainder),
                                        msg=((dividend, "//", divisor, "signed?:", isSigned), (quotient, "rem:", remainder)))

    def test_div(self):
        u = DivNonRestoring()
        u.DATA_WIDTH = 3

        def prepareDataInFn():
            DW = u.DATA_WIDTH
            T = Bits(DW)
            dataIn = []
            for (dividend, divisor, isSigned) in self.GOLDEN_DATA[0]:
                _dividend = T.from_py(dividend)
                _divisor = T.from_py(divisor)
                _isSigned = BIT.from_py(isSigned)
                dataIn.append(Concat(_isSigned, _divisor, _dividend))
            return dataIn

        def checkDataOutFn(dataOut):
            DW = u.DATA_WIDTH
            dataOutRef = []
            for (quotient, remainder) in self.GOLDEN_DATA[1]:
                dataOutRef.append((remainder << DW) | quotient)

            self.assertValSequenceEqual(dataOut, dataOutRef, "[%s] != [%s]" % (
                ", ".join("(q:%d, r:%d)" % (int(i) & mask(DW), int(i) >> DW) if i._is_full_valid() else repr(i) for i in dataOut),
                ", ".join("(q:%d, r:%d)" % (q, r) for q,r in self.GOLDEN_DATA[1])
            ))

        self.compileSimAndStart(u,
                                target_platform=TestLlvmIrAndMirPlatform.forSimpleDataInDataOutUnit(
                                    prepareDataInFn, checkDataOutFn, None, debugFilter=HlsDebugBundle.ALL_RELIABLE,
                                    noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
                                    runTestAfterEachPass=True))
        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        u.data_in._ag.data.extend(self.GOLDEN_DATA[0])
        self.runSim((len(u.data_in._ag.data) * u.DATA_WIDTH + 10) * int(CLK_PERIOD))

        self.assertValSequenceEqual(u.data_out._ag.data,
                                    self.GOLDEN_DATA[1])
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    #from hwt.synthesizer.utils import to_rtl_str
    #from hwtHls.platform.virtual import VirtualHlsPlatform
    ## from hwtHls.platform.xilinx.artix7 import Artix7Fast
    #u = DivNonRestoring()
    ## u.DATA_WIDTH = 8
    #print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([DivNonRestoring_TC('test_div_py')])
    suite = testLoader.loadTestsFromTestCase(DivNonRestoring_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
