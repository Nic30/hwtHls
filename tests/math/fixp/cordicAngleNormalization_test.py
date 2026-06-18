#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from tests.math.fixp._fixpAlu1_TC import FixpAlu1_TC
from tests.math.fixp.cordicAngleNormalization import cordic_withNormalization0_to_0_25, normalizeAnglePiRads0to0_25
from tests.math.fixp.fixpOperatorsTrigonometric_test import FixpSinNoLutUnroll_TC
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps
from tests.passTestIo import PassTestIoOut, ErrMsgFormatterT, \
    errMsgFrormatter_ioName


class _CordicAngleNormalizationTestModule(_BaseALU1HwModule):
    
    @override
    def hwConfig(self) -> None:
        _BaseALU1HwModule.hwConfig(self)
        self.IN_CHANNEL_TYPE = HwIOStructRdVld

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        t = self.T
        assert t is not None, self
        self._addDataInDataOut(
            HBits(t.bit_length()),
            HStruct(
                (HBits(HFixedPointQ(2, t.frac_bit_length, signed=False).bit_length()), "value"),
                (BIT, "swapXY"),
                (BIT, "negateX"),
                (BIT, "negateY"),
            )
        )

    @override
    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(data_in: float) -> tuple[float, bool, bool, bool]:
        return cordic_withNormalization0_to_0_25(data_in)

    @override
    @hlsBytecode
    def aluFn(self, _inp):
        T = self.T
        anglePiRad = _inp._reinterpret_cast(T)

        swapXY, negateX, negateY, _anglePiRad0to0_25 = PyBytecodeInline(normalizeAnglePiRads0to0_25)(anglePiRad)

        resTmp = self._getTypeOfIo(self.data_out).from_py(None)
        resTmp.value = _anglePiRad0to0_25._explicit_cast(T)\
            ._explicit_cast(HFixedPointQ(2, T.frac_bit_length, signed=False))\
            ._reinterpret_cast(resTmp.value._dtype)
        resTmp.swapXY = swapXY
        resTmp.negateX = negateX
        resTmp.negateY = negateY
        return resTmp


class PassTestIoOutForCordicAngleNormalization(PassTestIoOut):

    def __init__(self, fpTy:HdlType, dataRef: list[tuple[float, bool, bool, bool]], DATA_IN_FOR_DBG: Optional[list[float]], itemCntLimit:Optional[int]=None,
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 errMsgFormatter: Optional[ErrMsgFormatterT]=errMsgFrormatter_ioName,
                 randomizeControl=False,):
        super().__init__(dataRef, itemCntLimit=itemCntLimit, name=name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                         errMsgFormatter=errMsgFormatter, randomizeControl=randomizeControl)
        self.FP_TY = fpTy
        self.DATA_IN_FOR_DBG = DATA_IN_FOR_DBG
        outFpTy = fpTy._createMutated(int_bit_length=2)
        outBitTy = HBits(outFpTy.bit_length())
        self.outFpTy = outFpTy
        self.outBitTy = outBitTy

        def toFloat(v):
            assert v._dtype.bit_length() == outBitTy.bit_length(), (v, outBitTy)
            return float(outBitTy.from_py(v.val, v.vld_mask)._reinterpret_cast(outFpTy)) \
                if v._is_full_valid() else v

        self.toFloat = toFloat

        def toBool(v):
            return bool(v) if v._is_full_valid() else None

        self.toBool = toBool
        self.dataOutRefAsIntTuples: Optional[list[tuple[int, int, int, int]]] = None
    
    # def _buildDataOutRefAsTuples(self):
    #    fpTy = self.FP_TY
    #    bitTy = self.bitTy
    #    dataOutRefAsIntTuples = []
    #    for v, swapXY, negateX, negateY in self.dataOutRef:
    #        ref = (int(fpTy.from_py(v)._reinterpret_cast(bitTy)),
    #               int(swapXY),
    #               int(negateX),
    #               int(negateY))
    #        dataOutRefAsIntTuples.append(ref)
    #    self.dataOutRefAsIntTuples = dataOutRefAsIntTuples
    
    def checkForLlvmIr(self, dataSim:list[HBitsConst]):
        outBitTy = self.outBitTy
        toFloat = self.toFloat
        toBool = self.toBool
        # the output record is packed into wide word (ir/mir interpret)
        w = outBitTy.bit_length()
        _dataOut = [(toFloat(v[w:]), toBool(v[w]), toBool(v[w + 1]), toBool(v[w + 2])) for v in dataSim]
        
        dataRef = self.dataRef
        self.passTests.tc.assertSequenceEqual(
            _dataOut, dataRef,
            (self.DATA_IN_FOR_DBG, dataSim, "!=", dataRef)
        )  

    def checkForRtl(self):
        toFloat = self.toFloat
        toBool = self.toBool
        dataOut = self._getRtlDutPort()._ag.data

        # the record is provided as a tuple (rtl sim)
        _dataOut = [(toFloat(v[0]), toBool(v[1]), toBool(v[2]), toBool(v[3])) for v in dataOut]

        dataRef = self.dataRef
        self.passTests.tc.assertSequenceEqual(
            _dataOut, dataRef,
            (self.DATA_IN_FOR_DBG, dataOut, "!=", dataRef)
        )  
 

class CordicAngleNormalization_TC(FixpSinNoLutUnroll_TC):
    FP_TY = HFixedPointQ(4, 8, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    RTL_SIM_TIME_MULTIPLIER = 1.0
    INPUT_DATA = [
         # 0.5,
         *(0.0625 * i for i in range(int((2 / 0.0625) * 1.2))),
         *(-0.0625 * i for i in range(int((2 / 0.0625) * 1.2))),
         # 0.0,
         # 0.1, 0.2, 0.25, 0.5,
         # 1.0
    ]

    def test_rtl(self, runTestAfterEachPass=False, freq=int(1e6)):
        dut = _CordicAngleNormalizationTestModule()
        dut.T = self.FP_TY
        dut.IN_CHANNEL_TYPE = HwIOStructRdVld
        dut.CLK_FREQ = freq
        FixpAlu1_TC._test_rtl(self, runTestAfterEachPass=runTestAfterEachPass, freq=freq, dut=dut,
                               OUT_DATA_REF=(PassTestIoOutForCordicAngleNormalization(dut.T, [], DATA_IN_FOR_DBG=self.INPUT_DATA), ),
                               )


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast
    # from tests.math.installMathLib import installFpComponentGenerators

    # m = _CordicAngleNormalizationTestModule()
    # m.CLK_FREQ = int(1e6)
    # m.T = HFixedPointQ(4, 8, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    # platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
    #                      llvmCliArgs=[
    #                          # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
    #                          LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
    #                      ]
    #                      )
    # installFpComponentGenerators(platform)
    # print(to_rtl_str(m, target_platform=platform))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in [CordicAngleNormalization_TC, ]])
    # suite = testLoader.loadTestsFromTestCase(FixpDiv_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
