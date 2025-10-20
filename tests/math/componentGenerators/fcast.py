from typing import Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import \
    ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpConfig, Register, \
    MachineRegisterInfo, MachineInstr, Instruction, \
    InstructionToCallInst, APInt, APFloat
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import to_unsigned
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.fixp.fixpResize import fixp_resize
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpCast import OP_CAST_HFLOATTMP_TO_HFLOATTMP


@serializeParamsUniq
class FCastHwModule(_BaseALU1HwModule):

    @override
    def hwConfig(self) -> None:
        _BaseALU1HwModule.hwConfig(self)
        self.T_OUT: HdlType = HwParam(HFixedPointQ(2, 4))

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        t = self.T
        assert t is not None, self

        self._addDataInDataOut(HBits(self.T.bit_length()), HBits(self.T_OUT.bit_length()))

    @hlsBytecode
    def aluFn(self, inp) -> RtlSignal:
        if isinstance(self.T, HFixedPointQ) and isinstance(self.T_OUT, HFixedPointQ):
            res = fixp_resize(inp, self.T, self.T_OUT)
        else:
            raise NotImplementedError()
        return res

    def _isFullyUnrolled(self):
        return True


class ComponentGeneratorFCAST_hwtHlsFpIntrinsic_castToHFloatTmp(ComponentGenerator):

    @override
    def llvmIrInterpretDecode(self, interpret:LlvmIrInterpret, instr:Instruction) -> LlvmIrInstrFunction:
        _src0, = interpret._decodeInstArguments((instr.getOperand(0),))
        src0IsConst = isinstance(_src0, HConst)
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr))
        resUndef = HFloatTmp.from_py(None)

        def _intrinsic_fp_castToHFloatTmp(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]

            if src0._is_full_valid():
                res = HFloatTmp.from_py(float(cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(src0._dtype.bit_length(), f"{src0.val:x}", 16))))
            else:
                res = resUndef

            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_fp_castToHFloatTmp


class ComponentGeneratorFCAST_hwtHlsFpIntrinsic_castFromHFloatTmp(ComponentGenerator):

    @override
    def llvmIrInterpretDecode(self, interpret:LlvmIrInterpret, instr:Instruction) -> LlvmIrInstrFunction:
        _src0, = interpret._decodeInstArguments((instr.getOperand(0),))
        src0IsConst = isinstance(_src0, HConst)
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr))
        w = cfg.getBitWidth()
        t = HBits(w)
        resUndef = t.from_py(None)

        def _intrinsic_fp_castToHFloatTmp(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]

            if src0._is_full_valid():
                v = int(cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(float(src0))))
                if v < 0:
                    v = to_unsigned(v, w)
                res = t.from_py(v)
            else:
                res = resUndef

            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_fp_castToHFloatTmp


class ComponentGeneratorFCAST(ComponentGeneratorFp):

    def __init__(self, platform:DefaultHlsPlatform, genNamePrefix:str, moduleName:str):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        # dataWidth -> scheduling
        self.schedulingCache: dict[tuple[HFloatTmpConfig, HFloatTmpConfig], tuple[ComponentRealizationMeta, ComponentRealizationMeta]]

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                            builder: HlsNetlistBuilder,
                            mbMeta: MachineBasicBlockMeta,
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Register, ops: MirToHlsNetlistTranslatedInstrOpsT) -> Optional[HlsNetNodeOutAny]:
        dstFpCfg, ops = self._llvmMirExtractHFloatTmpConfigFromOps(ops, True)
        srcFpCfg, ops = self._llvmMirExtractHFloatTmpConfigFromOps(ops, False)
        assert len(ops) == 1, (instr, ops)
        opSpecialization = (srcFpCfg, dstFpCfg)
        res = builder.buildOp(OP_CAST_HFLOATTMP_TO_HFLOATTMP, opSpecialization, HBits(dstFpCfg.getBitWidth()), ops[0], name=name)
        mirToNetlist.valCache.add(mbMeta.block, dst, res, True)
        return allBlockingLoadAck

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, cfgSrc: HFloatTmpConfig, cfgDst: HFloatTmpConfig, realization:Optional[ComponentRealizationMeta]):
        hwModule = FCastHwModule()

        if not cfgSrc.isInQFormat:
            raise NotImplementedError(cfgSrc)

        hwModule.T = HFixedPointQ.fromHFloatTmpConfig(cfgSrc)
        if not cfgDst.isInQFormat:
            raise NotImplementedError(cfgDst)

        hwModule.T_OUT = HFixedPointQ.fromHFloatTmpConfig(cfgDst)
        hwModule.CLK_FREQ = int(1. / realTimeClkPeriod)
        if realization is not None:
            hwModule._setIoChannelTypes(realization)
        return hwModule

    @override
    def resolveRealizationOfLlvmMirMachineInstr(self, MRI: MachineRegisterInfo,
                                        netlist: HlsNetlistCtx, instr: MachineInstr) -> ComponentRealizationMeta:
        cfg0: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, instr.getNumOperands() - 2 * HFloatTmpConfig.MEMBER_CNT - 1)
        cfg1: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, instr.getNumOperands() - HFloatTmpConfig.MEMBER_CNT - 1)
        return self.resolveRealizationForHlsNetlist(netlist, (cfg0, cfg1))

    @override
    def resolveRealizationOfNode(self, node:HlsNetNodeOperator) -> None:
        return self.resolveRealizationForHlsNetlist(node.netlist, node.operatorSpecialization)

    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx, cfg: tuple[HFloatTmpConfig, HFloatTmpConfig]) -> None:
        try:
            return self.schedulingCache[cfg][1]
        except KeyError:
            pass
        cfgSrc, cfgDst = cfg
        cfgSrc: HFloatTmpConfig
        cfgDst: HFloatTmpConfig

        # run compilation of IntDiv HwModule to resolve scheduling properties
        hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, cfgSrc, cfgDst, None)
        _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
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
    def toHwtCompatibleOperatorAfterScheduling(self, node:HlsNetNode, worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfgSrc, cfgDst = node.operatorSpecialization
        cfgSrc: HFloatTmpConfig
        cfgDst: HFloatTmpConfig
        r, _ = self.schedulingCache[(cfgSrc, cfgDst)]
        hwModule = self._getConfiguredHwModule(freq, cfgSrc, cfgDst, r)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)
        return True

    @override
    def toRtlForNode(self, node:HlsNetNode, allocator:ArchElement) -> None:
        raise NotImplementedError("This should have been lowered before in toHwtCompatibleOperatorAfterScheduling", node)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    # from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = FCastHwModule()
    m.T = HFixedPointQ(2, 3)
    m.CLK_FREQ = int(1e6)
    print(to_rtl_str(m, target_platform=Artix7Fast(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[
        #   LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        #   LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        # ]
    )))
