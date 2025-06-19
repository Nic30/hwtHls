from typing import Optional, Callable

from hwt.code import Concat
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import Instruction, BasicBlock, InstructionToICmpInst, \
    InstructionToCastInst, InstructionToSelectInst, InstructionToBinaryOperator, BinaryOperator, \
    CastInst
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from pyDigitalWaveTools.vcd.writer import VcdWriter


def _decodeOpcode_ICmpInst(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    cmp = InstructionToICmpInst(instr)
    assert cmp is not None, instr

    pred = cmp.getPredicate()
    op = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]

    _src0, _src1 = interpret._decodeInstArguments(instr.iterOperandValues())

    src0IsConst = isinstance(_src0, HConst)
    src1IsConst = isinstance(_src1, HConst)
    opFn = op._evalFn

    def _opcode_SelectInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        if src0IsConst:
            src0 = _src0
        else:
            src0 = regs[_src0]

        if src1IsConst:
            src1 = _src1
        else:
            src1 = regs[_src1]

        assert src0._dtype.signed is None, ("Use only not-signed internally", cmp, src0)
        assert src1._dtype.signed is None, ("Use only not-signed internally", cmp, src1)

        if src0._dtype != src1._dtype:
            # cases where force_vector, strict_sign or strict_width flag is different
            assert src0._dtype.bit_length() == src1._dtype.bit_length(), (
                "Operands must be of compatible type", instr, src0._dtype, src1._dtype)
            src1 = src1._auto_cast(src0._dtype)

        res = opFn(src0, src1)

        # inlined interpret._storeInstrResult from perf. reasons
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    return _opcode_SelectInst


def _decodeOpcode_SelectInst(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    select = InstructionToSelectInst(instr)
    assert select is not None, instr

    _c, _tVal, _fVal = interpret._decodeInstArguments(instr.iterOperandValues())
    cIsConst = isinstance(_c, HConst)
    tIsConst = isinstance(_tVal, HConst)
    fIsConst = isinstance(_fVal, HConst)

    def _opcode_SelectInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        if cIsConst:
            c = _c
        else:
            c = regs[_c]

        if tIsConst:
            tVal = _tVal
        else:
            tVal = regs[_tVal]

        if fIsConst:
            fVal = _fVal
        else:
            fVal = regs[_fVal]

        if c._is_full_valid():
            if c:
                res = tVal
            else:
                res = fVal
        else:
            res = tVal._dtype.from_py(None)

        # inlined interpret._storeInstrResult from perf. reasons
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    return _opcode_SelectInst


def _decodeOpcode_CastInst(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
    cast: CastInst = InstructionToCastInst(instr)
    assert cast is not None, instr

    opc = cast.getOpcode()
    _src0, = interpret._decodeInstArguments(cast.iterOperandValues())
    src0IsConst = isinstance(_src0, HConst)
    CastOps = Instruction.CastOps
    newWidth = cast.getType().getScalarSizeInBits()
    oTy = cast.getOperand(0).getType()
    assert oTy.isIntegerTy(), oTy
    oWidth = oTy.getIntegerBitWidth()

    if opc == CastOps.ZExt:
        padding = HBits(newWidth - oWidth).from_py(0)

        def _opcode_ZExt(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if src0IsConst:
                o = _src0
            else:
                o = regs[_src0]
            assert o._dtype.signed is None, (instr, o)
            res = Concat(padding, o)
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _opcode_ZExt

    elif opc == CastOps.SExt:

        def _opcode_SExt(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if src0IsConst:
                o = _src0
            else:
                o = regs[_src0]
            assert o._dtype.signed is None, (instr, o)
            msb = o[oWidth - 1]
            res = Concat(*(msb for _ in range(newWidth - oWidth)), o)
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _opcode_SExt

    elif opc == CastOps.Trunc:

        def _opcode_Trunc(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if src0IsConst:
                o = _src0
            else:
                o = regs[_src0]

            res = o[newWidth:]
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _opcode_Trunc

    else:
        raise NotImplementedError(instr)


def _makeDecodeOpcodeFunction_BinaryOperator(fn: Callable[[HConst, HConst], HConst]):

    def _decodeOpcode_BinaryOperator(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> LlvmIrInstrFunction:
        bi: BinaryOperator = InstructionToBinaryOperator(instr)
        assert bi is not None, instr

        _ops = interpret._decodeInstArguments(bi.iterOperandValues())

        def _opcode_BinaryOperator(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            ops = interpret._prepareInstrArguments(_ops, regs)
            res = fn(*ops)
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _opcode_BinaryOperator

    return _decodeOpcode_BinaryOperator


def _opcode_Intrinsic_uadd_sat(ops: tuple[HBitsConst, HBitsConst]):
    a, b = ops
    s = a + b
    if s < a:
        return a
    else:
        return s


def _opcode_Intrinsic_usub_sat(ops: tuple[HBitsConst, HBitsConst]):
    a, b = ops
    if a < b:
        return a._dtype.from_py(0)
    else:
        return a - b


def _opcode_Intrinsic_sadd_sat(ops: tuple[HBitsConst, HBitsConst]):
    a, b = ops
    a = a._signed()
    b = b._signed()
    # https://stackoverflow.com/a/17582366
    intMin, intMax = a._dtype.get_domain_range()
    if a > 0:
        _intMax = a._dtype.from_py(intMax)
        if b > _intMax - a:  # if b > than distance of a to max
            return _intMax._vec()
    else:
        _intMin = a._dtype.from_py(intMin)
        if b < _intMin - a:  # if b < than distance of a to min
            return _intMin._vec()

    return (a + b)._vec()


def _opcode_Intrinsic_ssub_sat(ops: tuple[HBitsConst, HBitsConst]):
    a, b = ops
    a = a._signed()
    b = b._signed()
    intMin, intMax = a._dtype.get_domain_range()
    res = a - b
    if a >= 0:
        if b < 0 and res < 0:
            return a._dtype.from_py(intMax)._vec()
    else:
        if b > 0 and res > 0:
            return a._dtype.from_py(intMin)._vec()

    return res._vec()
