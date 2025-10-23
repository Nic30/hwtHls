#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from itertools import zip_longest
from math import isnan
from math import nan, inf
import struct
import sys
from typing import Callable, List, Tuple

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.math.fp.fpadd import IEEE754FpAdd
from tests.math.fp.fpcmp_test import IEEE754FpComparator
from tests.math.fp.fptypes import IEEE754Fp64, IEEE754Fp, IEEE754Fp16
from tests.math.fp.fptypes_test import int64reinterpretToFloat, \
    fpPyDictToFpTuple, fpConstToFpTuple
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class _Test_IEEE754FpAlu(HwModule):

    def hwConfig(self) -> None:
        self.T = HwParam(IEEE754Fp64)
        self.CLK_FREQ = HwParam(int(20e6))
        self.FP_FUNCTION = HwParam(IEEE754FpAdd)

    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.a = HwIOStructRdVld()
        self.b = HwIOStructRdVld()
        self.res = HwIOStructRdVld()._m()
        self.a.T = self.b.T = self.res.T = self.T

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            a = hls.read(self.a).data
            b = hls.read(self.b).data
            res = PyBytecodeInline(self.FP_FUNCTION)(a, b)
            hls.write(res, self.res, mayBecomeFlushable=False)

    def hwImpl(self) -> None:
        IEEE754FpComparator.hwImpl(self)


