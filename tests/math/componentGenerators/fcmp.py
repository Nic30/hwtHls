from operator import eq, gt, ge, lt, le, ne
from typing import Optional

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.architecture.componentGeneratorUtils import ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpConfig, MachineInstr, Register, MachineRegisterInfo, TargetOpcode, \
    APInt, APFloat, CmpInst, InstructionToCallInst, Instruction, InstructionToFCmpInst, FCmpInst, CallInst
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    ComponentRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.llvmMirToNetlist.utils import MirToHlsNetlistTranslatedInstrOpsT
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.math.componentGenerators._componentGeneratorFp import ComponentGeneratorFp
from tests.math.componentGenerators._genericHwModules import _FpBinOpAluHwModule
from tests.math.componentGenerators.fpshl import ComponentGeneratorFP_SHL
from tests.math.fp.fpcmp import IEEE754FpCmpResult, IEEE754FpCmp
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import OP_FCMP_OEQ, OP_FCMP_OGT, \
    OP_FCMP_OGE, OP_FCMP_OLT, OP_FCMP_OLE, OP_FCMP_ONE


@serializeParamsUniq
class _FpCmpOpAluHwModule(_FpBinOpAluHwModule):
    """
    Universal HwModule wrapper around floating point compare operator function.
    """

    @override
    def hwConfig(self) -> None:
        _FpBinOpAluHwModule.hwConfig(self)
        self.FPCMP_OP = HwParam(None)

    @override
    def hwDeclr(self) -> None:
        assert self.FN is NotImplemented
        addClkRstn(self)

        t = self.T
        inT = HStruct(
            (t, "a"),
            (t, "b"),
        )
        OP = self.FPCMP_OP
        self._addDataInDataOut(inT, BIT)

        @hlsBytecode
        def _FN(x, loopPragmaGetter=lambda: None):
            res = PyBytecodeInline(IEEE754FpCmp)(x)
            if OP == HwtOps.EQ:
                return res._eq(IEEE754FpCmpResult.EQ)
            elif OP == HwtOps.UGT:
                return res._eq(IEEE754FpCmpResult.GT)
            elif OP == HwtOps.UGE:
                return res._eq(IEEE754FpCmpResult.GT) | res._eq(IEEE754FpCmpResult.EQ)
            elif OP == HwtOps.ULT:
                return res._eq(IEEE754FpCmpResult.LT)
            elif OP == HwtOps.ULE:
                return res._eq(IEEE754FpCmpResult.LT) | res._eq(IEEE754FpCmpResult.EQ)
            elif OP == HwtOps.NE:
                return res != IEEE754FpCmpResult.EQ
            else:
                raise AssertionError()

        self.FN = _FN


class ComponentGeneratorFCMP_hwtHlsFpIntrinsic(ComponentGenerator):

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction) -> LlvmIrInstrFunction:
        cmp = InstructionToCallInst(instr)
        assert cmp, instr
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 3)
        pred, _src0, _src1 = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1), instr.getOperand(2),))
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        resUndef = BIT.from_py(None)
        try:
            pred = CmpInst.Predicate(int(pred))
            opFn = ComponentGeneratorFCMP.CMP_PREDICATE_TO_FP_OP_PY[pred]
        except KeyError:
            raise AssertionError(instr)

        def _intrinsic_fp_fcmp(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if src0IsConst:
                op0 = _src0
            else:
                op0 = regs[_src0]

            if src1IsConst:
                op1 = _src1
            else:
                op1 = regs[_src1]

            if op0._is_full_valid() and op1._is_full_valid():
                op0 = float(cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(op0._dtype.bit_length(), int(op0))))
                op1 = float(cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(op1._dtype.bit_length(), int(op1))))
                v = opFn(op0, op1)
                res = BIT.from_py(v)
            else:
                res = resUndef
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_fp_fcmp


