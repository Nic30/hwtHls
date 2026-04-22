from typing import Optional

from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.types.array import HArray
from hwt.hdl.types.arrayConst import HArrayConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.io.hwIoVectorized import splitConstBitsToLanes, \
    HwIoProxyScalarVectorized
from hwtHls.llvm.llvmIr import Instruction, InstructionToGetElementPtrInst, \
    IntegerType, TypeToArrayType, InstructionToFreezeInst, InstructionToAllocaInst, TypeToIntegerType, \
    ValueToAllocaInst, AllocaInst, Value, ArrayType, InstructionToExtractValueInst, ExtractValueInst, \
    InstructionToLoadInst, ValueToArgument, TypeToPointerType, ValueToInstruction, ValueToConstantFP, \
    ValueToUndefValue, ValueToConstantInt, InstructionToStoreInst, StreamChannelProps, HwtHlsIoMetadata
from hwtHls.ssa.analysis.llvmIrInterpretUtils import PtrAddrTuple, \
    LlvmIrInstrFunction, SimIoUnderflowErr
from hwtLib.abstract.sim_ram import SimRam
from hwtSimApi.agents.base import NOP
from pyDigitalWaveTools.vcd.writer import VcdWriter


def _opcode_Intrinsic_memcpy(interpret: "LlvmIrInterpret", instr: Instruction, ops: tuple[object, ...]):
    dst, src, length, isVolatile = ops
    length = int(length)
    if isinstance(dst, AllocaInstCell) and isinstance(dst.v, HArrayConst) and isinstance(src, HArrayConst):
        dst = dst.v
        DL = interpret.F.getParent().getDataLayout()
        if dst._dtype.element_t != src._dtype.element_t:
            raise NotImplementedError(dst._dtype.element_t, src._dtype.element_t)
        elmTy = IntegerType.getIntNTy(instr.getContext(), dst._dtype.element_t.bit_length())
        # arrTy = TypeToArrayType(instr.getOperand(0).getType())
        # assert arrTy is not None
        # size = DL.getTypeAllocSize(arrTy).getFixedValue()
        # sizeOfWord = size // arrTy.getNumElements()
        sizeOfWord = DL.getTypeAllocSize(elmTy).getFixedValue()
        if length % sizeOfWord != 0:
            raise NotImplementedError(instr)
        for wordI in range(length // sizeOfWord):
            dst[wordI] = src[wordI]

    else:
        raise NotImplementedError(dst.__class__, src.__class__)


class AllocaInstCell():

    def __init__(self, waveLog: Optional[VcdWriter], inst: AllocaInst, v: HConst):
        self.v = v
        self.inst = inst
        self.waveLog = waveLog

    def setValue(self, v: HConst, nowTime: int):
        waveLog = self.waveLog
        if waveLog and self.inst in waveLog._idScope:
            waveLog.logChange(nowTime, self.inst, v, None)
        self.v = v


def _decodeOpcode_Alloca(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    alloca: AllocaInst = InstructionToAllocaInst(instr)
    assert alloca is not None, instr
    assert alloca.getNumOperands() == 1, alloca  # expects only alignment value
    Ty = alloca.getAllocatedType()
    intTy = TypeToIntegerType(Ty)
    arrTy = TypeToArrayType(Ty)
    if intTy is not None:
        v = HBits(intTy.getIntegerBitWidth()).from_py(None)
    elif arrTy is not None:
        arrTy: ArrayType
        pyT = HBits(arrTy.getElementType().getScalarSizeInBits())[arrTy.getNumElements()]

        def _opcode_AllocaArray(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            regs[instr] = AllocaInstCell(waveLog, instr, pyT.from_py(None))

        return _opcode_AllocaArray

    elif Ty.isDoubleTy():
        v = interpret._getHFloatTmp().from_py(None)
    else:
        raise NotImplementedError(instr)

    def _opcode_Alloca(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
        regs[instr] = AllocaInstCell(waveLog, instr, v)

    return _opcode_Alloca


def _decodeOpcode_Freeze(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    freeze = InstructionToFreezeInst(instr)
    assert freeze is not None, instr
    ops = interpret._decodeInstArguments(instr.iterOperandValues())
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
                if isinstance(base, AllocaInstCell):
                    baseArrayTy = base.v._dtype
                    baseArrayTyIsLlvm = False
                elif isinstance(base, HConst):
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
            res: AllocaInstCell = regs[srcPtr]
            assert res.v._dtype.bit_length() == width, (debugScope, srcPtr)
            return res.v

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
    elif isinstance(base, AllocaInstCell):
        assert isinstance(base.v, HArrayConst), base
        return base.v[i0]
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


def decodeOpcode_Load(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    load = InstructionToLoadInst(instr)
    assert load is not None, instr
    srcPtr, = load.iterOperandValues()
    srcPtrAsArg = ValueToArgument(srcPtr)
    if srcPtrAsArg is None:
        # load with GEP from GlobalVariable
        width = instr.getType().getScalarSizeInBits()
        srcAlloca = ValueToAllocaInst(srcPtr)
        if srcAlloca is not None:
            srcAlloca: AllocaInst
            streamOffsetMd = srcAlloca.getMetadata(interpret.strCtx.addStringRef(StreamChannelProps.METADATA_NAME_TMP_VAR_DATA_OFFSET))
            if streamOffsetMd is not None:
                return interpret.streamIoHandler._decodeLoadFromStreamTmpVar_offset(instr, srcAlloca, streamOffsetMd)

        def _opcode_Load_fromLocal(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            res = _getItemFromLocalPointer(regs, srcPtr, width, instr)
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _opcode_Load_fromLocal
    else:

        t = TypeToPointerType(srcPtrAsArg.getType())
        argI = t.getAddressSpace() - 1
        ioValues = interpret.fnArgs[argI]
        ioMd: HwtHlsIoMetadata = interpret.ioMetadata[argI]
        isBlocking = ioMd.hasBlockingLoad
        if not isBlocking:
            w = instr.getType().getScalarSizeInBits()
            nopVal = HBits(w).from_py(0, 1 << (w - 1))  # only vld=0 valid
        streamProps: Optional[StreamChannelProps] = interpret.streamIoHandler._streamProps.get(srcPtrAsArg, None)
        if streamProps is not None:
            assert ioMd.ioVectorization is None, instr
            busWordWidth = streamProps.getWidthOfBusWord()
            ldWidth = instr.getType().getIntegerBitWidth()
            if ldWidth != busWordWidth:
                # this is load of just 1 segment from segmented bus
                assert ldWidth < busWordWidth, instr
                assert ldWidth == busWordWidth // streamProps.segmentCnt, instr
                return interpret.streamIoHandler._decodeLlvmIrLoadOfSingleSegmentFromSegmentedBus(interpret, instr, srcPtrAsArg, streamProps)

        elif ioMd.ioVectorization is not None:
            raise NotImplementedError(instr)

        def _opcode_Load_fromIo(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            try:
                res = next(ioValues)
            except StopIteration:
                raise SimIoUnderflowErr()
            if res is NOP:
                assert not isBlocking, instr
                res = nopVal
            else:
                assert isinstance(res, HConst) and \
                    isinstance(res._dtype, HBits) and\
                    res._dtype.signed is None, ("Input value must be must be not-signed BitsVal", instr, res)
                if isBlocking:
                    assert res._dtype.bit_length() == instr.getType().getScalarSizeInBits(), (
                        "Input value must be must have correct width", instr, res)
                else:
                    assert res._dtype.bit_length() + 1 == instr.getType().getScalarSizeInBits(), (
                        "Input value must be must have correct width", instr, res)
                    res = b1._concat(res)  # concat with valid=1
            # print("  load", instr, res)
            if waveLog is not None:
                # update for value of input port itinterpret
                waveLog.logChange(nowTime, srcPtrAsArg, res, None)
            # update for result of loainterpretstruction
            interpret._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _opcode_Load_fromIo


def decodeOpcode_Store(interpret: "LlvmIrInterpret", instr: Instruction) -> LlvmIrInstrFunction:
    """
    Convert StoreInst to a python function which will perform the store operation on propper object.
    """
    store = InstructionToStoreInst(instr)
    assert store is not None, instr
    _v, dstPtr = store.iterOperandValues()
    vAsConstInt = ValueToConstantInt(_v)
    vIsConst = True
    if vAsConstInt is not None:
        pyT = HBits(vAsConstInt.getType().getScalarSizeInBits())
        _v = int(vAsConstInt.getValue())
        if _v < 0:  # convert to unsigned
            _v = pyT.all_mask() + _v + 1
        _v = pyT.from_py(_v)
    elif ValueToUndefValue(_v) is not None:  # :note: class PoisonValue final : public UndefValue
        Ty = _v.getType()
        arrTy = TypeToArrayType(Ty)
        if arrTy is not None:
            pyT = HBits(arrTy.getElementType().getScalarSizeInBits())[arrTy.getNumElements()]
        else:
            pyT = HBits(_v.getType().getScalarSizeInBits())
        _v = pyT.from_py(None)
    else:
        vAsConstFP = ValueToConstantFP(_v)
        if vAsConstFP:
            _v = interpret._getHFloatTmp().from_py(float(vAsConstFP.getValue()))
        else:
            vIsConst = False

    dstPtrInstr = ValueToInstruction(dstPtr)
    if dstPtrInstr is not None:
        dstGep = InstructionToGetElementPtrInst(dstPtrInstr)
        if dstGep is not None:

            def _opcode_Store_gep(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                """
                Store into an array using index.
                """
                if vIsConst:
                    v = _v
                else:
                    v = regs[_v]
                dstPtr, addr = regs[dstGep]

                if isinstance(dstPtr, SimRam):
                    dstPtr.write(addr, v)
                    return

                dstPtrAsArg = ValueToArgument(dstPtr)
                if dstPtrAsArg is not None:
                    raise NotImplementedError()

                alloca = ValueToAllocaInst(dstPtr)
                if alloca is not None:
                    raise NotImplementedError()
                raise NotImplementedError(dstGep)

            return _opcode_Store_gep

    dstPtrAsArg = ValueToArgument(dstPtr)
    if dstPtrAsArg is not None:
        t = TypeToPointerType(dstPtrAsArg.getType())
        argI = t.getAddressSpace() - 1
        ioMd: HwtHlsIoMetadata = interpret.ioMetadata[argI]
        ioValues = interpret.fnArgs[argI]
        segmentWidth = ioMd.writeWordWidth
        w = store.getAccessType().getIntegerBitWidth()
        laneCnt = HwIoProxyScalarVectorized.getLaneCntFromWidth(ioMd, segmentWidth, w)

        if laneCnt == 1:

            def _opcode_Store_toScalarIo(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                if vIsConst:
                    v = _v
                else:
                    v = regs[_v]

                ioValues.append(v)
                if waveLog is not None:
                    # update for value of output port
                    waveLog.logChange(nowTime, dstPtrAsArg, v, None)

            return _opcode_Store_toScalarIo

        else:
            if vIsConst:
                _v = tuple(splitConstBitsToLanes(_v, laneCnt, segmentWidth))
            undef = HBits(segmentWidth).from_py(None)
            def _opcode_Store_toVectorIo(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                if vIsConst:
                    v = _v
                else:
                    v = regs[_v]
                    v = splitConstBitsToLanes(v, laneCnt, segmentWidth)

                ioValues.extend(v)
                if waveLog is not None:
                    # update for value of output port
                    waveLog.logChange(nowTime, dstPtrAsArg, v[-1] if v else undef, None)
                        

            return _opcode_Store_toVectorIo

    else:
        alloca = ValueToAllocaInst(dstPtr)
        if alloca is not None:

            def _opcode_Store_toAlloca(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                if vIsConst:
                    v = _v
                else:
                    v = regs[_v]
                curV: AllocaInstCell = regs[alloca]
                allocatedWidth = curV.v._dtype.bit_length()
                storeWidth = v._dtype.bit_length()
                if allocatedWidth == storeWidth:
                    curV.setValue(v, nowTime)
                else:
                    curV.setValue(curV.v[allocatedWidth: storeWidth]._concat(v), nowTime)

            return _opcode_Store_toAlloca

        raise NotImplementedError(instr)