class IEEE754FpAdd_TC(SimTestCase):
    TEST_DATA = [
        (1.0, 1.0),
        (1.0, -1.0),
        (1.125, 1.0),
        (1.25, 1.0),
        (1.0, 2.0),
        (1.0, 2.25),
        (nan, 1.0),
        (inf, 1.0),
        (-inf, 1.0),
        (inf, nan),
        (sys.float_info.max, 1.0),
        (sys.float_info.epsilon, sys.float_info.epsilon),
    ]

    TEST_DATA_FORMATED = [
       (IEEE754Fp64.from_py(aF), IEEE754Fp64.from_py(bF)) for aF, bF in TEST_DATA
    ]
    # :note: staticmethod must be used otherwise function is bounded as instance method to this class
    #  and it add "self" parameter
    FP_FUNCTION = staticmethod(IEEE754FpAdd)

    FP_FUNCTION_HAS_SIM_ARG = True

    @staticmethod
    def model(a: float, b: float):
        return a + b

    def FP_OPERATOR_FN(self, a: IEEE754Fp64, b: IEEE754Fp64):
        return self.model(a, b)

    @staticmethod
    def prepareTestDataAndRef(TEST_DATA_FORMATED: List[Tuple[IEEE754Fp64, IEEE754Fp64]], model: Callable[[float, float], float]):
        aDataIn = []
        bDataIn = []
        resRef = []
        for (a, b) in TEST_DATA_FORMATED:
            aDataIn.append(a)
            bDataIn.append(b)
            _a = a.to_py()
            _b = b.to_py()
            _resRef = float(model(_a, _b))
            resRef.append(_resRef)
        return aDataIn, bDataIn, resRef

    @staticmethod
    def getPrepareDataFnForIRSim(TEST_DATA: List[Tuple[float, float]], fpTy:IEEE754Fp):

        def prepareDataInFn():
            aDataIn = []
            bDataIn = []
            t = HBits(fpTy.bit_length())
            for a, b in TEST_DATA:
                aDataIn.append(t.from_py(struct.pack("d", a)))
                bDataIn.append(t.from_py(struct.pack("d", b)))

            return aDataIn, bDataIn

        return prepareDataInFn

    def test_py(self):
        assert sys.float_info.mant_dig == 53
        fpFn = self.FP_FUNCTION
        t: IEEE754Fp = self.TEST_DATA_FORMATED[0][0]._dtype
        for (a, b), (aRaw, bRaw) in zip(self.TEST_DATA_FORMATED, self.TEST_DATA):
            resRef = self.model(aRaw, bRaw)
            if self.FP_FUNCTION_HAS_SIM_ARG:
                res = fpFn(a, b, isSim=True)
            else:
                res = fpFn(a, b)

            # print(aRaw, "+", bRaw, "=", t.to_py(res), "(", resRef, ")")
            msg = ('got', res.to_py(), "expected", resRef,
                   "a", aRaw, "b", bRaw, "a", a, "b", b,
                   )
            self.assertEqual(fpConstToFpTuple(res), fpConstToFpTuple(t.from_py(resRef)),
                             msg=msg)

    def _test_ir_mir_rtl(self, dut: _Test_IEEE754FpAlu):
        assert sys.float_info.mant_dig == 53
        prepareDataInFn = self.getPrepareDataFnForIRSim(self.TEST_DATA, dut.T)
        aDataIn, bDataIn, resRef = self.prepareTestDataAndRef(self.TEST_DATA_FORMATED, self.model)

        def checkDataOutFn(dataOut):
            assert dataOut
            T = dut.T
            for i, (ref, d) in enumerate(zip_longest(resRef, dataOut)):
                self.assertIsNotNone(ref, ("Output data contains more data then was expected", dataOut[len(resRef):]))
                self.assertIsNotNone(d, ("Output data is missing data", resRef[len(dataOut):]))
                v = int64reinterpretToFloat(int(d))
                if isnan(ref):
                    self.assertTrue(isnan(v), (v, ref))
                else:
                    self.assertEqual(v, ref, (i, T.from_py(v), T.from_py(ref)))

        platform = TestLlvmIrAndMirPlatform.forSimpleDataInDataOutHwModule(
            prepareDataInFn, checkDataOutFn, None,
            topToRunTestsOn=dut,
            inputCnt=2,
            # noOptIrTest=TestLlvmIrAndMirPlatform.TEST_NO_OPT_IR,
            # runTestAfterEachPass=True,
            # debugFilter=HlsDebugBundle.ALL_RELIABLE,
        )
        installMathLibComponentGenerators(platform)
        self.compileSimAndStart(dut, target_platform=platform)

        dut.a._ag.data.extend(aDataIn)
        dut.b._ag.data.extend(bDataIn)
        dut.a._ag.presetBeforeClk = True
        dut.b._ag.presetBeforeClk = True

        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        self.runSim((len(self.TEST_DATA_FORMATED) + 1) * int(CLK_PERIOD))

        def formatFp64(d):
            "d in format (mantissa, exponent, sign)"
            mantissa, exponent, sign = d
            assert sign._dtype.bit_length() == 1
            return (int(sign), int(exponent), int(mantissa))

        def formatFloat(d: float):
            return fpPyDictToFpTuple(HStructConstBase.to_py(IEEE754Fp64.from_py(d)))

        res = [formatFp64(d) for d in dut.res._ag.data]
        resRefAsHwFp = [formatFloat(d) for d in resRef]

        self.assertSequenceEqual(res, resRefAsHwFp,
                                 [(a.to_py(), b.to_py(), a, b)
                                  for a, b in self.TEST_DATA_FORMATED])
        self.rtl_simulator_cls = None

    def test_ir_mir_rtl(self):
        dut = _Test_IEEE754FpAlu()
        dut.FP_FUNCTION = self.FP_FUNCTION
        dut.CLK_FREQ = int(100e3)
        self._test_ir_mir_rtl(dut)

    def test_op_ir_mir_rtl(self):
        # test that component generator instantiates fadd correctly
        dut = _Test_IEEE754FpAlu()
        dut.FP_FUNCTION = self.FP_OPERATOR_FN
        dut.CLK_FREQ = int(100e3)
        self._test_ir_mir_rtl(dut)


class IEEE754FpSub_TC(IEEE754FpAdd_TC):

    # :note: this should also test OP_FNEG
    @staticmethod
    def model(a: float, b: float):
        return a - b

    FP_OPERATOR_FN = staticmethod(model)

    def test_py(self):
        pass  # dissable this test because there is no  FP_FUNCTION like IEEE754FpSub and operation is lowered to IEEE754FpAdd

    def test_ir_mir_rtl(self):
        pass  # :see: IEEE754FpSub_TC.test_py


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast

    m = _Test_IEEE754FpAlu()
    m.CLK_FREQ = int(100e3)
    m.T = IEEE754Fp16
    # def FP_OPERATOR_FN(a, b):
    #    T = a._dtype
    #    return (a._auto_cast(HFloatTmp) + b._auto_cast(HFloatTmp))._auto_cast(T)
    # m.FP_FUNCTION = FP_OPERATOR_FN
    m.FP_FUNCTION = lambda a, b: a - b
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL, ]
    )
    installMathLibComponentGenerators(p)
    #print(to_rtl_str(m, target_platform=p))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpAdd_TC('test_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpSub_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
