from datetime import datetime
import re
from typing import Union, Optional, Callable, Sequence

from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.hdlType import HdlType
from hwtHls.code import ctlz, zext, hwUMax, hwUMin, hwSMax, hwSMin, fshl, fshr, \
    cttz, ctpop
from hwtHls.llvm.llvmIr import Function, BasicBlock, InstructionToCallInst, \
    InstructionToPHINode, ValueToBasicBlock, \
    ValueToConstantInt, ValueToFunction, ValueToInstruction, Instruction, \
    InstructionToLoadInst, InstructionToStoreInst, ValueToArgument, ValueToGlobalValue, \
    ValueToConstantFP, TypeToPointerType, TypeToIntegerType, IntegerType, \
    LLVMStringContext, ValueToUndefValue, TypeToArrayType, ArrayType, \
    Intrinsic, ValueToAllocaInst, ValueToConstantArray, ValueToConstantDataArray, IsStreamIo, Value, PHINode, \
    Module, Argument, InstructionToGetElementPtrInst, HwtHlsIoMetadata, HwtHlsIoMetadata_get, \
    AllocaInst, StreamChannelProps, LlvmCompilationBundle, TargetOpcode, Type
from hwtHls.platform.platform import ComponentGeneratorDict
from hwtHls.ssa.analysis.llvmIrInterpretCall import _decodeOpcode_CallInst
from hwtHls.ssa.analysis.llvmIrInterpretInt import _decodeOpcode_ICmpInst, \
    _decodeOpcode_SelectInst, _makeDecodeOpcodeFunction_BinaryOperator, \
    _decodeOpcode_CastInst, _opcode_Intrinsic_usub_sat, \
    _opcode_Intrinsic_uadd_sat, _opcode_Intrinsic_sadd_sat, \
    _opcode_Intrinsic_ssub_sat, _opcode_Intrinsic_uadd_with_overflow, \
    _opcode_Intrinsic_usub_with_overflow, _opcode_Intrinsic_sadd_with_overflow, \
    _opcode_Intrinsic_ssub_with_overflow
from hwtHls.ssa.analysis.llvmIrInterpretJump import _decodeOpcode_Br, \
    _decodeOpcode_Switch, _decodeOpcode_RetInst
from hwtHls.ssa.analysis.llvmIrInterpretMem import _decodeOpcode_GetElementPtr, \
    _decodeOpcode_Freeze, _decodeOpcode_Alloca, _getItemFromLocalPointer, \
    _decodeOpcode_ExtractValueInst
from hwtHls.ssa.analysis.llvmIrInterpretStreamIo import LlvmIrInterpretStreamIo
from hwtHls.ssa.analysis.llvmIrInterpretUtils import BINARY_OPS_TO_FN, \
    _prepareWaveWriterTopIo, VcdLlvmIrCodelineFormatter, \
    VcdLlvmIrSimTimeFormatter, VcdLlvmIrBBFormatter, RE_NON_ID, PtrAddrTuple, \
    SimIoUnderflowErr, LlvmIrInstrFunction, LlvmIrInterpretArgs, AnyInstrOpcode
from hwtHls.ssa.translation.toLlvm import PyObjectPlaceholderList
from hwtLib.abstract.sim_ram import SimRam
from hwtSimApi.agents.base import NOP
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.triggers import StopSimumulation
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import VcdBitsFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import to_unsigned


