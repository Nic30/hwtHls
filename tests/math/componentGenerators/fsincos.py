#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
from typing import Optional

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragmaFunction import PyBytecodeSkipPass
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpRounding, HFloatTmpSaturation
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary
from tests.math.fixp.cordicHybridLut import Cordic
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmpOps import OP_FSINCOS, OP_FSIN, OP_FCOS, \
    OP_FSINCOSPI, OP_FSINPI, OP_FCOSPI


@serializeParamsUniq
class FixpSinCosCordic(_BaseALU1HwModule):

    @override
    def hwConfig(self) -> None:
        _BaseALU1HwModule.hwConfig(self)
        self.T = HFixedPointQ(3, 10,
                              rounding=HFloatTmpRounding.ROUND_FLOOR,
                              saturation=HFloatTmpSaturation.SATURATE_NONE)
        self.MAIN_FN_META = PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass", ])
        self.ITERATION_COUNT: Optional[int] = HwParam(None)
        self.STAGES_IN_LUT: Optional[int] = HwParam(0)

    @override
    def _getMaxIterationCount(self):
        return self._getMaxIterationCountForTy(self.T)

    @staticmethod
    def _getMaxIterationCountForTy(t: HFixedPointQ) -> int:
        return 2 + t.frac_bit_length

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        T = self.T
        assert T.rounding == HFloatTmpRounding.ROUND_FLOOR, (T.rounding, "rounding on input should be disabled (only output is rounded)")
        assert T.saturation == HFloatTmpSaturation.SATURATE_NONE, T.rounding

        t = HBits(T.bit_length())
        _BaseALU1HwModule._addDataInDataOut(self, t, HStruct(
            (t, "sin"),
            (t, "cos"),
        ))
        if self.ITERATION_COUNT is None:
            self.ITERATION_COUNT = self._getMaxIterationCount()
        else:
            assert self.ITERATION_COUNT <= self._getMaxIterationCount(), (
                self, self.ITERATION_COUNT, self._getMaxIterationCount())
        assert self.STAGES_IN_LUT <= self.ITERATION_COUNT, (self.STAGES_IN_LUT, self.ITERATION_COUNT)

    @override
    def _isFullyUnrolled(self):
        ITERATION_COUNT = self._getMaxIterationCount() - self.STAGES_IN_LUT
        assert self.UNROLL_FACTOR <= ITERATION_COUNT or self.UNROLL_FACTOR == 1, (
            "UNROLL_FACTOR is unnecessary large", self.UNROLL_FACTOR, self._getMaxIterationCount(), self.STAGES_IN_LUT, self.T, self)
        return self.UNROLL_FACTOR == ITERATION_COUNT or ITERATION_COUNT == 0

    @override
    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal):
        T = self.T
        cordic = Cordic(self.ITERATION_COUNT, self.STAGES_IN_LUT, loopPragmaGetter=lambda: _BaseALU1HwModule._getLoopMeta(self))

        inp = _inp._reinterpret_cast(T)
        res = PyBytecodeInline(cordic.cosSin)(inp)
        resTmp = self._getTypeOfIo(self.data_out).from_py(None)
        resTmp.cos = res[0]._auto_cast(T)._reinterpret_cast(resTmp.cos._dtype)
        resTmp.sin = res[1]._auto_cast(T)._reinterpret_cast(resTmp.sin._dtype)
        return resTmp


class ComponentGeneratorFSIN_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.sin(x)


class ComponentGeneratorFCOS_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.cos(x)


class ComponentGeneratorFSINPI_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.sin(x * math.pi)


class ComponentGeneratorFCOSPI_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.cos(x * math.pi)


