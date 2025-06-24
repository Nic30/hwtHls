#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpRounding, HFloatTmpSaturation
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from tests.math.componentGenerators.fsincos import FixpSinCosCordic
from tests.math.fixp.cordicAtan2 import CordicAtan2
from tests.math.fixp.fixpTypes import HFixedPointQ

# maybe useful:
# * approx version https://doi.org/10.1109/UPCON56432.2022.9986456

@serializeParamsUniq
class FixpAtan2HypotCordic(FixpSinCosCordic):

    @override
    def hwConfig(self) -> None:
        FixpSinCosCordic.hwConfig(self)
        self.HAS_ATAN2 = HwParam(True)
        self.HAS_HYPOT = HwParam(False)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        T = self.T
        assert T.rounding == HFloatTmpRounding.ROUND_FLOOR, (T.rounding, "rounding on input should be disabled (only output is rounded)")
        assert T.saturation == HFloatTmpSaturation.SATURATE_NONE, T.rounding

        t = HBits(T.bit_length())
        outputFields = []
        if self.HAS_ATAN2:
            outputFields.append((t, "atan2"))
        if self.HAS_HYPOT:
            outputFields.append((t, "hypot"))
        _BaseALU1HwModule._addDataInDataOut(self,
                                             HStruct((t, "y"), (t, "x")),
                                             HStruct(*outputFields))
        if self.ITERATION_COUNT is None:
            self.ITERATION_COUNT = self._getMaxIterationCount()
        else:
            assert self.ITERATION_COUNT <= self._getMaxIterationCount(), (
                self, self.ITERATION_COUNT, self._getMaxIterationCount())
        assert self.STAGES_IN_LUT == 0, self.STAGES_IN_LUT

    @staticmethod
    def getAtan2Function(cordic: CordicAtan2):
        return cordic.atan2

    @override
    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal):
        T = self.T
        cordic = CordicAtan2(self.ITERATION_COUNT, loopPragmaGetter=lambda: _BaseALU1HwModule._getLoopMeta(self))

        inpY = _inp.y._reinterpret_cast(T)
        inpX = _inp.x._reinterpret_cast(T)
        res = PyBytecodeInline(self.getAtan2Function(cordic))(inpY, inpX)
        resTmp = self._getTypeOfIo(self.data_out).from_py(None)
        if self.HAS_ATAN2:
            resTmp.atan2 = res[0]._auto_cast(T)._reinterpret_cast(resTmp.atan2._dtype)
        if self.HAS_HYPOT:
            resTmp.hypot = res[1]._auto_cast(T)._reinterpret_cast(resTmp.hypot._dtype)
        return resTmp


class ComponentGeneratorFATAN2HYPOT(ComponentGenerator):

    def __init__(self, platform:"DefaultHlsPlatform", hasAtan2:bool, hasHypot:bool,
                 genNamePrefix:str, moduleName:str,
                 optThroughputVsArea=0.0,
                 FIXP_HWMODULE_CLS=FixpAtan2HypotCordic):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[float, HFloatTmpConfig], tuple[OpRealizationMeta, int, int]]
        self._hasAtan2 = hasAtan2
        self._hasHypot = hasHypot
        self.optThroughputVsArea = optThroughputVsArea
        self.FIXP_HWMODULE_CLS = FIXP_HWMODULE_CLS
        assert hasAtan2 or hasHypot

    def _getConfiguredFixpHwModule(self,
                                   realTimeClkPeriod:float,
                                   ty:HFixedPointQ,
                                   UNROLL_FACTOR:int,
                                   realization:OpRealizationMeta):
        hwModule = self.FIXP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.UNROLL_FACTOR = UNROLL_FACTOR
        hwModule.HAS_ATAN2 = self._hasAtan2
        hwModule.HAS_HYPOT = self._hasHypot
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == 2, node
        return self.resolveRealizationForHlsNetlist(node.netlist, node.operatorSpecialization)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", cfg: HFloatTmpConfig) -> None:
        cacheKey = (cfg, self.optThroughputVsArea)
        try:
            return self.schedulingCache[cacheKey][0]
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

            # run compilation of IntDiv HwModule to resolve scheduling properties
            hwModule = self._getConfiguredFixpHwModule(netlist.realTimeClkPeriod, ty, UNROLL_FACTOR, None)
            _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
                netlist.parentHwModule, hwModule,
                netlist.dbgSubmoduleBuidTracer, cacheKey, (UNROLL_FACTOR,))
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

            cacheKey = (cfg, self.optThroughputVsArea)
            realization, UNROLL_FACTOR = self.schedulingCache[cacheKey]
            hwModule = self._getConfiguredFixpHwModule(freq, HFixedPointQ.fromHFloatTmpConfig(cfg),
                                                       UNROLL_FACTOR, realization)
            if self._hasAtan2 and self._hasHypot:
                outputsBitMap = None
            elif self._hasAtan2:
                outputsBitMap = None  # cos starts at the bit 0
            elif self._hasHypot:
                outputsBitMap = (cfg.getBitWidth(),)  # remainder starts after quotient
            else:
                raise AssertionError("sincos component must be configured as a cos or sin (or both)")

            ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(
                self,
                node, hwModule, worklist, outputsBitMap=outputsBitMap)
            return True

        else:
            raise NotImplementedError()

        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)


@serializeParamsUniq
class FixpAtan2HypotCordicPi(FixpAtan2HypotCordic):

    @staticmethod
    def getAtan2Function(cordic: CordicAtan2):
        return cordic.atan2pi


class ComponentGeneratorFATAN2HYPOT_PI(ComponentGeneratorFATAN2HYPOT):

    def __init__(self, platform:"DefaultHlsPlatform", hasAtan2:bool, hasHypot:bool,
                 genNamePrefix:str, moduleName:str,
                 optThroughputVsArea=0.0,
                 optMaxStagesInLut=10,
                 FIXP_HWMODULE_CLS=FixpAtan2HypotCordicPi):
        super().__init__(platform, hasAtan2, hasHypot, genNamePrefix, moduleName,
                         optThroughputVsArea=optThroughputVsArea,
                         optMaxStagesInLut=optMaxStagesInLut,
                         FIXP_HWMODULE_CLS=FIXP_HWMODULE_CLS)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.componentGenerators.install import installFpComponentGenerators

    m = FixpAtan2HypotCordic()
    m.T = HFixedPointQ(4, 4, True, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    m.UNROLL_FACTOR = m._getMaxIterationCount()
    m.CLK_FREQ = int(100e6)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.filterPrintFuncs(["FixpCosSinCordic.mainThread",]),
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
