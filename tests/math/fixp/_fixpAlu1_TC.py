#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type, Optional, Union, Sequence

from hwt.hdl.const import HConst
from hwt.hwModule import HwModule
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS, HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from pyMathBitPrecise.bit_utils import mask
from tests.math.fixp.fixpOperatorsHwModules import _FixpUnOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.passTestIoFixp import PassTestIoInHFixedPoint, \
    PassTestIoOutHFixedPoint
from tests.math.installMathLib import installMathLibComponentGenerators
from tests.passTestInjector import PassTestInjector
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule, hlsModelProps
from tests.passTestIo import PassTestIoIn, PassTestIoOut


class FixpAlu1_TC(SimTestCase):
    FP_TY = HFixedPointQ(4, 8)
    MAX_TABLE_ADDR_WIDTH = 0
    optThroughputVsArea = 0.0
    RTL_SIM_TIME_MULTIPLIER = 1.0
    MODULE_CLS: Type[_FixpUnOpTestModule]
    MAX_ULP = 1
    INPUT_DATA: list[tuple[float, ...]] = NotImplemented  # should be defined in child class

    def initPlatform(self, target_platform:VirtualHlsPlatform):
        installMathLibComponentGenerators(target_platform,
                                     optThroughputVsArea=self.optThroughputVsArea,
                                     MAX_TABLE_ADDR_WIDTH=self.MAX_TABLE_ADDR_WIDTH)
    
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(self, a: float) -> float:
        return self.MODULE_CLS.HLS_OP_FN(a)

    def test_rtl(self, dut: HwModule=None, freq=int(1e6), runTestAfterEachPass=False,
                  IN_DATA: Optional[tuple[Union[PassTestIoIn, Sequence[HConst]], ...]]=None,
                  OUT_DATA_REF: Optional[tuple[Union[PassTestIoOut, list[HConst]], ...]]=None,
                  IO_CONTROL_RANDOMIZE: Optional[tuple[Optional[Optional[bool]], ...]]=None,
                  rtlTimeMultiplier=1,
                  PassTestInjectorCls: type[PassTestInjector]=PassTestInjectorForDInDOutHwModule,
                  PassTestInjectorKwArgs:dict={},
                  platform:Optional[VirtualHlsPlatform]=None,
                  platformKwArgs=dict(
                    # debugFilter={*HlsDebugBundle.ALL_RELIABLE,
                    #             # HlsDebugBundle.DBG_4_0_hwscheduleTrace,
                    #             # HlsDebugBundle.DBG_4_0_hwscheduleDumpAfterPhases,
                    #             # HlsDebugBundle.DBG_4_0_hwschedulePrintPhaseBoundaries,
                    #             # HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                    #             # HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                    #           },
                    llvmCliArgs=[
                        LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                       # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                       # LLVM_CLI_COMMON_OPTS.VREGIFCVT_TRACE,
                       # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    ],)
                  ):
        if dut is None:
            dut = self.MODULE_CLS()
            dut.T = self.FP_TY
        if freq is not None:
            dut.CLK_FREQ = freq

        passTests: PassTestInjectorForDInDOutHwModule = PassTestInjectorCls(
            dut, self, **PassTestInjectorKwArgs)
        passTests.setRunTestsAfter(
            runTestAfterEachPass=runTestAfterEachPass,
            # runTestAfterEachMirPass=True,
        )
        passTests.setTimeLimits(wallTimeRtlDefaultMultiplier=self.RTL_SIM_TIME_MULTIPLIER * rtlTimeMultiplier,
                                wallTimeRtlDefaultAddAfter=20)
        if platform is None:
            platform = VirtualHlsPlatform(**platformKwArgs)
        else:
            assert not platformKwArgs
        self.initPlatform(platform)
        if IN_DATA is None:
            IN_DATA = (PassTestIoInHFixedPoint(dut.T, self.INPUT_DATA, name="data_in"),)
        if OUT_DATA_REF is None:
            OUT_DATA_REF = (PassTestIoOutHFixedPoint(dut.T, self.INPUT_DATA, [], maxErrorInt=mask(self.MAX_ULP), name="data_out"),)
        passTests.test_allInOne_withModel(IN_DATA=IN_DATA,
                                          OUT_DATA_REF=OUT_DATA_REF,
                                          IO_CONTROL_RANDOMIZE=IO_CONTROL_RANDOMIZE,
                                          platform=platform)
        self.rtl_simulator_cls = None

