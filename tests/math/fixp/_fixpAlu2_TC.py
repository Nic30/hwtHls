from typing import Optional, Union, Sequence

from hwt.hdl.const import HConst
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
from hwtHls.platform.virtual import VirtualHlsPlatform
from pyMathBitPrecise.bit_utils import mask
from tests.math.fixp._fixpAlu1_TC import FixpAlu1_TC
from tests.math.fixp.fixpOperatorsHwModules import _FixpBinOpTestModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fixp.passTestIoFixp import PassTestIoInHFixedPoint, \
    PassTestIoOutHFixedPoint
from tests.passTestInjector import PassTestInjector
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIo import PassTestIoIn, PassTestIoOut
from tests.passTestIoStruct import PassTestIoInStructWrap


class FixpAlu2_TC(SimTestCase):
    FP_TY: HFixedPointQ = HFixedPointQ(4, 8)
    MAX_TABLE_ADDR_WIDTH = 0
    optThroughputVsArea = 0.0
    RTL_SIM_TIME_MULTIPLIER = 1.0
    INPUT_DATA: list[tuple[float, float]] = NotImplementedError
    MODULE_CLS: _FixpBinOpTestModule = NotImplementedError
    MAX_ULP = 0

    def initPlatform(self, target_platform:VirtualHlsPlatform):
        FixpAlu1_TC.initPlatform(self, target_platform)

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6), dut=None,
                 IN_DATA: Optional[tuple[Union[PassTestIoIn, Sequence[HConst]], ...]]=None,
                 OUT_DATA_REF: Optional[tuple[Union[PassTestIoOut, list[HConst]], ...]]=None,
                 PassTestInjectorKwArgs:dict={},
                 PassTestInjectorCls:type[PassTestInjector]=PassTestInjectorForDInDOutHwModule,
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
                    ],)):
        fpTy = self.FP_TY
        if IN_DATA is None:
            IN_DATA = (PassTestIoInStructWrap((PassTestIoInHFixedPoint(fpTy, [], "a"),
                                               PassTestIoInHFixedPoint(fpTy, [], "b")),
                                              self.INPUT_DATA, name="data_in", flattenForModel=True),)
        if OUT_DATA_REF is None:
            OUT_DATA_REF = (PassTestIoOutHFixedPoint(fpTy, self.INPUT_DATA, [], maxErrorInt=mask(self.MAX_ULP), name="data_out"),)
        
        FixpAlu1_TC.test_rtl(self, dut, freq=freq, runTestAfterEachPass=runTestAfterEachPass,
                               PassTestInjectorKwArgs=PassTestInjectorKwArgs,
                               PassTestInjectorCls=PassTestInjectorCls,
                               IN_DATA=IN_DATA,
                               OUT_DATA_REF=OUT_DATA_REF,
                               platform=platform,
                               platformKwArgs=platformKwArgs,
                               )
