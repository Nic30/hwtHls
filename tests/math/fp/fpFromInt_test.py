#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from itertools import zip_longest
from math import isnan

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import int64_t
from pyMathBitPrecise.bit_utils import mask, ValidityError, to_signed
from tests.math.fp._PassTestInjectorForFp import PassTestIoOutIEEE754Fp
from tests.math.fp.fpFromInt import IEEE754FpFromInt
from tests.math.fp.fptypes import IEEE754Fp64
from tests.passTestInjector import PassTestInjector
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule, \
    hlsModelProps
from tests.passTestIo import PassTestIoInPyInt


class IEEE754FpFromIntConventor(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(20e6))
        self.T_IN = HwParam(int64_t)
        self.T = HwParam(IEEE754Fp64)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.a = HwIOStructRdVld()
        self.a.T = self.T_IN
        self.res = HwIOStructRdVld()._m()
        self.res.T = self.T

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            a = hls.read(self.a).data
            res = PyBytecodeInline(IEEE754FpFromInt)(a, self.T)
            hls.write(res, self.res)

    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(a: int) -> float:
        return float(a)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class PassTestIoOutForIEEE754FpFromInt(PassTestIoOutIEEE754Fp):
    
    @override
    def checkForLlvmIr(self, dataSim:list[HBitsConst]):
        tc = self.passTests.tc
        T = self.fpTy
        resRef = self.dataRef

        for i, (din, ref, res) in enumerate(zip_longest(self.DATA_IN_FOR_DBG, resRef, dataSim)):
            ref: float
            res: HBitsConst
            assert not isnan(ref)
            tc.assertIsNotNone(ref, ("Output data contains more data then was expected", dataSim[len(resRef):]))
            tc.assertIsNotNone(res, ("Output data is missing data", i, resRef[len(dataSim):]))
            v = T.reinterpretRawIntToFloat(int(res))
            try:
                _resInt = "%016X" % int(res)
            except ValidityError:
                _resInt = None
            tc.assertEqual(v, ref, (self.name, i, "in:", din, _resInt, "%016X" % T.reinterpretFloatToRawInt(ref),
                                    "got:", T.from_py(v), "expected:", T.from_py(ref)))


class IEEE754FpFromInt_TC(SimTestCase):
    INPUT_DATA = [
        0, 1, 2, 3,
        mask(32),
        mask(63),  # max number
        to_signed(mask(64) - mask(63), 64),  # min number
        to_signed(mask(64), 64),  # -1
        to_signed(mask(64) - 1, 64),  # -2
    ]
    LOG_TIME = False

    def test_py(self):
        for a in self.INPUT_DATA:
            # print("in:", a)
            _res = IEEE754FpFromInt(int64_t.from_py(a), IEEE754Fp64)
            try:
                res = _res.to_py()
            except ValidityError:
                res = None
            # check if conversion from py int to hvalue and to float is correct
            resRef = IEEE754FpFromIntConventor.model(a)
            # print(res, resRef, "\n", _res, IEEE754Fp64.from_py(resRef))
            self.assertEqual(res, resRef,
                             msg=(res, _res, 'expected', resRef))

    def test_rlt(self):
        dut = IEEE754FpFromIntConventor()
        dut.CLK_FREQ = int(1e6)
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        if self.LOG_TIME:
            passTests.setDebugLogTime(PassTestInjector.logTimeToStdout)
            
        passTests.test_allInOne_withModel((PassTestIoInPyInt(HBits(64), self.INPUT_DATA),),
                                          (PassTestIoOutForIEEE754FpFromInt(dut.T, self.INPUT_DATA, []),))
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtLib.types.ctypes import int16_t
    from tests.math.fp.fptypes import IEEE754Fp16
    m = IEEE754FpFromIntConventor()
    # m.T_IN = int16_t
    # m.T = IEEE754Fp16
    m.T_IN = int64_t
    m.T = IEEE754Fp64
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    # import cProfile
    # pr = cProfile.Profile()
    # pr.enable()

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpFromInt_TC('test_rlt')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpFromInt_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

    # pr.disable()
    # pr.dump_stats('profile.prof')
