#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.simulator.simTestCase import SimTestCase
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline, \
    PyBytecodeSkipPass
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask
from tests.bitOpt.divNonRestoring import divNonRestoring
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class DivNonRestoring(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(4)
        self.FREQ = HwParam(int(20e6))
        self.UNROLL_FACTOR = HwParam(1)
        self.MAIN_FN_META = HwParam(None)

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.data_in = HwIOStructRdVld()
        t = HBits(self.DATA_WIDTH)
        self.data_in.T = HStruct(
            (t, "dividend"),
            (t, "divisor"),
            (BIT, "signed"),
        )
        self.data_out = HwIOStructRdVld()._m()
        self.data_out.T = HStruct(
            (t, "quotient"),
            (t, "remainder")
        )

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        self.MAIN_FN_META
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
        [(1, 1, 0), (2, 2, 0), (4, 2, 0), ],  # (13, 3, 0), (3, 15, 0), (9, 3, 0)],  # dividend, divisor, isSigned
        [(1, 0), (1, 0), (2, 0), ],  # (4, 1), (0, 3), (3, 0)],  # quotient, remainder
    ]

    def test_div_py(self):
        T = HBits(4)
        for (dividend, divisor, isSigned), (quotient, remainder) in zip(self.GOLDEN_DATA[0], self.GOLDEN_DATA[1]):
            _dividend = T.from_py(dividend)
            _divisor = T.from_py(divisor)
            _isSigned = BIT.from_py(isSigned)
            _quotient, _remainder = divNonRestoring(_dividend, _divisor, _isSigned, 1)
            self.assertValSequenceEqual([_quotient, _remainder], (quotient, remainder),
                                        msg=((dividend, "//", divisor, "signed?:", isSigned), (quotient, "rem:", remainder)))

    def test_div(self, MAIN_FN_META=None, runTestAfterEachPass=False):
        dut = DivNonRestoring()
        dut.DATA_WIDTH = 3
        dut.MAIN_FN_META = MAIN_FN_META

        def prepareDataInFn():
            DW = dut.DATA_WIDTH
            T = HBits(DW)
            dataIn = []
            for (dividend, divisor, isSigned) in self.GOLDEN_DATA[0]:
                _dividend = T.from_py(dividend)
                _divisor = T.from_py(divisor)
                _isSigned = BIT.from_py(isSigned)
                dataIn.append(Concat(_isSigned, _divisor, _dividend))
            return dataIn

        def checkDataOutFn(dataOut):
            DW = dut.DATA_WIDTH
            dataOutRef = []
            for (quotient, remainder) in self.GOLDEN_DATA[1]:
                dataOutRef.append((remainder << DW) | quotient)

            self.assertValSequenceEqual(dataOut, dataOutRef, "[%s] != [%s]" % (
                ", ".join("(q:%d, r:%d)" % (int(i) & mask(DW), int(i) >> DW) if i._is_full_valid() else repr(i) for i in dataOut),
                ", ".join("(q:%d, r:%d)" % (q, r) for q, r in self.GOLDEN_DATA[1])
            ))

        self.compileSimAndStart(dut,
                                target_platform=TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
                                    prepareDataInFn, checkDataOutFn, None, #debugFilter=HlsDebugBundle.ALL_RELIABLE,
                                    noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
                                    runTestAfterEachPass=runTestAfterEachPass
                                    ))
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.data_in._ag.data.extend(self.GOLDEN_DATA[0])
        self.runSim((len(dut.data_in._ag.data) * dut.DATA_WIDTH + 10) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.data_out._ag.data,
                                    self.GOLDEN_DATA[1])
        self.rtl_simulator_cls = None

    def test_div_no_SlicesToIndependentVariablesPass(self):
        self.test_div(MAIN_FN_META=PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass"]), runTestAfterEachPass=False)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # # from hwtHls.platform.xilinx.artix7 import Artix7Fast
    # m = DivNonRestoring()
    # # m.DATA_WIDTH = 8
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([DivNonRestoring_TC('test_div_py')])
    suite = testLoader.loadTestsFromTestCase(DivNonRestoring_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
