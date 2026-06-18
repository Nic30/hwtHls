from typing import Union, Optional, Sequence

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.llvm.llvmIr import CmpInst, MachineBasicBlock, Register, HFloatTmpConfig, HFloatTmpRounding, HFloatTmpSaturation, \
    MachineInstr, MachineRegisterInfo, APInt, APFloat, CallInst, Instruction
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import to_unsigned
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpUtils import HFloatTmpConfigToHType


class ComponentGeneratorFp(ComponentGenerator):
    """
    Base class for fixed and floating point component generators configured by HFloatTmpConfig
    """
    INPUT_CNT = 1
    opDef: HOperatorDef = None  # :note: specify this in child class

    @override
    def llvmIrInterpretDecode(self, interpret:"LlvmIrInterpret", instr:CallInst) -> LlvmIrInstrFunction:
        resUndef = HFloatTmp.from_py(None)
        evalFn = self.evalFn
        if self.INPUT_CNT == 1:
            ops = interpret._decodeInstArguments((instr.getOperand(0),))

            def _intrinsic_unary_eval(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                op0, = interpret._prepareInstrArguments(ops, regs)
                if op0._is_full_valid():
                    op0 = float(op0)
                    v = evalFn(op0)
                    res = HFloatTmp.from_py(v)
                else:
                    res = resUndef
                # inlined interpret._storeInstrResult from perf. reasons
                if waveLog is not None:
                    waveLog.logChange(nowTime, instr, res, None)
                regs[instr] = res

            return _intrinsic_unary_eval

        elif self.INPUT_CNT == 2:
            ops = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1)))

            def _intrinsic_bin_eval(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                op0, op1 = interpret._prepareInstrArguments(ops, regs)
                if op0._is_full_valid() and op1._is_full_valid():
                    op0 = float(op0)
                    op1 = float(op1)
                    v = evalFn(op0, op1)
                    res = HFloatTmp.from_py(v)
                else:
                    res = resUndef
                # inlined interpret._storeInstrResult from perf. reasons
                if waveLog is not None:
                    waveLog.logChange(nowTime, instr, res, None)
                regs[instr] = res

            return _intrinsic_bin_eval
        else:
            raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    def llvmMirInterpretDecode_binary(self, interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 3)
        dst, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0), instr.getOperand(1), instr.getOperand(2)))
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        evalFn = self.opDef._evalFn

        # resTy = HBits(log2ceil(w + 1))
        def _opcode_FP_binary(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndef
            else:
                if src0IsConst:
                    src0 = _src0
                else:
                    src0 = regs[_src0]
                if src1IsConst:
                    src1 = _src1
                else:
                    src1 = regs[_src1]

                if src0._dtype.signed is not None:
                    src0 = src0._cast_sign(None)

                if src1._dtype.signed is not None:
                    src1 = src1._cast_sign(None)

                if src0._is_full_valid() and src1._is_full_valid():
                    t = src0._dtype
                    src0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src0)))
                    src1 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src1)))
                    res = evalFn(float(src0), float(src1))
                    res = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(res))
                    res = int(res)
                    if res < 0:
                        res = to_unsigned(res, t.bit_length())
                    res = t.from_py(res)
                else:
                    res = resUndef

            regs[dst] = res

        return _opcode_FP_binary

    def llvmMirInterpretDecode_unary(self, interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 2)
        dst, _src0 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0), instr.getOperand(1)))
        src0IsConst = isinstance(_src0, HConst)
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)
        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        evalFn = self.opDef._evalFn

        # resTy = HBits(log2ceil(w + 1))
        def _opcode_FP_unary(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndef
            else:
                if src0IsConst:
                    src0 = _src0
                else:
                    src0 = regs[_src0]

                if src0._dtype.signed is not None:
                    src0 = src0._cast_sign(None)

                if src0._is_full_valid():
                    t = src0._dtype
                    src0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src0)))
                    res = evalFn(float(src0))
                    res = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(res))
                    res = int(res)
                    if res < 0:
                        res = to_unsigned(res, t.bit_length())
                    res = t.from_py(res)
                else:
                    res = resUndef

            regs[dst] = res

        return _opcode_FP_unary

    @override
    def llvmMirInterpretDecode(self, interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        if self.INPUT_CNT == 1:
            return self.llvmMirInterpretDecode_unary(interpret, MRI, instr)
        elif self.INPUT_CNT == 2:
            return self.llvmMirInterpretDecode_binary(interpret, MRI, instr)
        else:
            raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @staticmethod
    def _llvmMirExtractHFloatTmpConfigFromOps(ops: list[Union[CmpInst.Predicate,
                                                              MachineBasicBlock,
                                                              Register,
                                                              HlsNetNodeOutAny,
                                                              HwIO,
                                                              int]],
                                              endsWithEnCond: bool):
        """
        Extract HFloatTmpConfig options from end of the operands,
        with the possibility that there is an  extra enCond in ops (and HFloatTmpConfig options are before it)
        """
        endsWithEnCond = int(endsWithEnCond)
        hFloatTmpConfigMembers = ops[-HFloatTmpConfig.MEMBER_CNT - endsWithEnCond:-2 - endsWithEnCond]
        opSpecialization = HFloatTmpConfig(*hFloatTmpConfigMembers,
                                           HFloatTmpRounding(ops[-2 - endsWithEnCond]),
                                           HFloatTmpSaturation(ops[-1 - endsWithEnCond]))

        ops = ops[:-HFloatTmpConfig.MEMBER_CNT - endsWithEnCond]
        return opSpecialization, ops

    @override
    def resolveRealizationOfLlvmMirMachineInstr(self, MRI: MachineRegisterInfo,
                                                netlist: HlsNetlistCtx,
                                                instr: MachineInstr) -> ComponentRealizationMeta:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, instr.getNumOperands() - HFloatTmpConfig.MEMBER_CNT - 1)
        return self.resolveRealizationForHlsNetlist(netlist, cfg)

    @override
    def resolveRealizationOfNode(self, node: HlsNetNodeOperator) -> ComponentRealizationMeta:
        # assert len(node.dependsOn) == self.INPUT_CNT + , node
        w = node.dependsOn[0]._dtype.bit_length()
        netlist = node.netlist
        cfg: HFloatTmpConfig = node.operatorSpecialization
        assert w == cfg.getBitWidth(), (node, w, cfg.getBitWidth(), cfg)
        return self.resolveRealizationForHlsNetlist(netlist, cfg)

    def resolveRealizationForHlsNetlist(self, netlist: HlsNetlistCtx,
                                        cfg: HFloatTmpConfig) -> ComponentRealizationMeta:
        """
        :note: this method should also update schedulingCache
        """
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def llvmMirToHlsNetlist(self,
            mirToNetlist:HlsNetlistAnalysisPassMirToNetlist,
            builder:HlsNetlistBuilder,
            mbMeta:MachineBasicBlockMeta,
            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
            name: Optional[str],
            instr: MachineInstr,
            dst:Register, ops: MirToHlsNetlistTranslatedInstrOpsT,
            inNames: Optional[Sequence[str]]=None,
            outNames: Optional[Sequence[str]]=None) -> Optional[HlsNetNodeOutAny]:
        enCond = ops[-1]
        opSpecialization, ops = self._llvmMirExtractHFloatTmpConfigFromOps(ops, True)
        r = self.resolveRealizationOfLlvmMirMachineInstr(mirToNetlist.MRI, builder.netlist, instr)
        return mirToNetlist._translateOperatorFromComponent(mirToNetlist, builder, mbMeta, allBlockingLoadAck, enCond, name, instr,
                                                            dst, ops, r, self.opDef, opSpecialization, inNames, outNames)

    def _scaleUnrollFactor(self, cfg: HFloatTmpConfig):
        ty = HFloatTmpConfigToHType(cfg)

        if self.optThroughputVsArea == 0:
            UNROLL_FACTOR = 1
        elif self.optThroughputVsArea == 1.0:
            if cfg.isInQFormat:
                HWMODULE_CLS = self.FIXP_HWMODULE_CLS
            else:
                HWMODULE_CLS = self.FP_HWMODULE_CLS

            UNROLL_FACTOR = HWMODULE_CLS._getMaxIterationCountForTy(ty)
        else:
            raise NotImplementedError()

        return UNROLL_FACTOR
