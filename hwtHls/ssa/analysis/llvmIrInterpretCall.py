
from typing import Optional

from hwt.code import Concat
from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import BasicBlock, Instruction, CallInst, InstructionToCallInst, Intrinsic
from pyDigitalWaveTools.vcd.writer import VcdWriter


def _decodeOpcode_CallInst(interpret: "LlvmIrInterpret", bb: BasicBlock, instr: Instruction) -> tuple[BasicBlock, bool]:
    call: CallInst = InstructionToCallInst(instr)
    assert call is not None, instr
    fn = call.getCalledFunction()
    fnName = fn.getName().str()
    inId = fn.getIntrinsicID()
    iiFn = interpret.INTRINSIC_ID_TO_FN.get(inId, None)
    if iiFn is not None:
        _ops = interpret._decodeInstArguments(a.get() for a in call.args())

        def _opcode_CallInst_intrinsic(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            ops = interpret._prepareInstrArguments(_ops, regs)
            res = iiFn(ops)
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
            fn = interpret._dispatchDictFP[m.group(1)]  # lookup fn by name
            return fn(interpret, bb, instr)
        else:
            raise NotImplementedError(instr)

    else:
        raise NotImplementedError(instr, Intrinsic.IndependentIntrinsics(inId))