class ComponentGeneratorFCMP_delegate(ComponentGeneratorFp):
    """
    Used during execution of interprets and llvmMirToHlsNetlist to select variant of ComponentGeneratorFCMP based on predicate
    """

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction) -> LlvmIrInstrFunction:
        cmp = InstructionToFCmpInst(instr)
        pred = cmp.getPredicate()
        gen = self.platform._componentGenerators[(FCmpInst, pred)]
        return gen.llvmIrInterpretDecode(interpret, instr)

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        pred = CmpInst.Predicate(int(instr.getOperand(1).getImm()))
        gen = self.platform._componentGenerators[(TargetOpcode.HWTFPGA_FP_FCMP, pred)]
        return gen.llvmMirInterpretDecode(interpret, MRI, instr)

    def resolveRealizationOfLlvmMirMachineInstr(self, MRI: MachineRegisterInfo,
                                                netlist: HlsNetlistCtx, instr: MachineInstr) -> ComponentRealizationMeta:
        pred = CmpInst.Predicate(instr.getOperand(1).getImm())
        gen = self.platform._componentGenerators[(TargetOpcode.HWTFPGA_FP_FCMP, pred)]
        return gen.resolveRealizationOfLlvmMirMachineInstr(MRI, netlist, instr)

    def llvmMirToHlsNetlist(self,
                            mirToNetlist: HlsNetlistAnalysisPassMirToNetlist,
                            builder: HlsNetlistBuilder,
                            mbMeta: MachineBasicBlockMeta,
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Register, ops: MirToHlsNetlistTranslatedInstrOpsT) -> Optional[HlsNetNodeOutAny]:
        pred = ops[0]
        pred = CmpInst.Predicate(pred)
        gen = self.platform._componentGenerators[(TargetOpcode.HWTFPGA_FP_FCMP, pred)]
        return gen.llvmMirToHlsNetlist(mirToNetlist, builder, mbMeta,
                                       allBlockingLoadAck, name, instr, dst, ops)


