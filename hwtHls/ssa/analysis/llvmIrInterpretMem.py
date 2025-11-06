from typing import Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.array import HArray
from hwt.hdl.types.arrayConst import HArrayConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import Instruction, InstructionToGetElementPtrInst, \
    TypeToArrayType, InstructionToFreezeInst, InstructionToAllocaInst, TypeToIntegerType, \
    ValueToAllocaInst, AllocaInst, Value, ArrayType, InstructionToExtractValueInst, ExtractValueInst
from hwtHls.ssa.analysis.llvmIrInterpretUtils import PtrAddrTuple, \
    LlvmIrInstrFunction
from hwtLib.abstract.sim_ram import SimRam
from pyDigitalWaveTools.vcd.writer import VcdWriter


def _decodeOpcode_Alloca(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    alloca: AllocaInst = InstructionToAllocaInst(instr)
    assert alloca is not None, instr
    assert alloca.getNumOperands() == 1  # alignment value
    Ty = alloca.getAllocatedType()
    intTy = TypeToIntegerType(Ty)
    if intTy is not None:
        v = HBits(intTy.getIntegerBitWidth()).from_py(None)
    elif Ty.isDoubleTy():
        v = interpret._getHFloatTmp().from_py(None)
    else:
        raise NotImplementedError(instr)

    def _opcode_Alloca(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        regs[instr] = v

    return _opcode_Alloca


def _decodeOpcode_Freeze(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    freeze = InstructionToFreezeInst(instr)
    assert freeze is not None, instr
    ops = interpret._decodeInstArguments(instr.iterOperandValue())
    _src0, = ops
    op0IsConst = isinstance(_src0, HConst)

    def _opcode_Freeze(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        if op0IsConst:
            o = _src0
        else:
            o = regs[_src0]
        regs[instr] = o

    return _opcode_Freeze


def _decodeOpcode_GetElementPtr(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    gep = InstructionToGetElementPtrInst(instr)
    assert gep is not None, instr
    ops = interpret._decodeInstArguments(instr.iterOperandValues())
    for i1 in ops[1:-1]:
        # assert that only last index is non zero
        assert int(i1) == 0, (gep, i1)

    base = ops[0]
    _i0 = ops[-1]
    ops = [base, _i0]

    def _opcode_GetElementPtr(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        base, _i0 = interpret._prepareInstrArguments(ops, regs)
        if not _i0._is_full_valid():
            i0 = _i0._dtype.from_py(None)
        else:
            if isinstance(base, PtrAddrTuple):
                base, i0 = base
            else:
                i0 = _i0._dtype.from_py(0)

            if int(_i0) != 0:
                if isinstance(base, HConst):
                    baseArrayTy = base._dtype
                    baseArrayTyIsLlvm = False
                elif isinstance(base, SimRam):
                    baseArrayTy = HBits(base.getWriteWordWidth())[base.itemCnt]
                    baseArrayTyIsLlvm = False
                else:
                    assert isinstance(base, Value), base
                    baseArrayTy = base.getOperand(0).getType()
                    baseArrayTyIsLlvm = True

                srcElmTy = gep.getSourceElementType()
                srcElmArrayTy: ArrayType = TypeToArrayType(srcElmTy)
                if srcElmArrayTy is not None:
                    # normal GEP accessing using index
                    if baseArrayTyIsLlvm:
                        baseArrayTy: ArrayType
                        assert srcElmArrayTy == baseArrayTy, (srcElmArrayTy, baseArrayTy)
                    else:
                        baseArrayTy: HArray
                        assert srcElmArrayTy.getNumElements() == baseArrayTy.size and\
                            srcElmArrayTy.getElementType().getScalarSizeInBits() == baseArrayTy.element_t.bit_length(), (srcElmArrayTy, baseArrayTy)
                else:
                    # gep using uint8_t pointer arithmetic, translating to index native to base
                    assert srcElmTy.isIntegerTy() and srcElmTy.getScalarSizeInBits() == 8, srcElmTy
                    if baseArrayTyIsLlvm:
                        srcElementWidth = TypeToArrayType(baseArrayTy).getElementType().getScalarSizeInBits()
                    else:
                        srcElementWidth = baseArrayTy.element_t.bit_length()
                    srcElementSize = srcElementWidth // 8
                    if srcElementWidth > srcElementSize * 8:
                        srcElementSize += 1
                    _i0 = _i0 // srcElementSize

                i0 = i0 + _i0

        regs[instr] = PtrAddrTuple((base, i0))

    return _opcode_GetElementPtr


def _getItemFromLocalPointer(regs: dict[Instruction, HBitsConst], srcPtr: Instruction, width: int, debugScope):
    if isinstance(srcPtr, PtrAddrTuple):
        base = srcPtr
    else:
        alloca = ValueToAllocaInst(srcPtr)
        if alloca is not None:
            res = regs[srcPtr]
            assert res._dtype.bit_length() == width, (debugScope, srcPtr)
            return res

        base = regs[srcPtr]

    # v = NOT_SPECIFIED
    if isinstance(base, PtrAddrTuple):  # consume products of gep
        base, i0 = base
        if not isinstance(i0, int) and not i0._is_full_valid():
            i0 = None
        else:
            i0 = int(i0)
    else:
        i0 = 0

    if i0 is None:
        return HBits(width).from_py(None)
    else:
        assert isinstance(base, HArrayConst), base
        return base[i0]
#        if isinstance(base, GlobalValue):
#            base = base.getOperand(0)  # extract data
#
#        if v is NOT_SPECIFIED:
#            arrVal = ValueToConstantArray(base)
#            if arrVal is None:
#                arrVal = ValueToConstantDataArray(base)
#                assert arrVal, (debugScope, base)
#                if i0 >= arrVal.getNumElements():
#                    v = None
#                else:
#                    v = arrVal.getElementAsAPInt(i0)
#            else:
#                if i0 >= arrVal.getNumOperands():
#                    v = None
#                else:
#                    v = ValueToConstantInt(arrVal.getOperand(i0)).getValue()
#            if v is not None:
#                v = to_unsigned(int(v), width)


def _decodeOpcode_ExtractValueInst(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    evi: ExtractValueInst = InstructionToExtractValueInst(instr)
    assert evi is not None, instr
    ops = interpret._decodeInstArguments(instr.iterOperandValues())
    indices = tuple(evi.indices())

    def _opcode_ExtractValueInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        v, = interpret._prepareInstrArguments(ops, regs)
        for i in indices:
            v = v[i]
        regs[instr] = v

    return _opcode_ExtractValueInst
