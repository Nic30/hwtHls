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
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpRounding, HFloatTmpSaturation
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import sin, cos, sinpi, cospi
from tests.math.hFloatTmp.hFloatTmpUtils import HFloatTmpConfigToHType


@serializeParamsUniq
class TanCordicDivHwModule(_BaseALU1HwModule):

    def hwDeclr(self) -> None:
        addClkRstn(self)
        T = self.T
        assert T.rounding == HFloatTmpRounding.ROUND_FLOOR, (T.rounding, "rounding on input should be disabled (only output is rounded)")
        assert T.saturation == HFloatTmpSaturation.SATURATE_NONE, T.rounding

        t = HBits(T.bit_length())
        _BaseALU1HwModule._addDataInDataOut(self, t, t)

    def _isFullyUnrolled(self):
        return True  # the tan itself has no unroll factor but internal sin/cos and div have its own

    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal) -> HBitsRtlSignal:
        T = self.T
        inp = _inp._reinterpret_cast(T)._auto_cast(HFloatTmp)
        sinVal = sin(inp)
        cosVal = cos(inp)
        tanVal = sinVal / cosVal
        return tanVal._auto_cast(T)._reinterpret_cast(self._getTypeOfIo(self.data_out))


@serializeParamsUniq
class TanpiCordicDivHwModule(TanCordicDivHwModule):

    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal) -> HBitsRtlSignal:
        T = self.T
        inp = _inp._reinterpret_cast(T)._auto_cast(HFloatTmp)
        sinVal = sinpi(inp)
        cosVal = cospi(inp)
        tanVal = sinVal / cosVal
        return tanVal._auto_cast(T)._reinterpret_cast(self._getTypeOfIo(self.data_out))


class ComponentGeneratorFTAN(ComponentGenerator):
    FP_HWMODULE_CLS = TanCordicDivHwModule
    INPUT_CNT = 1

    def __init__(self, platform:"DefaultHlsPlatform",
                 genNamePrefix:str, moduleName:str):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # HFloatTmpConfig -> scheduling OpRealizationMeta
        self.schedulingCache: dict[tuple[HFloatTmpConfig], OpRealizationMeta]

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, ty:Union[IEEE754Fp, HFixedPointQ], realization: Optional[OpRealizationMeta]):
        hwModule = self.FP_HWMODULE_CLS()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> None:
        assert len(node.dependsOn) == self.INPUT_CNT, node
        cfg: HFloatTmpConfig = node.operatorSpecialization

        try:
            return self.schedulingCache[cfg]
        except KeyError:
            pass
        netlist = node.netlist
        # run compilation of IntDiv HwModule to resolve scheduling properties
        ty = HFloatTmpConfigToHType(cfg)

        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, ty, None)
        _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule,
            netlist.dbgSubmoduleBuidTracer, cfg)
        return r

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization

        realization = self.schedulingCache[cfg]
        ty = HFloatTmpConfigToHType(cfg)

        hwModule = self._getConfiguredHwModule(freq, ty, realization)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        if realization.fitsIntoSingleClockWindow():
            assert hwModule.hlsOpRealizationMeta.fitsIntoSingleClockWindow(), (hwModule, realization, hwModule.hlsOpRealizationMeta)
        return True


class ComponentGeneratorFTANPI(ComponentGeneratorFTAN):
    FP_HWMODULE_CLS = TanpiCordicDivHwModule


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.componentGenerators.install import installFpComponentGenerators

    m = TanpiCordicDivHwModule()
    m.T = HFixedPointQ(3, 14, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
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
    installFpComponentGenerators(platform, defaultOptThroughputVsArea=1.0, MAX_TABLE_ADDR_WIDTH=10)
    print(to_rtl_str(m, target_platform=platform))