class ComponentGeneratorFCMP(ComponentGeneratorFp):
    # U - unsigned, S - signed, O - ordered
    CMP_PREDICATE_TO_OP = {
        CmpInst.Predicate.FCMP_OEQ: OP_FCMP_OEQ,
        CmpInst.Predicate.FCMP_OGT: OP_FCMP_OGT,
        CmpInst.Predicate.FCMP_OGE: OP_FCMP_OGE,
        CmpInst.Predicate.FCMP_OLT: OP_FCMP_OLT,
        CmpInst.Predicate.FCMP_OLE: OP_FCMP_OLE,
        CmpInst.Predicate.FCMP_ONE: OP_FCMP_ONE,
    }
    CMP_PREDICATE_TO_FP_OP_PY = {
        CmpInst.Predicate.FCMP_OEQ: eq,
        CmpInst.Predicate.FCMP_OGT: gt,
        CmpInst.Predicate.FCMP_OGE: ge,
        CmpInst.Predicate.FCMP_OLT: lt,
        CmpInst.Predicate.FCMP_OLE: le,
        CmpInst.Predicate.FCMP_ONE: ne,
    }

    def __init__(self, platform: DefaultHlsPlatform, genNamePrefix:str, moduleName:str,
                 HWT_OPERATOR_UNSIGNED: HOperatorDef,
                 HWT_OPERATOR_SIGNED:HOperatorDef):
        ComponentGeneratorFp.__init__(self, platform, genNamePrefix, moduleName)
        self.HWT_OPERATOR_UNSIGNED = HWT_OPERATOR_UNSIGNED
        self.HWT_OPERATOR_SIGNED = HWT_OPERATOR_SIGNED
        self.schedulingCache: dict[HFloatTmpConfig, tuple[ComponentRealizationMeta, ComponentRealizationMeta]]

    @override
    def llvmIrInterpretDecode(self, interpret: LlvmIrInterpret, instr: Instruction) -> LlvmIrInstrFunction:
        cmp = InstructionToFCmpInst(instr)
        pred = cmp.getPredicate()
        op = ComponentGeneratorFCMP.CMP_PREDICATE_TO_OP[pred]
        _src0, _src1 = interpret._decodeInstArguments(instr.iterOperandValues())
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)

        opFn = op._evalFn

        def _opcode_FCmpInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]

            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]

            assert src0._dtype == HFloatTmp, ("Use only HFloatTmp for fp types internally", instr, src0)
            assert src1._dtype == HFloatTmp, ("Use only HFloatTmp for fp types internally", instr, src1)

            res = opFn(src0, src1)
            res = BIT.from_py(res)
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _opcode_FCmpInst

    @override
    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 4)  # dst, pred, lhs, rhs
        dst, predicate, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0),
                                                                                   instr.getOperand(1),
                                                                                   instr.getOperand(2),
                                                                                   instr.getOperand(3)))
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        resUndef = BIT.from_py(None)
        opDef = self.CMP_PREDICATE_TO_OP[CmpInst.Predicate(predicate)]
        evalFn = opDef._evalFn

        def _opcode_HWTFPGA_FP_FCMP(nowTime: int, regs: list[HConst]):
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
                assert res._dtype == BIT, res
            else:
                res = resUndef

            regs[dst] = res

        return _opcode_HWTFPGA_FP_FCMP

    @override
    def llvmMirToHlsNetlist(self,
                            mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                            builder: "HlsNetlistBuilder",
                            mbMeta: "MachineBasicBlockMeta",
                            allBlockingLoadAck: Optional[HlsNetNodeOutAny],
                            name: Optional[str],
                            instr: MachineInstr,
                            dst: Register, ops: MirToHlsNetlistTranslatedInstrOpsT) -> Optional[HlsNetNodeOutAny]:
        # enCond = ops[-1]
        cfg, ops = self._llvmMirExtractHFloatTmpConfigFromOps(ops, True)
        predicate, lhs, rhs = ops
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError(cfg)
            if cfg.hasSign:
                opDef = self.HWT_OPERATOR_SIGNED
            else:
                opDef = self.HWT_OPERATOR_UNSIGNED
            cfg = None  # this will be an normal integer math
        else:
            try:
                opDef = self.CMP_PREDICATE_TO_OP[predicate]
            except KeyError:
                raise AssertionError(instr)

        res = builder.buildOp(opDef, cfg, BIT, lhs, rhs, name=name)
        mirToNetlist.valCache.add(mbMeta.block, dst, res, True)
        return allBlockingLoadAck

    @override
    def toHwtCompatibleOperatorBeforeScheduling(self, node:HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
        return False

    @override
    def toHwtCompatibleOperatorAfterScheduling(self, node:"HlsNetNode", worklist: SetList[HlsNetNode]) -> bool:
        freq = node.netlist.realTimeClkPeriod
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            return False

        realizationSeenFromIn, realizationSeenFromOut = self.schedulingCache[(self.optThroughputVsArea, cfg)]
        hwModule = self._getConfiguredHwModule(freq, IEEE754Fp.fromHFloatTmpConfig(cfg), realizationSeenFromIn)
        ComponentGenerator_replaceHlsNetNodeOperatorWithHwModule(self, node, hwModule, worklist)

        if realizationSeenFromOut.fitsIntoSingleClockWindow():
            assert hwModule.getHlsOpRealizationMeta()[1].fitsIntoSingleClockWindow(), (hwModule, realizationSeenFromOut, hwModule.getHlsOpRealizationMeta())
        return True

    def _getConfiguredHwModule(self, realTimeClkPeriod:float, ty:IEEE754Fp, realization: Optional[OpRealizationMeta]):
        hwModule = _FpCmpOpAluHwModule()
        hwModule.T = ty
        hwModule.CLK_FREQ = int(1 / realTimeClkPeriod)
        hwModule.FPCMP_OP = self.HWT_OPERATOR_UNSIGNED
        if realization is not None:
            hwModule._setIoChannelTypes(realization)

        return hwModule

    def resolveRealizationForHlsNetlist(self, netlist: "HlsNetlistCtx",
                                        cfg: HFloatTmpConfig) -> ComponentRealizationMeta:
        p = self.platform
        cacheKey = cfg
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError()
            if cfg.hasSign:
                op = self.HWT_OPERATOR_SIGNED
            else:
                op = self.HWT_OPERATOR_UNSIGNED

            r = p.get_op_realization(op, None, cfg.getBitWidth(), 2, netlist.realTimeClkPeriod)
            r = ComponentRealizationMeta.fromOpRealization(r)
            self.schedulingCache[cacheKey] = (r, r)
            return r
        else:
            try:
                return self.schedulingCache[cacheKey][1]
            except KeyError:
                pass

            # run compilation of IntDiv HwModule to resolve scheduling properties
            hwModule = self._getConfiguredHwModule(netlist.realTimeClkPeriod, IEEE754Fp.fromHFloatTmpConfig(cfg), None)
            _, _, r = self.resolveRealizationOfNode_compileToResolveScheduling(
                netlist.parentHwModule, hwModule,
                netlist.dbgSubmoduleBuidTracer, cacheKey)
            return r

    @override
    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: ArchElement) -> None:
        assert not node._isMarkedRemoved, node
        assert not node._isRtlAllocated, node
        _i0, _i1 = ComponentGeneratorFP_SHL._toRtlForNode_getInputDeps(node, allocator)
        cfg: HFloatTmpConfig = node.operatorSpecialization
        if cfg.isInQFormat:
            if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
                raise NotImplementedError(node, cfg)

            if cfg.hasSign:
                op = self.HWT_OPERATOR_SIGNED
            else:
                op = self.HWT_OPERATOR_UNSIGNED

            outSig = op._evalFn(_i0.data, _i1.data)
            width = _i0.data._dtype.bit_length()
            assert outSig._dtype.bit_length() == 1, (
                "result of FCMP must be 1b wide",
                outSig._dtype, width, node, cfg)
        else:
            # netlist = node.netlist
            raise NotImplementedError()

        return ComponentGeneratorFP_SHL._toRtlForNode_registerOutput(node, allocator, outSig)
