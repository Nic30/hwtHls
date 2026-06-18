
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.math.componentGenerators._genericHwModules import _FpAlu1HwModule
from tests.math.fp._PassTestInjectorForFp import PassTestInjectorForFp
from tests.math.fp.fptypes import IEEE754Fp16, IEEE754FpHConst
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


class IEEE754FpAlu1_TC(SimTestCase):
    """
    Base classes for unary IEEE754Fp testcases
    """
    FP_FUNCTION = staticmethod(NotImplemented)
    FP_FUNCTION_HAS_SIM_ARG = False
    SIM_TIME_MULTIPLIER_IR_MIR = 3000
    FP_TY = IEEE754Fp16
    INPUT_DATA: list[float] = NotImplemented

    optThroughputVsArea = 1.0
    MAX_TABLE_ADDR_WIDTH = 0
    
    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(data_in: float):
        raise NotImplementedError()

    # @expectedFailure  # last bit is not correctly rounded
    def test_py(self):
        fpFn = self.FP_FUNCTION
        FP_TY = self.FP_TY
        for inPy in self.INPUT_DATA:
            inHw = FP_TY.from_py(inPy)
            resRef = self.model(inPy)
            if self.FP_FUNCTION_HAS_SIM_ARG:
                res = fpFn(inHw, isSim=True)
            else:
                res = fpFn(inHw)
            res: IEEE754FpHConst
            # print(aRaw, "+", bRaw, "=", t.to_py(res), "(", resRef, ")")
            msg = ('got', res.to_py(), "expected", resRef,
                   "inPy:", inPy,
                   "inHw:", inHw,
                   )
            self.assertEqual(res.to_py_tuple(), FP_TY.from_py(resRef).to_py_tuple(),
                             msg=msg)

    def _test_ir_mir_rtl(self, dut: _FpAlu1HwModule,
                         platformKwArgs=dict(),
                         platform:Optional[VirtualHlsPlatform]=None):
        passTests = PassTestInjectorForFp(dut, self, dut.T, self.optThroughputVsArea, self.MAX_TABLE_ADDR_WIDTH)
        wallTime = len(self.INPUT_DATA) * self.SIM_TIME_MULTIPLIER_IR_MIR
        passTests.setTimeLimits(wallTimeIr=wallTime, wallTimeMir=wallTime)
        passTests.test_allInOne_withModel((self.INPUT_DATA,), platformKwArgs=platformKwArgs, platform=platform)
        self.rtl_simulator_cls = None

