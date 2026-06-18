#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from typing import Sequence, Optional, Any

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
from tests.math.fp._PassTestInjectorForFp import PassTestIoInIEEE754Fp
from tests.math.fp.fpToInt import IEEE754FpToInt
from tests.math.fp.fptypes import IEEE754Fp64
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule, \
    hlsModelProps
from tests.passTestIo import PassTestIoOut


class IEEE754FpToIntConventor(HwModule):

    @override
    def hwConfig(self) -> None:
        self.T = HwParam(IEEE754Fp64)
        self.RES_T = HwParam(int64_t)
        self.CLK_FREQ = HwParam(int(20e6))

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.a = HwIOStructRdVld()
        self.a.T = self.T
        self.res = HwIOStructRdVld()._m()
        self.res.T = self.RES_T

    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(a: float) -> int:
        """
        :attention: implementation of RES_T = int64_t only
        """
        res = int(a)
        return max(min(res, mask(64 - 1)), to_signed(1 << 63, 64))

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            a = hls.read(self.a).data
            res = self.res.T.from_py(None)
            PyBytecodeInline(IEEE754FpToInt)(a, res)
            hls.write(res, self.res)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class PassTestIoOutWithInDataInErrMsg(PassTestIoOut):

    def __init__(self, dataRef:list[Any], IN_DATA_FOR_DEBUG:list, itemCntLimit:Optional[int]=None,
        name:Optional[str]=None,
        rtlPresetBeforeClk=True,
        randomizeControl=False):
        super().__init__(dataRef, itemCntLimit=itemCntLimit, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         randomizeControl=randomizeControl)
        self.IN_DATA_FOR_DEBUG = IN_DATA_FOR_DEBUG
    
    def checkForLlvmIr(self, dataSim:list[HBitsConst]):
        tc = self.passTests.tc
        tc.assertEqual(len(dataSim), len(self.dataRef))
        res_t = int64_t
        for res, resRef, a in zip(dataSim, self.dataRef, self.IN_DATA_FOR_DEBUG):
            res = res_t.from_py(to_signed(res.val, 64), res.vld_mask)
            tc.assertValEqual(res, resRef, msg=(res, 'expected', resRef, "input", a))


class IEEE754FpToInt_TC(SimTestCase):
    INPUT_DATA = [float(n) for n in [
        0.1,
        0, 1, 2, 3,
        mask(32),
        mask(63),
        mask(64) - mask(63),
        mask(64),
        -1,
        -0.1,
        -2,
        -3,
        -mask(63),
    ]]

    def test_py(self):
        assert sys.float_info.mant_dig - 1 == IEEE754Fp64.MANTISSA_WIDTH, (sys.float_info.mant_dig, IEEE754Fp64.MANTISSA_WIDTH)
        resV = int64_t.from_py(None)
        for a in self.INPUT_DATA:
            _a = IEEE754Fp64.from_py(a)
            _res = IEEE754FpToInt(_a, resV)
            try:
                res = int(_res)
            except ValidityError:
                res = None
            # check if conversion from py int to hvalue and to float is correct
            resRef = IEEE754FpToIntConventor.model(a)
            self.assertEqual(res, resRef, msg=(res, _res, 'expected', resRef, "input", a))

    def test_rtl(self):
        dut = IEEE754FpToIntConventor()
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.setTimeLimits(wallTimeRtl=(len(self.INPUT_DATA) + 1) * 2)
        passTests.test_allInOne_withModel(
            (PassTestIoInIEEE754Fp(dut.T, self.INPUT_DATA),),
            (PassTestIoOutWithInDataInErrMsg([], self.INPUT_DATA),)
        )

        self.rtl_simulator_cls = None


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from tests.math.fp.fptypes import IEEE754Fp
    from hwtLib.types.ctypes import int8_t

    m = IEEE754FpToIntConventor()
    m.T = IEEE754Fp(4, 4)
    m.RES_T = int8_t
    m.CLK_FREQ = int(1e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpToInt_TC('test_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpToInt_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
