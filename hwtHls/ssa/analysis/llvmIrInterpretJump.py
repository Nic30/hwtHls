from itertools import islice
from typing import Optional, Union

from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.arrayQuery import grouper
from hwtHls.llvm.llvmIr import BasicBlock, Instruction, InstructionToBranchInst, ValueToBasicBlock, InstructionToSwitchInst
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from hwtSimApi.triggers import StopSimumulation
from pyDigitalWaveTools.vcd.writer import VcdWriter


def _decodeOpcode_Br(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    br = InstructionToBranchInst(instr)
    assert br is not None, instr
    bb: BasicBlock = instr.getParent()
    if instr.getNumOperands() == 1:
        nextBb = ValueToBasicBlock(instr.getOperand(0))
        assert nextBb is not None, instr

        def _opcode_BranchInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if waveLog is not None:
                waveLog.logChange(nowTime, interpret._simBlockLabel, nextBb, None)

            interpret._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
            return nextBb

        return _opcode_BranchInst

    else:
        assert instr.getNumOperands() == 3, instr
        _cond, falseBlock, trueBlock = interpret._decodeInstArguments(instr.iterOperandValues())  # true/false is visually reversed in print, but ops are in this order
        condIsConst = isinstance(_cond, HConst)

        def _opcode_BranchInst_cond(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if condIsConst:
                cond = _cond
            else:
                cond = regs[_cond]
            assert cond._is_full_valid(), (br, cond)
            if cond:
                nextBb = trueBlock
            else:
                nextBb = falseBlock

            if waveLog is not None:
                waveLog.logChange(nowTime, interpret._simBlockLabel, nextBb, None)
            interpret._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
            return nextBb

        return _opcode_BranchInst_cond
    raise NotImplementedError(instr)


def _decodeOpcode_Switch(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    switchBr = InstructionToSwitchInst(instr)
    assert switchBr is not None, instr
    ops = interpret._decodeInstArguments(instr.iterOperandValues())
    _cond = ops[0]
    condIsConst = isinstance(_cond, HConst)
    bb: BasicBlock = instr.getParent()
    if condIsConst:
        assert _cond._is_full_valid(), ("jump condition must be always valid", _cond, bb, instr)
        _cond = _cond._cast_sign(None)
    defDst = ops[1]
    assert isinstance(defDst, BasicBlock), defDst

    condValPairs: list[tuple[Union[Union[HBitsConst, Instruction], bool, BasicBlock]]] = []
    for condVal, dst in grouper(2, islice(ops, 2, None)):
        assert isinstance(dst, BasicBlock), dst
        _IsConst = isinstance(condVal, HConst)
        condValPairs.append((condVal, _IsConst, dst))

    def _opcode_SwitchInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        if condIsConst:
            cond = _cond
        else:
            cond = regs[_cond]
            assert cond._is_full_valid(), ("jump condition must be always valid", cond, bb, instr)
            cond = cond._cast_sign(None)

        nextBB = defDst
        for condVal, condValIsConst, dst in condValPairs:
            if not condValIsConst:
                condVal = regs[condVal]
            if cond._eq(condVal):
                nextBB = dst
                break

        if waveLog is not None:
            waveLog.logChange(nowTime, interpret._simBlockLabel, nextBB, None)
        interpret._runBlockPhis(bb, nextBB, waveLog, regs, nowTime)
        return nextBB

    return _opcode_SwitchInst


def _decodeOpcode_RetInst(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:

    def _opcode_RetInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        raise StopSimumulation()

    return _opcode_RetInst
