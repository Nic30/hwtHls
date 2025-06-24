from hwt.hdl.commonConstants import b1
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.thread import HlsThreadFromPy
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.scope import HlsScope
from tests.math.fixp.fixpResize import fixp_resize
from tests.math.fixp.fixpTypes import HFixedPointQ


@serializeParamsUniq
class FCastHwModule(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ: int = HwParam(int(20e6))
        self.IN_T: HdlType = HwParam(HFixedPointQ(2, 4))
        self.OUT_T: HdlType = HwParam(HFixedPointQ(2, 4))

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.data_in = HwIOVectSignal(self.IN_T.bit_length())
        self.data_out = HwIOVectSignal(self.OUT_T.bit_length())._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            inp = hls.read(self.data_in).data
            if isinstance(self.IN_T, HFixedPointQ) and isinstance(self.OUT_T, HFixedPointQ):
                res = fixp_resize(inp, self.IN_T, self.OUT_T)
            else:
                raise NotImplementedError()
            hls.write(res, self.data_out, mayBecomeFlushable=False)

    def _isFullyUnrolled(self):
        return True

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()
        _BaseALU1HwModule._backupTiming(self, hls, True)


class ComponentGeneratorFCAST(ComponentGenerator):

    def __init__(self, platform:"DefaultHlsPlatform", genNamePrefix:str, moduleName:str):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[HFloatTmpConfig, HFloatTmpConfig], OpRealizationMeta]

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, cfgSrc: HFloatTmpConfig, cfgDst: HFloatTmpConfig):
        hwModule = FCastHwModule()

        if not cfgSrc.isInQFormat:
            raise NotImplementedError(cfgSrc)

        hwModule.IN_T = HFixedPointQ.fromHFloatTmpConfig(cfgSrc)
        if not cfgDst.isInQFormat:
            raise NotImplementedError(cfgDst)

        hwModule.OUT_T = HFixedPointQ.fromHFloatTmpConfig(cfgDst)
        hwModule.CLK_FREQ = int(1. / realTimeClkPeriod)

        return hwModule

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        return self.resolveRealizationForHlsNetlist(node.netlist, node.operatorSpecialization)

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx", cfg: tuple[HFloatTmpConfig, HFloatTmpConfig]) -> None:
        try:
            return self.schedulingCache[cfg]
        except KeyError:
            pass
        cfgSrc, cfgDst = cfg
        cfgSrc: HFloatTmpConfig
        cfgDst: HFloatTmpConfig

        # run compilation of IntDiv HwModule to resolve scheduling properties
        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, cfgSrc, cfgDst)
        _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
            netlist.parentHwModule, hwModule, netlist.dbgSubmoduleBuidTracer, cfg)
        return r

#    @override
#    def toHwtCompatibleOperatorBeforeScheduling(self, node:"HlsNetNode",
#        worklist:SetList["HlsNetNode"]):
#        cfgSrc, cfgDst = node.operatorSpecialization
#        cfgSrc: HFloatTmpConfig
#        cfgDst: HFloatTmpConfig
#        # check for cases where this is just sext, zext, trunc or other for of bitslicing/concatenation
#        # such a implementation is too simple to justify the overhead of HwModule instantiation and thus
#        # such implementations are lowered in advance
#
#        if cfgSrc.isInQFormat and cfgDst.isInQFormat and cfgSrc.rounding == :
#            raise NotImplementedError()
#
#        return False

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfgSrc, cfgDst = node.operatorSpecialization
        cfgSrc: HFloatTmpConfig
        cfgDst: HFloatTmpConfig
        hwModule = self._getConfiguredHwModule(freq, cfgSrc, cfgDst)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        return True

    @override
    def toRtlForNode(self, node:"HlsNetNode", allocator:"ArchElement") -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    # from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = FCastHwModule()
    m.IN_T = HFixedPointQ(2, 3)
    m.CLK_FREQ = int(1e6)
    print(to_rtl_str(m, target_platform=Artix7Fast(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[
        #   LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        #   LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        # ]
    )))
