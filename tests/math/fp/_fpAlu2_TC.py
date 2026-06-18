#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Union, Sequence, Any

from hwt.constants import NOT_SPECIFIED
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from tests.math.componentGenerators._genericHwModules import _FpAlu1HwModule
from tests.math.fp._PassTestInjectorForFp import PassTestInjectorForFp, \
    PassTestIoInIEEE754Fp, PassTestIoOutIEEE754Fp
from tests.math.fp.fptypes import IEEE754Fp16, IEEE754FpHConst
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps
from tests.passTestIo import PassTestIoIn, PassTestIoOut
from tests.passTestIoStruct import PassTestIoInStructWrap


class IEEE754FpAlu2_TC(SimTestCase):
    """
    Base classes for binary IEEE754Fp testcases
    """
    FP_FUNCTION = staticmethod(NotImplemented)
    FP_FUNCTION_HAS_SIM_ARG = False
    SIM_TIME_MULTIPLIER_IR_MIR = 3000
    FP_TY = IEEE754Fp16
    INPUT_DATA: list[tuple[float, float]] = NotImplemented

    optThroughputVsArea = 1.0
    MAX_TABLE_ADDR_WIDTH = 0
    
    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(a: float, b: float) -> float:
        raise NotImplementedError()

    def test_py(self):
        fpFn = self.FP_FUNCTION
        FP_TY = self.FP_TY
        for inPy in self.INPUT_DATA:
            inHw = tuple(FP_TY.from_py(v) for v in inPy)
            resRef = self.model(*inPy)
            if self.FP_FUNCTION_HAS_SIM_ARG:
                res = fpFn(*inHw, isSim=True)
            else:
                res = fpFn(*inHw)
            res: IEEE754FpHConst
            # print(aRaw, "+", bRaw, "=", t.to_py(res), "(", resRef, ")")
            msg = ('got', res.to_py(), "expected", resRef,
                   "inPy:", inPy,
                   "inHw:", inHw,
                   )
            self.assertEqual(res.to_py_tuple(), FP_TY.from_py(resRef).to_py_tuple(),
                             msg=msg)

    def _test_ir_mir_rtl(self, dut: _FpAlu1HwModule,
                         IN_DATA: Optional[tuple[Union[PassTestIoIn, Sequence[Any]], ...]]=None,
                         OUT_DATA_REF: Optional[tuple[Union[PassTestIoOut, list[Any]], ...]]=None,
                         platformKwArgs=dict(),
                         platform:Optional[VirtualHlsPlatform]=None,
                         wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,
                       ):
        passTests = PassTestInjectorForFp(dut, self, dut.T, self.optThroughputVsArea, self.MAX_TABLE_ADDR_WIDTH)
        wallTime = len(self.INPUT_DATA) * self.SIM_TIME_MULTIPLIER_IR_MIR
        passTests.setTimeLimits(wallTimeIr=wallTime, wallTimeMir=wallTime, wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)
        
        fpTy = self.FP_TY
        if IN_DATA is None:
            IN_DATA = (PassTestIoInStructWrap((PassTestIoInIEEE754Fp(fpTy, [], "a"),
                                               PassTestIoInIEEE754Fp(fpTy, [], "b")),
                                              self.INPUT_DATA, name="data_in", flattenForModel=True),)
        if OUT_DATA_REF is None:
            OUT_DATA_REF = (PassTestIoOutIEEE754Fp(fpTy, self.INPUT_DATA, [], name="data_out"),)
        
        passTests.test_allInOne_withModel(IN_DATA=IN_DATA, OUT_DATA_REF=OUT_DATA_REF,
                                          platformKwArgs=platformKwArgs, platform=platform)
        self.rtl_simulator_cls = None

