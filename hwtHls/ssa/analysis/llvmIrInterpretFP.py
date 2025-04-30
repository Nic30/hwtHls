from typing import Optional, Callable

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwtHls.llvm.llvmIr import Instruction, HFloatTmpConfig, BasicBlock, APFloat, APInt, \
    InstructionToCallInst, InstructionToFCmpInst
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import to_unsigned
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


def _decodeOpcode_FNeg(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    assert instr.getType().isDoubleTy(), instr
    _v, = interpret._decodeInstArguments(instr.iterOperandValues())
    vIsConst = isinstance(_v, HConst)

    def _opcode_FNeg(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        if vIsConst:
            v = _v
        else:
            v = regs[_v]

        if v._is_full_valid():
            v = -v
        else:
            v = HFloatTmp.from_py(None)

        interpret._storeInstrResult(waveLog, nowTime, regs, instr, v)

    return _opcode_FNeg


def _decodeOpcode_FCmpInst(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    cmp = InstructionToFCmpInst(instr)
    assert cmp is not None, instr
    pred = cmp.getPredicate()
    op = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]
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

        assert src0._dtype == HFloatTmp, ("Use only HFloatTmp for fp types internally", cmp, src0)
        assert src1._dtype == HFloatTmp, ("Use only HFloatTmp for fp types internally", cmp, src1)

        res = opFn(src0, src1)
        res = BIT.from_py(res)
        # inlined interpret._storeInstrResult from perf. reasons
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    return _opcode_FCmpInst


def _decodeIntrinsic_fp_castToHFloatTmp(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
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


def _decodeIntrinsic_fp_castFromHFloatTmp(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
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


def _decodeIntrinsic_fp_unspecialized_floatInt(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction, fn: Callable[[float, int], float]) -> LlvmIrInstrFunction:
    ops = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1)))
    resUndef = HFloatTmp.from_py(None)

    def _intrinsic_fp_unspecialized_floatInt(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        op0, op1 = interpret._prepareInstrArguments(ops, regs)
        if op0._is_full_valid() and op1._is_full_valid():
            res = fn(float(op0), int(op1))
            res = HFloatTmp.from_py(res)
        else:
            res = resUndef
        # inlined interpret._storeInstrResult from perf. reasons
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    return _intrinsic_fp_unspecialized_floatInt


def _decodeIntrinsic_fp_unspecialized_shl(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    return _decodeIntrinsic_fp_unspecialized_floatInt(interpret, bb, instr, lambda v, sh: v * (2.0 ** sh))


def _decodeIntrinsic_fp_unspecialized_shr(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    return _decodeIntrinsic_fp_unspecialized_floatInt(interpret, bb, instr, lambda v, sh: v * (2.0 ** -sh))


def _decodeIntrinsic_fp_applySpecializedBinOperator_FloatInt(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction, binOpFn: Callable[[float, int], float]):
    ops = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1)))
    cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 2)
    resUndef = HBits(cfg.getBitWidth()).from_py(None)

    def _intrinsic_specialized_BinOperator_FloatInt(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        op0, op1 = interpret._prepareInstrArguments(ops, regs)
        if op0._is_full_valid() and op1._is_full_valid():
            t = op0._dtype
            op0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(op0)))
            op0 = float(op0)
            v = binOpFn(op0, int(op1))
            v = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v))
            res = int(v)
            if res < 0:
                res = to_unsigned(res, t.bit_length())
            res = t.from_py(res)
        else:
            res = resUndef
        # inlined interpret._storeInstrResult from perf. reasons
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    return _intrinsic_specialized_BinOperator_FloatInt


def _decodeIntrinsic_fp_applySpecializedBinOperator_FloatFloat(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction, binOpFn: Callable[[float, int], float]):
    ops = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1)))
    cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 2)
    resUndef = HBits(cfg.getBitWidth()).from_py(None)

    def _intrinsic_specialized_BinOperator_FloatFloat(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        op0, op1 = interpret._prepareInstrArguments(ops, regs)
        if op0._is_full_valid() and op1._is_full_valid():
            t = op0._dtype
            op0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(op0)))
            op0 = float(op0)
            op1 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(op1)))
            op1 = float(op1)
            v = binOpFn(op0, op1)
            v = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v))
            res = int(v)
            if res < 0:
                res = to_unsigned(res, t.bit_length())
            res = t.from_py(res)
        else:
            res = resUndef
        # inlined interpret._storeInstrResult from perf. reasons
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    return _intrinsic_specialized_BinOperator_FloatFloat


def _decodeIntrinsic_fp_applySpecializedUnOperator(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction, opFn: Callable[[float, ], float]):
    cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 1)
    resUndef = HBits(cfg.getBitWidth()).from_py(None)
    _v, = interpret._decodeInstArguments((instr.getOperand(0),))
    vIsConst = isinstance(_v, HConst)

    def _intrinsic_specializedUnOperator(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        if vIsConst:
            v = _v
        else:
            v = regs[_v]

        if v._is_full_valid():
            t = v._dtype
            v = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(v)))
            v = opFn(float(v))
            v = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v))
            v = int(v)
            if v < 0:
                v = to_unsigned(v, t.bit_length())
            res = t.from_py(v)
        else:
            res = resUndef
        # inlined interpret._storeInstrResult from perf. reasons
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    return _intrinsic_specializedUnOperator


def _decodeIntrinsic_fp_unOp(opFn: Callable[[float, ], float]):

    def _intrinsic_fp_unOp(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
        return _decodeIntrinsic_fp_applySpecializedUnOperator(interpret, bb, instr, opFn)

    return _intrinsic_fp_unOp


def _decodeIntrinsic_fp_binOp(binOpFn: Callable[[float, float], float]):

    def _intrinsic_fp_binOp(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
        return _decodeIntrinsic_fp_applySpecializedBinOperator_FloatFloat(interpret, bb, instr, binOpFn)

    return _intrinsic_fp_binOp


def _decodeIntrinsic_fp_binOp_floatInt(binOpFn: Callable[[float, int], float]):

    def _intrinsic_fp_binOp_floatInt(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
        return _decodeIntrinsic_fp_applySpecializedBinOperator_FloatInt(interpret, bb, instr, binOpFn)

    return _intrinsic_fp_binOp_floatInt


def _decodeIntrinsic_fp_fcmp(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    cmp = InstructionToCallInst(instr)
    assert cmp is not None, instr
    cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 3)
    pred, _src0, _src1 = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1), instr.getOperand(2),))
    src0IsConst = isinstance(_src0, HConst)
    src1IsConst = isinstance(_src1, HConst)
    resUndef = BIT.from_py(None)
    try:
        opFn = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_FP_OP_PY[int(pred)]
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
