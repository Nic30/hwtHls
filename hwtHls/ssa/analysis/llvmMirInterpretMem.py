
from hwt.hdl.const import HConst
from hwt.hdl.types.arrayConst import HArrayConst
from hwt.hdl.types.bits import HBits
from hwtHls.llvm.llvmIr import MachineRegisterInfo, MachineInstr, GlobalValue, ValueToGlobalValue, \
    ValueToConstantArray, ValueToConstantDataArray, ConstantDataArray, ArrayType, TypeToArrayType
from hwtHls.ssa.analysis.llvmIrInterpretMem import _getItemFromLocalPointer
from hwtHls.ssa.analysis.llvmIrInterpretUtils import PtrAddrTuple, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtLib.abstract.sim_ram import SimRam


def _decodeOpcode_HWTFPGA_ARG_GET(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, i = interpret._decodeInstArguments(MRI, instr, instr.operands())
    assert dst == i

    def _opcode_HWTFPGA_ARG_GET(timeNow: int, regs: list[HConst]):
        assert regs[i] is None, regs[i]
        regs[i] = interpret.fnArgs[i]

    return _opcode_HWTFPGA_ARG_GET


def _decodeOpcode_HWTFPGA_CLOAD(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, io, index, width, cond = interpret._decodeInstArguments(MRI, instr, instr.operands())
    indexMo = instr.getOperand(2)
    hasRuntimeIndex = indexMo.isReg()
    condMo = instr.getOperand(4)
    hasRuntimeCond = condMo.isReg()
    if not hasRuntimeCond:
        if not cond:
            raise AssertionError("Always disabled HWTFPGA_CLOAD, this instruction should not exits", instr)

    t = HBits(width)
    # data invalid, but vld=0 (vld is msb bit)
    invalidData = t.from_py(0, vld_mask=1 << width - 1)

    def _opcode_HWTFPGA_CLOAD(timeNow: int, regs: list[HConst]):
        if hasRuntimeCond:
            _cond = regs[cond]
            assert _cond._is_full_valid(), (instr, "HWTFPGA_CLOAD must be always valid because otherwise communication in simulation can not be modeled")
            if not _cond:
                # read disabled, set result to
                regs[dst] = invalidData
                return

        if hasRuntimeIndex or index != 0:
            _io = regs[io]
            if hasRuntimeIndex:
                _index = regs[index]
            else:
                _index = index
            assert isinstance(_io, HArrayConst), (io, ":note: GlobalValue and alike should have been converted to HConst during interpret regs initialization")
            v = _getItemFromLocalPointer(regs, PtrAddrTuple((_io, _index)), width, instr)
        else:
            try:
                v = next(regs[io])
            except StopIteration:
                raise SimIoUnderflowErr("underflow on io argument", instr)

            if isinstance(v, HConst):
                if v._dtype != t:
                    assert v._dtype.bit_length() == t.bit_length(), (instr, v._dtype, t, v)
                    v = v._reinterpret_cast(t)
            else:
                v = t.from_py(v)
        regs[dst] = v

    return _opcode_HWTFPGA_CLOAD


def _decodeOpcode_G_LOAD(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, _io = interpret._decodeInstArguments(MRI, instr, instr.operands())
    llt = MRI.getType(instr.getOperand(0).getReg())
    assert llt.isValid()
    width = llt.getScalarSizeInBits()
    t = HBits(width)

    def _opcode_G_LOAD(timeNow: int, regs: list[HConst]):
        if isinstance(_io, int):
            io = regs[_io]
        else:
            io = _io
        if isinstance(io, (GlobalValue, PtrAddrTuple)):
            # load from local memory
            v = _getItemFromLocalPointer(regs, io, width, instr)
        else:

            # load from io
            try:
                v = next(io)
            except StopIteration:
                raise SimIoUnderflowErr("underflow on io argument", instr)

            if isinstance(v, HConst):
                if v._dtype != t:
                    assert v._dtype.bit_length() == t.bit_length(), (instr, v._dtype, t, v)
                    v = v._reinterpret_cast(t)
            else:
                v = t.from_py(v)
        regs[dst] = v

    return _opcode_G_LOAD


def _decodeOpcode_HWTFPGA_CSTORE(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    val, _io, index, width, cond = interpret._decodeInstArguments(MRI, instr, instr.operands())
    assert isinstance(_io, int), instr
    condMo = instr.getOperand(4)
    hasRuntimeCond = condMo.isReg()
    if not hasRuntimeCond:
        if not cond:
            raise AssertionError("Always disabled HWTFPGA_CLOAD, this instruction should not exits", instr)
    valIsConst = isinstance(val, HConst)
    hasIndex = not isinstance(index, int) or index != 0

    def _opcode_HWTFPGA_CSTORE_toIO(timeNow: int, regs: list[HConst]):
        io = regs[_io]
        if hasRuntimeCond:
            _cond = regs[cond]
            assert _cond._is_full_valid(), instr
            if not _cond:
                return

        if valIsConst:
            _val = val
        else:
            _val = regs[val]
        if hasIndex:
            _index = regs[index]
            io.write(_index, _val)
        else:
            io.append(_val)

    return _opcode_HWTFPGA_CSTORE_toIO


def _decodeOpcode_G_STORE(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    val, _io = interpret._decodeInstArguments(MRI, instr, instr.operands())
    valIsConst = isinstance(val, HConst)
    assert isinstance(_io, int), instr

    def _opcode_G_STORE(timeNow: int, regs: list[HConst]):
        io = regs[_io]
        if valIsConst:
            _val = valIsConst
        else:
            _val = regs[val]

        if isinstance(io, PtrAddrTuple):
            # SimRam
            io[0].write(io[1], _val)
        else:
            io.append(_val)

    return _opcode_G_STORE


def _decodeOpcode_HWTFPGA_IMPLICIT_DEF(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, width = interpret._decodeInstArguments(MRI, instr, instr.operands())
    t = HBits(width)
    undefVal = t.from_py(None)

    def _opcode_HWTFPGA_IMPLICIT_DEF(timeNow: int, regs: list[HConst]):
        regs[dst] = undefVal

    return _opcode_HWTFPGA_IMPLICIT_DEF


def _decodeOpcode_G_IMPLICIT_DEF(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, = instr.operands()
    llt = MRI.getType(dst.getReg())
    assert llt.isValid(), instr
    t = HBits(llt.getScalarSizeInBits())
    undefVal = t.from_py(None)
    dst = dst.getReg().virtRegIndex()

    def _opcode_G_IMPLICIT_DEF(timeNow: int, regs: list[HConst]):
        regs[dst] = undefVal

    return _opcode_G_IMPLICIT_DEF


def _decodeOpcode_G_CONSTANT(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, val = interpret._decodeInstArguments(MRI, instr, instr.operands())
    assert isinstance(val, HConst), instr

    def _opcode_G_CONSTANT(timeNow: int, regs: list[HConst]):
        regs[dst] = val

    return _opcode_G_CONSTANT


def _decodeOpcode_G_GLOBAL_VALUE(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, val = interpret._decodeInstArguments(MRI, instr, instr.operands())
    val = ValueToGlobalValue(val)

    def _opcode_G_GLOBAL_VALUE(timeNow: int, regs: list[HConst]):
        regs[dst] = regs[val]

    return _opcode_G_GLOBAL_VALUE


def _decodeOpcode_G_PTR_ADD(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, _op0, _op1 = interpret._decodeInstArguments(MRI, instr, instr.operands())

    def _opcode_G_PTR_ADD(timeNow: int, regs: list[HConst]):
        if isinstance(_op0, int):
            op0 = regs[_op0]
        else:
            op0 = op0
        if isinstance(_op1, int):
            op1 = regs[_op1]
        else:
            op1 = op1

        if isinstance(op0, PtrAddrTuple):
            _base, index = op0
        else:
            _base = op0
            index = 0

        if isinstance(_base, SimRam):
            base = _base
            raise NotImplementedError("the elementWidth is aligned by LLVM at this point")
            elementWidth = _base.getWriteWordWidth()
        else:
            if isinstance(_base, GlobalValue):
                base = _base
            else:
                base = ValueToGlobalValue(_base)
                assert base is not None, _base

            baseMem = base.getOperand(0)  # extract data from GlobalValue
            # scale op1 from uint8_t* to native type of array
            arrVal = ValueToConstantArray(baseMem)
            if arrVal is None:
                arrVal = ValueToConstantDataArray(baseMem)
                assert arrVal, (instr, baseMem)
                arrVal: ConstantDataArray
                arrTy: ArrayType = TypeToArrayType(arrVal.getType())
                assert arrTy, baseMem
                elementTy = arrTy.getElementType()
            else:
                elementTy = arrVal.getOperand(0).getType()

            elementWidth = elementTy.getScalarSizeInBits()
            assert isinstance(base, GlobalValue), base

        elementSize = elementWidth // 8
        if elementWidth > elementSize * 8:
            elementSize += 1
        op1 = op1 // elementSize

        index = op1 + index

        regs[dst] = PtrAddrTuple((base, index))

    return _opcode_G_PTR_ADD