class ComponentGeneratorFSINCOS(ComponentGeneratorFp):

    def __init__(self, platform:DefaultHlsPlatform,
                 genNamePrefix:str, moduleName:str,
                 hasCos:bool, hasSin:bool,
                 optThroughputVsArea=0.0,
                 optMaxStagesInLut=10,
                 FIXP_HWMODULE_CLS=FixpSinCosCordic):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[float, HFloatTmpConfig], tuple[ComponentRealizationMeta, ComponentRealizationMeta, int, int]]
        self._hasCos = hasCos
        self._hasSin = hasSin
        if hasSin and hasCos:
            self.opDef = OP_FSINCOS
        elif hasSin:
            self.opDef = OP_FSIN
        elif hasCos:
            self.opDef = OP_FCOS
        else:
            raise AssertionError()
        self.optThroughputVsArea = optThroughputVsArea
        self.optMaxStagesInLut = optMaxStagesInLut
        self.FIXP_HWMODULE_CLS = FIXP_HWMODULE_CLS

    def _getConfiguredFixpHwModule(self,
                                   realTimeClkPeriod:float,
                                   ty:HFixedPointQ,
                                   STAGES_IN_LUT:int,
                                   UNROLL_FACTOR:int,
                                   realization:OpRealizationMeta):
        assert STAGES_IN_LUT <= ty.frac_bit_length + 2, (STAGES_IN_LUT, ty.frac_bit_length)
        hwModule = self.FIXP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.STAGES_IN_LUT = STAGES_IN_LUT
        hwModule.ITERATION_COUNT
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx, cfg: HFloatTmpConfig) -> None:
        cacheKey = (cfg, self.optThroughputVsArea, self.optMaxStagesInLut)
        try:
            return self.schedulingCache[cacheKey][1]
        except KeyError:
            pass

        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            ty = HFixedPointQ.fromHFloatTmpConfig(cfg)
            maxIterations = self.FIXP_HWMODULE_CLS._getMaxIterationCountForTy(ty)
            if self.optThroughputVsArea == 0:
                UNROLL_FACTOR = 1
            elif self.optThroughputVsArea == 1.0:
                UNROLL_FACTOR = maxIterations
            else:
                raise NotImplementedError()

            STAGES_IN_LUT = min(maxIterations, self.optMaxStagesInLut)
            # clap UNROLL_FACTOR to range of available
            # iterations which are not precomputed in LUT
            UNROLL_FACTOR = max(min(UNROLL_FACTOR, maxIterations - STAGES_IN_LUT), 1)

            # run compilation of IntDiv HwModule to resolve scheduling properties
            hwModule = self._getConfiguredFixpHwModule(netlist.realTimeClkPeriod, ty, STAGES_IN_LUT, UNROLL_FACTOR, None)
            _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
                netlist.parentHwModule, hwModule,
                netlist.dbgSubmoduleBuidTracer, cacheKey, (STAGES_IN_LUT, UNROLL_FACTOR))
            return r
        else:
            raise NotImplementedError()

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            cacheKey = (cfg, self.optThroughputVsArea, self.optMaxStagesInLut)
            realization, _, STAGES_IN_LUT, UNROLL_FACTOR = self.schedulingCache[cacheKey]
            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg),
                                                       STAGES_IN_LUT, UNROLL_FACTOR, realization)
            if self._hasCos and self._hasSin:
                outputsBitMap = None
            elif self._hasCos:
                outputsBitMap = (cfg.getBitWidth(),)  # cos starts after sin
            elif self._hasSin:
                outputsBitMap = None  # sin starts at the bit 0
            else:
                raise AssertionError("sincos component must be configured as a cos or sin (or both)")
            ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist, outputsBitMap=outputsBitMap)
            return True

        else:
            raise NotImplementedError()

        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)


@serializeParamsUniq
class FixpSinCosCordicPi(FixpSinCosCordic):

    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal):
        T = self.T
        cordic = Cordic(self.ITERATION_COUNT, self.STAGES_IN_LUT, loopPragmaGetter=lambda: _BaseALU1HwModule._getLoopMeta(self))

        inp = _inp._reinterpret_cast(T)
        res = PyBytecodeInline(cordic.cosSinPi)(inp)
        resTmp = _BaseALU1HwModule._getTypeOfIo(self.data_out).from_py(None)
        resTmp.cos = res[0]._reinterpret_cast(resTmp.cos._dtype)
        resTmp.sin = res[1]._reinterpret_cast(resTmp.sin._dtype)
        return resTmp


class ComponentGeneratorFSINCOS_PI(ComponentGeneratorFSINCOS):

    def __init__(self, platform:"DefaultHlsPlatform",
                 genNamePrefix:str, moduleName:str,
                 hasCos:bool, hasSin:bool,
                 optThroughputVsArea=0.0,
                 optMaxStagesInLut=10,
                 FIXP_HWMODULE_CLS=FixpSinCosCordicPi):
        super().__init__(platform, genNamePrefix, moduleName, hasCos, hasSin,
                         optThroughputVsArea=optThroughputVsArea,
                         optMaxStagesInLut=optMaxStagesInLut,
                         FIXP_HWMODULE_CLS=FIXP_HWMODULE_CLS)
        if hasSin and hasCos:
            self.opDef = OP_FSINCOSPI
        elif hasSin:
            self.opDef = OP_FSINPI
        elif hasCos:
            self.opDef = OP_FCOSPI
        else:
            raise AssertionError()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.componentGenerators.install import installFpComponentGenerators

    m = FixpSinCosCordic()
    # m.T = HFixedPointQ(3, 14, True,
    #                   rounding=HFloatTmpRounding.ROUND_FLOOR,
    #                   saturation=HFloatTmpSaturation.SATURATE_NONE)
    m.T = HFixedPointQ(3, 4, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    m.STAGES_IN_LUT = 4
    # m.UNROLL_FACTOR = m._getMaxIterationCount() - m.STAGES_IN_LUT
    m.CLK_FREQ = int(100e6)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.filterPrintFuncs(["FixpSinCosCordic.mainThread",]),
                              # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                              # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_ARGUMENTS,
                              # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                              # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          ]
                          )
    installFpComponentGenerators(platform)
    print(to_rtl_str(m, target_platform=platform))

    # import unittest

    # testLoader = unittest.TestLoader()
    # # suite = unittest.TestSuite([DivRestoring_TC('test_div_py')])
    # suite = testLoader.loadTestsFromTestCase(SinCosCordicTC)
    # runner = unittest.TextTestRunner(verbosity=3)
    # runner.run(suite)