class LlvmIrInterpret():
    """
    An interpret of the LLVM IR. Can run LLVM IR and log changes into wave.
    It first analyzes the LLVM IR and converts each instruction to a optimized python
    function to avoid overhead associated with lookup of intrinsic, constant parsing etc.
    
    :ivar F: llvm Function which will be executed by this interpret
    :ivar strCtx: string context for llvm string allocations during initialization of waveLog and metadata search
    :ivar timeStep: time step used for wave logging
    :ivar waveLog: writer for wave logging
    :ivar codelineOffset: offset from beginning from the MIR .ll file where function body starts
    """
    OPCODE_INT_TO_ENUM: dict[int, AnyInstrOpcode] = {
        **{i.value: i for i in Instruction.MemoryOps},
        **{i.value: i for i in Instruction.BinaryOps},
        **{i.value: i for i in Instruction.OtherOps},
        **{i.value: i for i in Instruction.TermOps},
        **{i.value: i for i in Instruction.CastOps},
    }
    INTRINSIC_ID_TO_FN = {
        Intrinsic.ctlz: lambda ops: zext(ctlz(*ops), ops[0]._dtype.bit_length()),
        Intrinsic.cttz: lambda ops: zext(cttz(*ops), ops[0]._dtype.bit_length()),
        Intrinsic.ctpop: lambda ops: zext(ctpop(*ops), ops[0]._dtype.bit_length()),
        Intrinsic.umax: lambda ops: hwUMax(*ops),
        Intrinsic.umin: lambda ops: hwUMin(*ops),
        Intrinsic.smax: lambda ops: hwSMax(*ops),
        Intrinsic.smin: lambda ops: hwSMin(*ops),
        Intrinsic.fshl: lambda ops: fshl(*ops),
        Intrinsic.fshr: lambda ops: fshr(*ops),
        Intrinsic.usub_sat: _opcode_Intrinsic_usub_sat,
        Intrinsic.uadd_sat: _opcode_Intrinsic_uadd_sat,
        Intrinsic.sadd_sat: _opcode_Intrinsic_sadd_sat,
        Intrinsic.ssub_sat: _opcode_Intrinsic_ssub_sat,
        Intrinsic.uadd_with_overflow: _opcode_Intrinsic_uadd_with_overflow,
        Intrinsic.usub_with_overflow: _opcode_Intrinsic_usub_with_overflow,
        Intrinsic.sadd_with_overflow: _opcode_Intrinsic_sadd_with_overflow,
        Intrinsic.ssub_with_overflow: _opcode_Intrinsic_ssub_with_overflow,
    }
    RE_FP_INTRINSIC_ID = re.compile(r"(hwtHls\.fp\.(unspecialized\.)?([a-zA-Z_0-9]+)\.)")
    # instruction with common handling of operands
    _dispatchDict1: dict[AnyInstrOpcode, Callable] = {
        Instruction.MemoryOps.GetElementPtr: _decodeOpcode_GetElementPtr,
        Instruction.OtherOps.Call: _decodeOpcode_CallInst,
        Instruction.OtherOps.ICmp: _decodeOpcode_ICmpInst,
        Instruction.OtherOps.Select: _decodeOpcode_SelectInst,
        Instruction.OtherOps.Freeze: _decodeOpcode_Freeze,
        Instruction.MemoryOps.Alloca: _decodeOpcode_Alloca,
        Instruction.TermOps.Br: _decodeOpcode_Br,
        Instruction.TermOps.Switch: _decodeOpcode_Switch,
        Instruction.TermOps.Ret: _decodeOpcode_RetInst,
        Instruction.OtherOps.ExtractValue: _decodeOpcode_ExtractValueInst,
        **{opcode: _decodeOpcode_CastInst
           for opcode in (Instruction.CastOps.BitCast,
                          Instruction.CastOps.Trunc,
                          Instruction.CastOps.ZExt,
                          Instruction.CastOps.SExt)
        },
        **{opcode: _makeDecodeOpcodeFunction_BinaryOperator(fn)
           for opcode, fn in BINARY_OPS_TO_FN.items()
        }
    }

    def __init__(self, llvm: LlvmCompilationBundle,
                 placeholderObjectSlots: PyObjectPlaceholderList,
                 componentGenerators: ComponentGeneratorDict,
                 _getHFloatType: Callable[Optional[Type], HdlType],
                 fnArgs: LlvmIrInterpretArgs,
                 timeStep: int=CLK_PERIOD):
        assert llvm.main
        self.F = llvm.main
        self.timeStep = timeStep
        self.waveLog: Optional[VcdWriter] = None
        self.strCtx: LLVMStringContext = llvm.strCtx
        self.codelineOffset: int = 0
        self.fnArgs: Optional[LlvmIrInterpretArgs] = None
        self.ioMetadata: list[HwtHlsIoMetadata] = HwtHlsIoMetadata_get(self.F)
        self.streamIoHandler = LlvmIrInterpretStreamIo(self)
        self.streamIoHandler._loadStreamChannelFormatInfo(self.F)
        self.placeholderObjectSlots = placeholderObjectSlots
        self._getHFloatType = _getHFloatType
        self.componentGenerators = componentGenerators
        self.fnArgs = fnArgs
        # instructions with special handling of operands
        self._dispatchDict0: dict[AnyInstrOpcode, Callable] = {
            Instruction.MemoryOps.Load: self._decodeOpcode_Load,
            Instruction.MemoryOps.Store: self._decodeOpcode_Store,
            Instruction.TermOps.Unreachable: self._decodeOpcode_UnreachableInst,
        }
        d = self._dispatchDict0
        for k, cg in componentGenerators.items():
            if isinstance(k, TargetOpcode):
                continue
            d[k] = cg.llvmIrInterpretDecode
        # dictionary which holds list of compiled function exec. functions for each block
        self._decodedBlocks: dict[BasicBlock, list[tuple[Instruction, LlvmIrInstrFunction]]] = {}
        # dictionary (src, dst block) -> tuples (phi, new value)
        self._decodedBlockPhis: dict[tuple[BasicBlock, BasicBlock],
                                     list[tuple[PHINode, Union[HBitsConst, "HFloatTmpConst", Instruction]]]
                                     ] = {}
        # object used as a key for current block value in wave logger
        self._simBlockLabel: Optional[object] = None
        self.nowTime: Optional[int] = None

    def installWaveLog(self, waveLog: VcdWriter, codelineOffset: int=0):
        self.waveLog = waveLog
        self.codelineOffset = codelineOffset

    def _prepareVcdWriter(self):
        waveLog = self.waveLog
        F = self.F
        strCtx = self.strCtx
        assert waveLog is not None
        assert strCtx is not None
        waveLog.date(datetime.now())
        waveLog.timescale(1)
        instrCodeline: dict[Instruction, int] = {}
        simCodelineLabel = object()
        simTimeLabel = object()
        simBlockLabel = object()
        with waveLog.varScope("__sim__") as simScope:
            simScope.addVar(simCodelineLabel, "codeline", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrCodelineFormatter(instrCodeline))
            simScope.addVar(simTimeLabel, "step", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrSimTimeFormatter(self.timeStep))
            simScope.addVar(simBlockLabel, "block", VCD_SIG_TYPE.ENUM, 0, VcdLlvmIrBBFormatter())

        _prepareWaveWriterTopIo(waveLog, strCtx, F)
        codelineOffset = self.codelineOffset
        with waveLog.varScope(F.getName().str().replace(".", "_")) as fnScope:
            for bb in F:
                for instr in bb:
                    instr: Instruction
                    instrCodeline[instr] = codelineOffset
                    codelineOffset += 1
                    t = TypeToIntegerType(instr.getType())
                    if t is None:
                        continue
                    name = " ".join(instr.printAsOperand().split(" ")[1:]).strip()
                    name = RE_NON_ID.sub("_", name)
                    name = name.lstrip("_")
                    if not name:
                        instr.setName(strCtx.addTwine(""))
                        name = " ".join(instr.printAsOperand().split(" ")[1:]).strip()
                        name = RE_NON_ID.sub("_", name)
                        assert name, name

                    fnScope.addVar(instr, name, VCD_SIG_TYPE.WIRE, t.getBitWidth(), VcdBitsFormatter())
                codelineOffset += 2

        waveLog.enddefinitions()
        return instrCodeline, simCodelineLabel, simTimeLabel, simBlockLabel

    def _decodePhiArgument(self, phi:PHINode, v: Value):
        vvConst = ValueToConstantInt(v)
        if vvConst is not None:
            pyT = HBits(vvConst.getType().getScalarSizeInBits())
            v = int(vvConst.getValue())
            if v < 0:  # convert to unsigned
                v = pyT.all_mask() + v + 1
            v = pyT.from_py(v)
            return v

        vvInstr = ValueToInstruction(v)
        if vvInstr is not None:
            return vvInstr

        vvUndef = ValueToUndefValue(v)
        if vvUndef is not None:
            pyT = HBits(vvUndef.getType().getScalarSizeInBits())
            v = pyT.from_py(None)
            return v

        vvGlobalValue = ValueToGlobalValue(v)
        if vvGlobalValue is not None:
            return PtrAddrTuple((vvGlobalValue, 0))

        vvConstFP = ValueToConstantFP(v)
        if vvConstFP is not None:
            return self._getHFloatTmp().from_py(float(vvConstFP.getValue()))

        raise NotImplementedError("NotImplemented type of value", phi, v)

    def _runBlockPhis(self, predBb: BasicBlock, bb: BasicBlock,
                      waveLog: Optional[VcdWriter],
                      regs: dict[Instruction, HConst], nowTime: int):
        """
        Atomically evaluate PHIs at the top of the block.
        """
        # print("_runBlockPhis", bb.getName().str())
        assert bb is not None, predBb
        # print(bb.printAsOperand())
        newPhiVals = []
        for phi, v in self._decodedBlockPhis[(predBb, bb)]:
            if isinstance(v, Instruction):
                v = regs[v]

            newPhiVals.append((phi, v))

        for phi, v in newPhiVals:
            # print("_runBlockPhis", phi, v)
            self._storeInstrResult(waveLog, nowTime, regs, phi, v)
            # regs[phi] = v

    def _storeInstrResult(self, waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst],
                     instr: Instruction, res: Union[HBitsConst, "HFloatTmpConst"]):
        if waveLog is not None:
            if isinstance(res, HConst):
                waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res

    def _decodeInstArguments(self, operandValues: Sequence[Value]):
        # prepare values for arguments
        ops: list[Union[HConst, BasicBlock, Function]] = []
        for v in operandValues:
            vAsConst = ValueToConstantInt(v)
            if vAsConst is not None:
                pyT = HBits(vAsConst.getType().getScalarSizeInBits())
                v = int(vAsConst.getValue())
                if v < 0:  # convert to unsigned
                    v = pyT.all_mask() + v + 1
                v = pyT.from_py(v)
                ops.append(v)
                continue

            vAsUndef = ValueToUndefValue(v)
            if vAsUndef is not None:
                pyT = HBits(vAsUndef.getType().getScalarSizeInBits())
                ops.append(pyT.from_py(None))
                continue

            vAsInstr = ValueToInstruction(v)
            if vAsInstr is not None:
                ops.append(vAsInstr)
                continue

            vAsConstFP = ValueToConstantFP(v)
            if vAsConstFP:
                ops.append(self._getHFloatTmp().from_py(float(vAsConstFP.getValue())))
                continue

            vAsBB = ValueToBasicBlock(v)
            if vAsBB is not None:
                ops.append(vAsBB)
                continue

            vAsFunction = ValueToFunction(v)
            if vAsFunction is not None:
                ops.append(vAsFunction)
                continue

            vAsGlobalValue = ValueToGlobalValue(v)
            if vAsGlobalValue is not None:
                ops.append(vAsGlobalValue)
                continue
            vAsArg = ValueToArgument(v)
            if vAsArg is not None:
                vAsArg:Argument
                ops.append(vAsArg)
                continue
            else:
                raise NotImplementedError(v)
        return ops

    def _prepareInstrArguments(self, args: list[Union[HConst, Instruction, BasicBlock, Function]], regs: dict[Instruction, HConst]) -> list[Union[HConst, BasicBlock, Function]]:
        # prepare values for arguments
        ops: list[Union[HConst, Instruction, BasicBlock, Function]] = []
        for v in args:
            if not isinstance(v, HConst):
                v = regs[v]
            ops.append(v)

        return ops

    def _decodeOpcode_Load(self, _, instr: Instruction) -> LlvmIrInstrFunction:
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
                streamOffsetMd = srcAlloca.getMetadata(self.strCtx.addStringRef(StreamChannelProps.METADATA_NAME_TMP_VAR_DATA_OFFSET))
                if streamOffsetMd is not None:
                    return self.streamIoHandler._decodeLoadFromStreamTmpVar_offset(instr, srcAlloca, streamOffsetMd)

            def _opcode_Load(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                res = _getItemFromLocalPointer(regs, srcPtr, width, instr)
                self._storeInstrResult(waveLog, nowTime, regs, instr, res)

        else:

            t = TypeToPointerType(srcPtrAsArg.getType())
            argI = t.getAddressSpace() - 1
            ioValues = self.fnArgs[argI]
            ioMd: HwtHlsIoMetadata = self.ioMetadata[argI]
            isBlocking = ioMd.hasBlockingLoad
            if not isBlocking:
                w = instr.getType().getScalarSizeInBits()
                nopVal = HBits(w).from_py(0, 1 << (w - 1))  # only vld=0 valid
            streamProps: Optional[StreamChannelProps] = self.streamIoHandler._streamProps.get(srcPtrAsArg, None)
            if streamProps is not None:
                busWordWidth = streamProps.getWidthOfBusWord()
                ldWidth = instr.getType().getIntegerBitWidth()
                if ldWidth != busWordWidth:
                    # this is load of just 1 segment from segmented bus
                    assert ldWidth < busWordWidth, instr
                    assert ldWidth == busWordWidth // streamProps.segmentCnt, instr
                    return self.streamIoHandler._decodeLlvmIrLoadOfSingleSegmentFromSegmentedBus(self, instr, srcPtrAsArg, streamProps)

            def _opcode_Load(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
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
                    # update for value of input port itself
                    waveLog.logChange(nowTime, srcPtrAsArg, res, None)
                # update for result of load instruction
                self._storeInstrResult(waveLog, nowTime, regs, instr, res)

        return _opcode_Load

    def _decodeOpcode_Store(self, _, instr: Instruction) -> LlvmIrInstrFunction:
        """
        Convert StoreInst to a python function which will do just that.
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
            pyT = HBits(_v.getType().getScalarSizeInBits())
            _v = pyT.from_py(None)
        else:
            vAsConstFP = ValueToConstantFP(_v)
            if vAsConstFP:
                _v = self._getHFloatTmp().from_py(float(vAsConstFP.getValue()))
            else:
                vIsConst = False

        dstPtrInstr = ValueToInstruction(dstPtr)
        if dstPtrInstr is not None:
            dstGep = InstructionToGetElementPtrInst(dstPtrInstr)
            if dstGep is not None:

                def _opcode_Store_gep(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
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
            ioValues = self.fnArgs[t.getAddressSpace() - 1]

            def _opcode_Store(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                if vIsConst:
                    v = _v
                else:
                    v = regs[_v]
                ioValues.append(v)
                if waveLog is not None:
                    # update for value of output port
                    waveLog.logChange(nowTime, dstPtrAsArg, v, None)

            return _opcode_Store
        else:
            alloca = ValueToAllocaInst(dstPtr)
            if alloca is not None:

                def _opcode_Store(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
                    if vIsConst:
                        v = _v
                    else:
                        v = regs[_v]
                    curV = regs[alloca]
                    allocatedWidth = curV._dtype.bit_length()
                    storeWidth = v._dtype.bit_length()
                    if allocatedWidth == storeWidth:
                        regs[alloca] = v
                    else:
                        regs[alloca] = curV[allocatedWidth: storeWidth]._concat(v)

                return _opcode_Store

            raise NotImplementedError(instr)

    def _decodeOpcode_UnreachableInst(self, _, instr: Instruction) -> LlvmIrInstrFunction:

        def _opcode_UnreachableInst(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            raise AssertionError("UnreachableInst should have never been reached", nowTime, instr)

        return  _opcode_UnreachableInst

    def _decodeLlvmInstr(self, instr: Instruction) -> LlvmIrInstrFunction:
        # check for instructions which require special handling of operands
        opc = instr.getOpcode()
        opc = self.OPCODE_INT_TO_ENUM[opc]
        opcodeFn = self._dispatchDict0.get(opc, None)
        if opcodeFn is not None:
            return opcodeFn(self, instr)

        callInstr = InstructionToCallInst(instr)
        if callInstr is not None:
            if IsStreamIo(callInstr):
                return self.streamIoHandler._decodeLlvmIrFunctionInstrStreamIo(self, callInstr)

        opcodeFn = self._dispatchDict1.get(opc, None)
        if opcodeFn is not None:
            return opcodeFn(self, instr)

        raise NotImplementedError(instr)

    def _decodeBlocks(self):
        decodedBlockPhis = self._decodedBlockPhis
        for bb in self.F:
            bb: BasicBlock
            for predBb in bb.predecessors():
                phis = decodedBlockPhis[(predBb, bb)] = []
                for instr in bb:
                    instr: Instruction
                    phi = InstructionToPHINode(instr)
                    if phi is None:
                        break
                    v = phi.getIncomingValueForBlock(predBb)
                    assert v is not None, phi
                    v = self._decodePhiArgument(phi, v)
                    phis.append((phi, v))

            bbDecoded = self._decodedBlocks[bb] = []
            for instr in bb:
                instr: Instruction
                if InstructionToPHINode(instr):
                    continue
                iDecoded = self._decodeLlvmInstr(instr)
                assert iDecoded is not None, instr
                bbDecoded.append((instr, iDecoded))

    def _run(self, bb: BasicBlock, regs: dict[Instruction, HConst], wallTime:Optional[int]):
        waveLog = self.waveLog
        timeStep = self.timeStep
        if waveLog is not None:
            _, simCodelineLabel, simTimeLabel, self._simBlockLabel = self._prepareVcdWriter()
        else:
            simCodelineLabel = None
            simTimeLabel = None
            self._simBlockLabel = None
        decodedBlocks = self._decodedBlocks
        bbDecoded = decodedBlocks[bb]
        self.nowTime = nowTime = -timeStep
        while True:
            for instr, instrDecoded in bbDecoded:
                nowTime += timeStep
                self.nowTime = nowTime
                if waveLog is not None:
                    waveLog.logChange(nowTime, simTimeLabel, nowTime, None)
                    waveLog.logChange(nowTime, simCodelineLabel, instr, None)

                nextBb = instrDecoded(waveLog, nowTime, regs)
                if wallTime is not None and nowTime >= wallTime:
                    raise StopSimumulation()
                if nextBb is not None:
                    bb = nextBb
                    bbDecoded = decodedBlocks[nextBb]
                    break

    @staticmethod
    def _initGlobalsFromIr(M: Module, regs: dict[Instruction, HConst]):
        for gv in M.globals():
            v = gv.getOperand(0)
            t: ArrayType = TypeToArrayType(v.getType())
            assert t is not None, v
            _v = ValueToConstantArray(v)
            if _v is None:
                _v = ValueToConstantDataArray(v)

            assert _v is not None, v
            v = _v
            elmT = t.getElementType()
            elmTyInt: IntegerType = TypeToIntegerType(elmT)
            if elmTyInt:
                width = elmTyInt.getIntegerBitWidth()
                elmTyHwt = HBits(elmTyInt.getIntegerBitWidth())
                arrTyHwt = elmTyHwt[t.getNumElements()]
                items = []
                for i in v:
                    i = int(ValueToConstantInt(i).getValue())
                    if i < 0:
                        i = to_unsigned(i, width)
                    items.append(i)
                instanceOfGv = arrTyHwt.from_py(items)
            else:
                assert elmT.isDoubleTy(), v
                instanceOfGv = arrTyHwt.from_py([float(ValueToConstantFP(i).getValue()) for i in v])
            regs[gv] = instanceOfGv

    def run(self, wallTime:Optional[int]=None):
        F = self.F

        regs: dict[Instruction, HConst] = {}
        self._initGlobalsFromIr(F.getParent(), regs)
        for a in F.args():
            a: Argument
            t = TypeToPointerType(a.getType())
            ioValues = self.fnArgs[t.getAddressSpace() - 1]
            regs[a] = ioValues

        self._decodeBlocks()
        bb: BasicBlock = F.getEntryBlock()
        self._run(bb, regs, wallTime)

