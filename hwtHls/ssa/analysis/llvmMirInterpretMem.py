
from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.types.arrayConst import HArrayConst
from hwt.hdl.types.bits import HBits
from hwtHls.llvm.llvmIr import MachineRegisterInfo, MachineInstr, GlobalValue, ValueToGlobalValue, \
    ValueToConstantArray, ValueToConstantDataArray, ConstantDataArray, ArrayType, TypeToArrayType, \
    HwtHlsIoMetadata
from hwtHls.ssa.analysis.llvmIrInterpretMem import _getItemFromLocalPointer
from hwtHls.ssa.analysis.llvmIrInterpretUtils import PtrAddrTuple, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtLib.abstract.sim_ram import SimRam
from hwtSimApi.agents.base import NOP
from hwtHls.io.hwIoVectorized import HwIoProxyScalarVectorized, \
    splitConstBitsToLanes


def _decodeOpcode_HWTFPGA_ARG_GET(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, i = interpret._decodeInstArguments(MRI, instr, instr.operands())
    assert dst == i

    def _opcode_HWTFPGA_ARG_GET(timeNow: int, regs: list[HConst]):
        assert regs[i] is None, regs[i]
        regs[i] = interpret.fnArgs[i]

    return _opcode_HWTFPGA_ARG_GET


def _decodeOpcode_HWTFPGA_CLOAD(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, io, index, width, _ = interpret._decodeInstArguments(MRI, instr, instr.operands())
    indexMo = instr.getOperand(2)
    hasRuntimeIndex = indexMo.isReg()
    cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

    argI = tuple(instr.memoperands())[0].getAddrSpace() - 1
    ioMd: HwtHlsIoMetadata = interpret.ioMetadata[argI]
    isBlocking = ioMd.hasBlockingLoad
    t = HBits(width)
    if isBlocking:
        tWithoutVld = t
        validFlagMask = 0
    else:
        tWithoutVld = HBits(width - 1)
        validFlagMask = 1 << width - 1

    if ioMd.ioVectorization is not None and ioMd.ioVectorization.laneCnt != 1:
        raise NotImplementedError(instr)

    # data invalid, but vld=0 (vld is msb bit)
    invalidData = t.from_py(0, vld_mask=validFlagMask)

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
            if v is NOP:
                assert not isBlocking, instr
                v = invalidData
            else:
                if isinstance(v, HConst):
                    if v._dtype != tWithoutVld:
                        if isBlocking:
                            assert v._dtype.bit_length() == width, (instr, v._dtype, t, v)
                        else:
                            assert v._dtype.bit_length() == width - 1, (instr, v._dtype, t, v)

                        v = v._reinterpret_cast(tWithoutVld)

                    if not isBlocking:
                        v = b1._concat(v)  # concat with valid=1

                else:
                    if not isBlocking:
                        v |= validFlagMask
                    v = t.from_py(v)
        regs[dst] = v

    return _opcode_HWTFPGA_CLOAD


def _decodeOpcode_G_LOAD(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, _io = interpret._decodeInstArguments(MRI, instr, instr.operands())
    llt = MRI.getType(instr.getOperand(0).getReg())
    assert llt.isValid()
    width = llt.getScalarSizeInBits()

    ptrLlt = MRI.getType(instr.getOperand(1).getReg())
    assert ptrLlt.isPointer(), ptrLlt
    addrSpace = ptrLlt.getAddressSpace()
    if addrSpace > 0:
        ioMd: HwtHlsIoMetadata = interpret.ioMetadata[addrSpace - 1]
        isBlocking = ioMd.hasBlockingLoad
        if ioMd.ioVectorization is not None and ioMd.ioVectorization.laneCnt != 1:
            raise NotImplementedError(instr)
    else:
        ioMd = None
        isBlocking = True

    if isBlocking:
        t = HBits(width)
    else:
        t = HBits(width + 1)

    def _opcode_G_LOAD(timeNow: int, regs: list[HConst]):
        if isinstance(_io, int):
            io = regs[_io]
        else:
            io = _io

        if isinstance(io, (GlobalValue, PtrAddrTuple)):
            # load from local memory
            res = _getItemFromLocalPointer(regs, io, width, instr)
        else:
            # load from io
            try:
                res = next(io)
            except StopIteration:
                raise SimIoUnderflowErr("underflow on io argument", instr)

            if isinstance(res, HConst):
                if isBlocking:
                    assert res._dtype.bit_length() == width, (
                        "Input value must be must have correct width", instr, res._dtype, width)
                    if res._dtype != t:
                        res = res._reinterpret_cast(t)
                else:
                    assert res._dtype.bit_length() + 1 == width, (
                        "Input value must be must have correct width", instr, res._dtype, width + 1)
                    res = b1._concat(res)  # concat with valid=1

            else:
                res = t.from_py(res)
        regs[dst] = res

    return _opcode_G_LOAD


def _decodeOpcode_HWTFPGA_CSTORE(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    val, _io, index, width, _ = interpret._decodeInstArguments(MRI, instr, instr.operands())
    assert isinstance(_io, int), instr
    cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)
    valIsConst = isinstance(val, HConst)
    hasIndex = not isinstance(index, int) or index != 0
    # :note: at this point the instruction pointer operand and register will likely have no type
    mo = tuple(instr.memoperands())[0]
    addrSpace = mo.getAddrSpace()
    if addrSpace > 0:
        ioMd: HwtHlsIoMetadata = interpret.ioMetadata[addrSpace - 1]
        segmentWidth = ioMd.writeWordWidth
        laneCnt = HwIoProxyScalarVectorized.getLaneCntFromWidth(ioMd, segmentWidth, width)
    else:
        laneCnt = 1

    if laneCnt == 1:

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
    else:
        if valIsConst:
            _val = splitConstBitsToLanes(val, laneCnt, segmentWidth)
        assert not hasIndex, instr

        def _opcode_HWTFPGA_CSTORE_toVecIO(timeNow: int, regs: list[HConst]):
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
                _val = splitConstBitsToLanes(_val, laneCnt, segmentWidth)

            io.extend(_val)

        return _opcode_HWTFPGA_CSTORE_toVecIO


def _decodeOpcode_G_STORE(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    val, _io = interpret._decodeInstArguments(MRI, instr, instr.operands())
    valIsConst = isinstance(val, HConst)
    assert isinstance(_io, int), instr

    ptrLlt = MRI.getType(instr.getOperand(1).getReg())
    addrSpace = ptrLlt.getAddressSpace()
    if addrSpace > 0:
        ioMd: HwtHlsIoMetadata = interpret.ioMetadata[addrSpace - 1]
        segmentWidth = ioMd.writeWordWidth
        if valIsConst:
            width = val._dtype.bit_length()
        else:
            valT = MRI.getType(instr.getOperand(0).getReg())
            assert valT, instr
            width = valT.getScalarSizeInBits()

        laneCnt = HwIoProxyScalarVectorized.getLaneCntFromWidth(ioMd, segmentWidth, width)
    else:
        laneCnt = 1

    if laneCnt == 1:

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
    else:
        if valIsConst:
            val = splitConstBitsToLanes(val, laneCnt, segmentWidth)

        def _opcode_G_STORE_vec(timeNow: int, regs: list[HConst]):
            io = regs[_io]
            if valIsConst:
                _val = val
            else:
                _val = regs[val]
                _val = splitConstBitsToLanes(_val, laneCnt, segmentWidth)

            io.extend(_val)

        return _opcode_G_STORE_vec


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

