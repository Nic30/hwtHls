#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
from typing import Optional

from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._genericHwModules import _FpAlu1HwModule
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary
from tests.math.componentGenerators.fdivrem import ComponentGeneratorFDIVREM
from tests.math.fixp.fixpSqrt import fixpSqrt
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fpsqrt import IEEE754FpSqrt, _IEEE754FpSqrt_getInternSqrtTy
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmpOps import OP_FSQRT
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


@serializeParamsUniq
class FixpSqrtHwModule(_FpAlu1HwModule):
    """
    Universal module of fixed point square root to implement operators.
    """
    FN = staticmethod(fixpSqrt)

    @override
    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(data_in: float) -> float:
        return math.sqrt(data_in)

    @override
    def hwConfig(self) -> None:
        _FpAlu1HwModule.hwConfig(self)

    @override
    def _getMaxIterationCount(self):
        return self._getMaxIterationCountForTy(self.T)

    @staticmethod
    def _getMaxIterationCountForTy(t: HFixedPointQ) -> int:
        if isinstance(t, HFixedPointQ):
            return (t.int_bit_length + 2 * t.frac_bit_length) // 2
        elif isinstance(t, HBits):
            return t.bit_length() // 2
        else:
            raise NotImplementedError(t)


class ComponentGeneratorLlvmIntrinsicSqrt(ComponentGeneratorFp):
    INPUT_CNT = 1

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        assert isinstance(x, float), x
        try:
            return math.sqrt(x)
        except ValueError:
            assert isinstance(x, float), x
            return math.nan


class ComponentGeneratorFSQRT_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    evalFn = staticmethod(ComponentGeneratorLlvmIntrinsicSqrt.evalFn)


@serializeParamsUniq
class FpSqrtHwModule(_FpAlu1HwModule):
    FN = staticmethod(IEEE754FpSqrt)

    def _getMaxIterationCount(self):
        return self._getMaxIterationCountForTy(self.T)

    @classmethod
    def _getMaxIterationCountForTy(self, ty: IEEE754Fp):
        mantisaFixPTy = _IEEE754FpSqrt_getInternSqrtTy(ty)
        return FixpSqrtHwModule._getMaxIterationCountForTy(mantisaFixPTy)

    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(data_in: float) -> float:
        try:
            return math.sqrt(data_in)
        except ValueError:
            return math.nan


class ComponentGeneratorFSQRT(ComponentGeneratorFp):
    opDef = OP_FSQRT
    FIXP_HWMODULE_CLS = FixpSqrtHwModule
    FP_HWMODULE_CLS = FpSqrtHwModule

    def __init__(self, platform:DefaultHlsPlatform,
                 genNamePrefix:str, moduleName:str,
                 optThroughputVsArea=0.0):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[float, HFloatTmpConfig], tuple[ComponentRealizationMeta, ComponentRealizationMeta, int]]
        self.optThroughputVsArea = optThroughputVsArea

    def _getConfiguredFixpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ, UNROLL_FACTOR:int, realization: Optional[ComponentRealizationMeta]):
        hwModule = self.FIXP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.ITERATION_COUNT = ty.frac_bit_length
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    def _getConfiguredFpHwModule(self, realTimeClkPeriod:float, ty:IEEE754Fp, UNROLL_FACTOR:int, realization: Optional[ComponentRealizationMeta]):
        hwModule = self.FP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx, cfg: HFloatTmpConfig) -> None:
        return ComponentGeneratorFDIVREM.resolveRealizationForHlsNetlist(self, netlist, cfg)

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:HlsNetNode, worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        realization, _, UNROLL_FACTOR = self.schedulingCache[(cfg, self.optThroughputVsArea)]
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realization)
        else:
            hwModule = self._getConfiguredFpHwModule(freq, IEEE754Fp.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realization)

        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        return True

    @override
    def toRtlForNode(self, node:HlsNetNode, allocator:ArchElement) -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators

    m = FixpSqrtHwModule()
    m.CLK_FREQ = int(1e6)
    m.T = HFixedPointQ(4, 8, signed=False)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                              # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          ]
                          )
    installMathLibComponentGenerators(platform)
    print(to_rtl_str(m, target_platform=platform))

    # import unittest

    # testLoader = unittest.TestLoader()
    # # suite = unittest.TestSuite([DivRestoring_TC('test_div_py')])
    # suite = testLoader.loadTestsFromTestCase(SinCosCordicTC)
    # runner = unittest.TextTestRunner(verbosity=3)
    # runner.run(suite)
