import math
from typing import Union, Optional

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpRounding, HFloatTmpSaturation
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.scope import HlsScope
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import sin, cos, sinpi, cospi, OP_FTAN, \
    OP_FTANPI, OP_FDIV, OP_FSINCOS
from tests.math.hFloatTmp.hFloatTmpUtils import HFloatTmpConfigToHType


@serializeParamsUniq
class TanCordicDivHwModule(_BaseALU1HwModule):

    def hwDeclr(self) -> None:
        addClkRstn(self)
        T = self.T

        t = HBits(T.bit_length())
        _BaseALU1HwModule._addDataInDataOut(self, t, t)

    def _isFullyUnrolled(self) -> bool:
        gens = self._target_platform._componentGenerators
        sincosGen = gens[OP_FSINCOS]
        divGen = gens[OP_FDIV]
        # the tan itself has no unroll factor but internal sin/cos and div have its own
        return abs(sincosGen.optThroughputVsArea - 1.0) >= -0.001 and \
            abs(divGen.optThroughputVsArea - 1.0) >= -0.001

    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal) -> HBitsRtlSignal:
        T = self.T
        inp = _inp._reinterpret_cast(T)._explicit_cast(HFloatTmp)
        sinVal = sin(inp)
        cosVal = cos(inp)
        tanVal = sinVal / cosVal
        return tanVal._explicit_cast(T)._reinterpret_cast(self._getTypeOfIo(self.data_out))

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(_BaseALU1HwModule.mainThread)(self, hls)


@serializeParamsUniq
class TanpiCordicDivHwModule(TanCordicDivHwModule):

    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal) -> HBitsRtlSignal:
        T = self.T
        inp = _inp._reinterpret_cast(T)._explicit_cast(HFloatTmp)
        sinVal = sinpi(inp)
        cosVal = cospi(inp)
        tanVal = sinVal / cosVal
        return tanVal._explicit_cast(T)._reinterpret_cast(self._getTypeOfIo(self.data_out))


class ComponentGeneratorLlvmIntrinsicTan(ComponentGeneratorFp):
    INPUT_CNT = 1

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.tan(x)


class ComponentGeneratorFTAN_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.tan(x)


class ComponentGeneratorFTANPI_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.tan(x * math.pi)


class ComponentGeneratorFTAN(ComponentGeneratorFp):
    FP_HWMODULE_CLS = TanCordicDivHwModule
    INPUT_CNT = 1
    opDef = OP_FTAN

    def __init__(self, platform:DefaultHlsPlatform,
                 genNamePrefix:str, moduleName:str):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # HFloatTmpConfig -> scheduling OpRealizationMeta
        self.schedulingCache: dict[tuple[HFloatTmpConfig], tuple[ComponentRealizationMeta, ComponentRealizationMeta]]

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, ty:Union[IEEE754Fp, HFixedPointQ], realization: Optional[ComponentRealizationMeta]):
        hwModule = self.FP_HWMODULE_CLS()
        hwModule._target_platform = self.platform
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    @override
    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx,
                                        cfg: HFloatTmpConfig) -> ComponentRealizationMeta:
        try:
            return self.schedulingCache[cfg][1]
        except KeyError:
            pass
        # run compilation of IntDiv HwModule to resolve scheduling properties
        ty = HFloatTmpConfigToHType(cfg)

        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, ty, None)
        _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule,
            netlist.dbgSubmoduleBuidTracer, cfg)
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:HlsNetNode, worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization

        realizationSeenFromIn, realizationSeenFromOut = self.schedulingCache[cfg]
        ty = HFloatTmpConfigToHType(cfg)

        hwModule = self._getConfiguredHwModule(freq, ty, realizationSeenFromIn)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        if realizationSeenFromOut.fitsIntoSingleClockWindow():
            assert hwModule.getHlsOpRealizationMeta()[1].fitsIntoSingleClockWindow(), (hwModule, realizationSeenFromOut, hwModule.getHlsOpRealizationMeta())
        return True


class ComponentGeneratorFTANPI(ComponentGeneratorFTAN):
    FP_HWMODULE_CLS = TanpiCordicDivHwModule
    opDef = OP_FTANPI


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators

    m = TanpiCordicDivHwModule()
    m.T = HFixedPointQ(3, 14, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    m.CLK_FREQ = int(100e6)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.filterPrintFuncs(["FixpCosSinCordic.mainThread",]),
                              LLVM_CLI_COMMON_OPTS.filterPrintFuncs(["TanCordicDivHwModule.mainThread", ]),
                              # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                              # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_ARGUMENTS,
                              # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                              LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          ]
                          )
    installMathLibComponentGenerators(platform, optThroughputVsArea=0.0, MAX_TABLE_ADDR_WIDTH=0)
    print(to_rtl_str(m, target_platform=platform))
