
from typing import Optional

from hwt.code import Concat
from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import BasicBlock, Instruction, CallInst, InstructionToCallInst, Intrinsic, ValueToConstantInt, ValueToInstruction, InstructionToCastInst
from hwtHls.ssa.analysis.llvmIrInterpretUtils import HwtHlsFpIntrisicName
from pyDigitalWaveTools.vcd.writer import VcdWriter


def _decodeOpcode_CallInst(interpret: "LlvmIrInterpret", instr: Instruction) -> tuple[BasicBlock, bool]:
    call: CallInst = InstructionToCallInst(instr)
    assert call is not None, instr
    fn = call.getCalledFunction()
    fnName = fn.getName().str()
    inId = fn.getIntrinsicID()
    if inId != 0:
        inId = Intrinsic.IndependentIntrinsics(inId)
        iiFn = interpret.INTRINSIC_ID_TO_FN.get(inId, None)
    else:
        iiFn = None

    if iiFn is not None:
        _ops = interpret._decodeInstArguments(a.get() for a in call.args())

        def _opcode_CallInst_intrinsic(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            ops = interpret._prepareInstrArguments(_ops, regs)
            res = iiFn(interpret, instr, ops)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _opcode_CallInst_intrinsic

    elif fnName.startswith("hwtHls.bitRangeGet"):
        resW = instr.getType().getScalarSizeInBits()
        bitVector, index = interpret._decodeInstArguments(a.get() for a in call.args())
        assert isinstance(index, HBitsConst), (instr, index)
        if resW != 1:
            index = slice(index + resW, index)

        bitVectorIsConst = isinstance(bitVector, HConst)
        if bitVectorIsConst:
            _res = bitVector[index]
        else:
            _res = None

        def _opcode_CallInst_bitRangeGet(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if _res is None:
                res = regs[bitVector][index]
            else:
                res = _res

            if res._dtype.signed is not None:
                res = res._cast_sign(None)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _opcode_CallInst_bitRangeGet

    elif fnName.startswith("hwtHls.bitConcat"):
        _ops = interpret._decodeInstArguments(a.get() for a in call.args())

        def _opcode_CallInst_bitConcat(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            ops = interpret._prepareInstrArguments(_ops, regs)
            res = Concat(*reversed(ops))
            assert res._dtype.bit_length() == instr.getType().getScalarSizeInBits(), (
                instr, res._dtype, [o._dtype for o in ops])
            if res._dtype.signed is not None:
                res = res._cast_sign(None)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _opcode_CallInst_bitConcat

    elif inId == Intrinsic.assume:
        _ops = interpret._decodeInstArguments(a.get() for a in call.args())

        def _opcode_CallInst_Assume(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            ops = interpret._prepareInstrArguments(_ops, regs)
            c = ops[0]
            assert c.vld_mask == 0 or c, ("Assumed value must be always true", instr)

        return _opcode_CallInst_Assume

    elif fnName.startswith("hwtHls.fp."):
        m = interpret.RE_FP_INTRINSIC_ID.match(fnName)
        if m:
            cg: "ComponentGenerator" = interpret.componentGenerators[HwtHlsFpIntrisicName(m.group(1))]  # lookup fn by name
            return cg.llvmIrInterpretDecode(interpret, instr)
        else:
            raise NotImplementedError(instr)

    elif fnName.startswith("hwtHls.pyObjectPlaceholder."):
        _fnId = instr.getOperand(0)
        fnId = ValueToConstantInt(_fnId)
        if fnId is None:
            # case where Constant Hoisting replaced const with bitcast
            fnId = ValueToInstruction(_fnId)
            assert fnId, _fnId
            fnId = InstructionToCastInst(fnId)
            assert fnId, _fnId
            fnId = ValueToConstantInt(fnId.getOperand(0))
            assert fnId, _fnId

        fnId = fnId.getValue().getZExtValue()
        ph: "HardBlockHwModule" = interpret.placeholderObjectSlots[fnId][0]
        gen: "ComponentGeneratorForHardBlock" = interpret.componentGenerators[ph.getComponentGeneratorKey()]
        return gen.llvmIrInterpretDecode(interpret, instr, ph)

    else:
        cg: "ComponentGenerator" = interpret.componentGenerators.get(inId)  # lookup fn by intrinsic id
        if cg:
            return cg.llvmIrInterpretDecode(interpret, instr)
        else:
            raise NotImplementedError(instr, Intrinsic.IndependentIntrinsics(inId))

