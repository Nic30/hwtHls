#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import replaceHlsNetNodeOperatorWithHwModule, \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder
from tests.math.componentGenerators.fdivrem import ComponentGeneratorFDIVREM
from tests.math.componentGenerators.genericHwModules import _FpUnOpAluHwModule
from tests.math.fixp.fixpSqrt import fixpSqrt
from tests.math.fixp.fixpTypes import HFixedPointQ


@serializeParamsUniq
class FixpSqrtHwModule(_FpUnOpAluHwModule):
    """
    Universal module of fixed point square root to implement operators.
    """

    @override
    def hwConfig(self) -> None:
        _FpUnOpAluHwModule.hwConfig(self)
        self.FN = fixpSqrt

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


class ComponentGeneratorFSQRT(ComponentGenerator):

    def __init__(self, platform:"DefaultHlsPlatform",
                 genNamePrefix:str, moduleName:str,
                 optThroughputVsArea=0.0,
                 FIXP_HWMODULE_CLS=FixpSqrtHwModule):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[float, HFloatTmpConfig], tuple[OpRealizationMeta, int]]
        self.optThroughputVsArea = optThroughputVsArea
        self.FIXP_HWMODULE_CLS = FIXP_HWMODULE_CLS

    def _getConfiguredFixpHwModule(self, realTimeClkPeriod:float, ty:HFixedPointQ, UNROLL_FACTOR:int, realization: Optional[OpRealizationMeta]):
        hwModule = self.FIXP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.ITERATION_COUNT = ty.frac_bit_length
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 1, node
        return self.resolveRealizationForHlsNetlist(node.netlist, node.operatorSpecialization)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", cfg: HFloatTmpConfig) -> None:
        return ComponentGeneratorFDIVREM.resolveRealizationForHlsNetlist(self, netlist, cfg)

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()

            realization, UNROLL_FACTOR = self.schedulingCache[(cfg, self.optThroughputVsArea)]
            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg), UNROLL_FACTOR, realization)
            ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
            return True

        else:
            raise NotImplementedError()

        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.componentGenerators.install import installFpComponentGenerators

    m = FixpSqrtHwModule()
    m.CLK_FREQ = int(1e6)
    m.T = HFixedPointQ(4, 8)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
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
