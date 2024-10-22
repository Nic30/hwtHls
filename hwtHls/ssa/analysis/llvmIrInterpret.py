from datetime import datetime
from io import StringIO
from itertools import islice
from operator import and_, or_, xor, add, mul, sub, floordiv, rshift, lshift
import re
from typing import Tuple, Generator, Union, List, Optional, Dict

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.const import HConst
from hwt.pyUtils.arrayQuery import grouper
from hwtHls.llvm.llvmIr import Function, BasicBlock, BinaryOperator, InstructionToBranchInst, InstructionToCallInst, \
    InstructionToGetElementPtrInst, InstructionToICmpInst, InstructionToPHINode, ValueToBasicBlock, \
    ValueToConstantInt, ValueToFunction, ValueToInstruction, Instruction, InstructionToBinaryOperator, \
    InstructionToLoadInst, InstructionToStoreInst, ValueToArgument, TypeToPointerType, TypeToIntegerType, \
    Argument, LLVMStringContext, MDOperand, MetadataAsMDNode, MetadataAsValueAsMetadata, Value, User, \
    UserToInstruction, InstructionToSelectInst, ValueToUndefValue, InstructionToCastInst, InstructionToSwitchInst, \
    Intrinsic, InstructionToFreezeInst
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.triggers import StopSimumulation
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import VcdBitsFormatter, \
    LogValueFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter
from hwtHls.code import ctlz, zext, hwUMax, hwUMin, hwSMax, hwSMin, fshl, fshr


class SimIoUnderflowErr(Exception):
    """
    This exception is raised when there is not enough data on some IO, it may mean that
    the simulation did finish or simulated function is missing some data
    """


# LLVM_BIN_OP_TO_HWT = {
#    TargetOpcode.HWTFPGA_ADD: AllOps.ADD,
#    TargetOpcode.HWTFPGA_SUB: AllOps.SUB,
#    TargetOpcode.HWTFPGA_MUL: AllOps.MUL,
#    TargetOpcode.HWTFPGA_UDIV: AllOps.DIV,
#    TargetOpcode.HWTFPGA_AND: AllOps.AND,
#    TargetOpcode.HWTFPGA_OR: AllOps.OR,
#    TargetOpcode.HWTFPGA_XOR: AllOps.XOR,
#    TargetOpcode.HWTFPGA_NOT: AllOps.NOT,
# }
RE_ID = re.compile('[^0-9a-zA-Z_]+')
BINARY_OPS_TO_FN = {
    Instruction.BinaryOps.And: and_,
    Instruction.BinaryOps.Or: or_,
    Instruction.BinaryOps.Xor: xor,
    Instruction.BinaryOps.Add: add,
    Instruction.BinaryOps.Sub: sub,
    Instruction.BinaryOps.Mul: mul,
    Instruction.BinaryOps.UDiv: floordiv,
    Instruction.BinaryOps.LShr: rshift,  # logical shift right
    Instruction.BinaryOps.Shl: lshift,
}


class VcdLlvmIrBBFormatter(LogValueFormatter):

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: BasicBlock, updater, t: int, out: StringIO):
        # val = newVal.getName().str()
        name = newVal.printAsOperand()[len("label "):]
        name = RE_ID.sub("_", name)
        out.write(f"s{name:s} {self.vcdId:s}\n")


class VcdLlvmIrCodelineFormatter(LogValueFormatter):

    def __init__(self, instrCodeline: Dict[Instruction, int]):
        self.instrCodeline = instrCodeline

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: Instruction, updater, t: int, out: StringIO):
        out.write(f"b{self.instrCodeline[newVal]:b} {self.vcdId:s}\n")


class VcdLlvmIrSimTimeFormatter(LogValueFormatter):

    def __init__(self, step: int):
        self.step = step

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: int, updater, t: int, out: StringIO):
        # val = newVal.getName().str()
        out.write(f"b{newVal//self.step:b} {self.vcdId:s}\n")


def _findLoadOrStoreWidthForValue(v: Value) -> int:
    for u in v.users():
        u: User
        userInstr = UserToInstruction(u)
        assert userInstr is not None, (v, u)
        ld = InstructionToLoadInst(userInstr)
        if ld is not None:
            return ld.getType().getIntegerBitWidth()
        st = InstructionToStoreInst(userInstr)
        if st is not None:
            return st.getOperand(0).getType().getIntegerBitWidth()

        gep = InstructionToGetElementPtrInst(userInstr)
        if gep is not None:
            raise NotImplementedError()

        raise NotImplementedError(userInstr)

    raise AssertionError("value has no use can not infer pointee width", v)


def _prepareWaveWriterTopIo(waveLog: VcdWriter, strCtx: LLVMStringContext, fn: Function):
    with waveLog.varScope("args") as argScope:
        argAddrWidths = fn.getMetadata(strCtx.addStringRef("hwtHls.param_addr_width"))
        assert argAddrWidths.getNumOperands() == 2
        assert argAddrWidths.getOperand(0).get() == argAddrWidths, argAddrWidths
        argAddrWidths = MetadataAsMDNode(argAddrWidths.getOperand(1).get())
        assert argAddrWidths.getNumOperands() == fn.arg_size()
        for arg, argAddrWidth in zip(fn.args(), argAddrWidths.iterOperands()):
            arg: Argument
            argAddrWidth: MDOperand
            argAddrWidth = MetadataAsValueAsMetadata(argAddrWidth.get())
            argAddrWidth = ValueToConstantInt(argAddrWidth.getValue())
            argAddrWidth = int(argAddrWidth.getValue())
            if argAddrWidth != 0:
                raise NotImplementedError(arg, argAddrWidth)
            name = RE_ID.sub("_", arg.getName().str())
            argWidth = _findLoadOrStoreWidthForValue(arg)
            argScope.addVar(arg, name, VCD_SIG_TYPE.WIRE, argWidth, VcdBitsFormatter())


LlvmIrInterpretArgs = Tuple[Generator[Union[int, HConst], None, None], List[HConst], ...]


class LlvmIrInterpret():
    """
    An interpret of the LLVM IR
    
    :ivar MF: llvm MachineInstance function which will be executed by this interpret
    :ivar timeStep: time step used for wave logging
    :ivar waveLog: writer for wave logging
    :ivar strCtx: string context for llvm string allocations during initialization of waveLog
    :ivar codelineOffset: offset from beginning from the MIR .ll file where function body starts
    """

    def __init__(self, F: Function, timeStep: int=CLK_PERIOD):
        self.F = F
        self.timeStep = timeStep
        self.waveLog: Optional[VcdWriter] = None
        self.strCtx: Optional[LLVMStringContext] = None
        self.codelineOffset: int = 0

    def installWaveLog(self, waveLog: VcdWriter, strCtx: LLVMStringContext, codelineOffset: int=0):
        self.waveLog = waveLog
        self.strCtx = strCtx
        self.codelineOffset = codelineOffset

    def _prepareVcdWriter(self):
        waveLog = self.waveLog
        F = self.F
        strCtx = self.strCtx
        assert waveLog is not None
        assert strCtx is not None
        waveLog.date(datetime.now())
        waveLog.timescale(1)
        instrCodeline: Dict[Instruction, int] = {}
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
                    name = RE_ID.sub("_", name)
                    name = name.lstrip("_")
                    fnScope.addVar(instr, name, VCD_SIG_TYPE.WIRE, t.getBitWidth(), VcdBitsFormatter())
                codelineOffset += 2

        waveLog.enddefinitions()
        return instrCodeline, simCodelineLabel, simTimeLabel, simBlockLabel

    def _runBlockPhis(self, predBb: BasicBlock, bb: BasicBlock, waveLog: Optional[VcdWriter], regs: Dict[Instruction, HConst], nowTime: int):
        """
        Atomically evaluate PHIs at the top of the block.
        """
        newPhiVals = []
        for instr in bb:
            phi = InstructionToPHINode(instr)
            if phi is None:
                break
            # special case for PHIs because they may have operands which are undefined
            v = phi.getIncomingValueForBlock(predBb)
            assert v is not None, phi
            vvConst = ValueToConstantInt(v)
            if vvConst is not None:
                pyT = HBits(vvConst.getType().getIntegerBitWidth())
                v = int(vvConst.getValue())
                if v < 0:  # convert to unsigned
                    v = pyT.all_mask() + v + 1
                v = pyT.from_py(v)
                if waveLog is not None:
                    waveLog.logChange(nowTime, phi, v, None)
                newPhiVals.append((phi, v))
                continue

            vvInstr = ValueToInstruction(v)
            if vvInstr is not None:
                v = regs[vvInstr]
                if waveLog is not None:
                    waveLog.logChange(nowTime, phi, v, None)
                newPhiVals.append((phi, v))
                continue

            vvUndef = ValueToUndefValue(v)
            if vvUndef is not None:
                pyT = HBits(vvUndef.getType().getIntegerBitWidth())
                v = pyT.from_py(None)
                if waveLog is not None:
                    waveLog.logChange(nowTime, phi, v, None)
                newPhiVals.append((phi, v))
                continue

            raise NotImplementedError("NotImplemented type of value", phi, v)

        for phi, v in newPhiVals:
            regs[phi] = v

    def _runLlvmIrFunctionInstr(self, waveLog: Optional[VcdWriter],
                                nowTime: int,
                                regs: Dict[Instruction, HConst],
                                instr: Instruction,
                                bb: BasicBlock,
                                fnArgs: LlvmIrInterpretArgs,
                                simBlockLabel: Optional[object]) -> Tuple[Optional[BasicBlock], BasicBlock, bool]:
        """
        :return: bb, isJump
        """
        # check for instructions which require special handling of operands
        load = InstructionToLoadInst(instr)
        if load is not None:
            srcPtr, = load.iterOperandValues()
            srcPtrAsArg = ValueToArgument(srcPtr)
            if srcPtrAsArg is not None:
                t = TypeToPointerType(srcPtrAsArg.getType())
                ioValues = fnArgs[t.getAddressSpace() - 1]
                try:
                    res = next(ioValues)
                except StopIteration:
                    raise SimIoUnderflowErr()

                assert isinstance(res, HConst) and \
                    isinstance(res._dtype, HBits) and\
                    not res._dtype.signed, ("Input value must be must be unsigned BitsVal", instr, res)
                assert res._dtype.bit_length() == instr.getType().getIntegerBitWidth(), (
                    "Input value must be must have correct width", instr, res)
                if waveLog is not None:
                    waveLog.logChange(nowTime, load, res, None)
                regs[instr] = res
                return bb, False
            else:
                raise NotImplementedError(instr, srcPtr)

        store = InstructionToStoreInst(instr)
        if store is not None:
            v, dstPtr = store.iterOperandValues()
            vAsConst = ValueToConstantInt(v)
            if vAsConst is not None:
                pyT = HBits(vAsConst.getType().getIntegerBitWidth())
                v = int(vAsConst.getValue())
                if v < 0:  # convert to unsigned
                    v = pyT.all_mask() + v + 1
                v = pyT.from_py(v)
            else:
                v = regs[v]

            dstPtrAsArg = ValueToArgument(dstPtr)
            if dstPtrAsArg is not None:
                t = TypeToPointerType(dstPtrAsArg.getType())
                ioValues = fnArgs[t.getAddressSpace() - 1]
                ioValues.append(v)
                if waveLog is not None:
                    waveLog.logChange(nowTime, dstPtrAsArg, v, None)
                return bb, False
            else:
                raise NotImplementedError(instr)

        # prepare values for argumens
        ops: List[Union[HConst, BasicBlock, Function]] = []
        for v in instr.iterOperandValues():
            vAsConst = ValueToConstantInt(v)
            if vAsConst is not None:
                pyT = HBits(vAsConst.getType().getIntegerBitWidth())
                v = int(vAsConst.getValue())
                if v < 0:  # convert to unsigned
                    v = pyT.all_mask() + v + 1
                v = pyT.from_py(v)
                ops.append(v)
                continue

            vAsUndef = ValueToUndefValue(v)
            if vAsUndef is not None:
                pyT = HBits(vAsUndef.getType().getIntegerBitWidth())
                ops.append(pyT.from_py(None))
                continue

            vAsInstr = ValueToInstruction(v)
            if vAsInstr is not None:
                ops.append(regs[vAsInstr])
                continue

            vAsBB = ValueToBasicBlock(v)
            if vAsBB is not None:
                ops.append(vAsBB)
                continue

            vAsFunction = ValueToFunction(v)
            if vAsFunction is not None:
                ops.append(vAsFunction)
            else:
                raise NotImplementedError(v)

        bi = InstructionToBinaryOperator(instr)
        if bi is not None:
            bi: BinaryOperator
            fn = BINARY_OPS_TO_FN.get(bi.getOpcode(), None)
            if fn is None:
                raise NotImplementedError(bi)
            res = fn(*ops)
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res
            return bb, False

        call = InstructionToCallInst(instr)
        if call is not None:
            fn = ops[-1]
            fnName = fn.getName().str()
            inId = fn.getIntrinsicID()
            if fnName.startswith("hwtHls.bitRangeGet"):
                resW = instr.getType().getIntegerBitWidth()
                bitVector, index, _ = ops
                if resW == 1:
                    res = bitVector[index]
                else:
                    res = bitVector[(index + resW): index]
                if res._dtype.signed is not None:
                    res = res._convSign(None)
            elif fnName.startswith("hwtHls.bitConcat"):
                res = Concat(*reversed(ops[:-1]))
                assert res._dtype.bit_length() == instr.getType().getIntegerBitWidth(), (
                    instr, res._dtype, [o._dtype for o in ops[:-1]])
                if res._dtype.signed is not None:
                    res = res._convSign(None)
            elif inId == Intrinsic.ctlz:
                res = ctlz(*ops[:-1])
                res = zext(res, ops[0]._dtype.bit_length())
            elif inId == Intrinsic.umax:
                res = hwUMax(*ops[:-1])
            elif inId == Intrinsic.umin:
                res = hwUMin(*ops[:-1])
            elif inId == Intrinsic.smax:
                res = hwSMax(*ops[:-1])
            elif inId == Intrinsic.smin:
                res = hwSMin(*ops[:-1])
            elif inId == Intrinsic.assume:
                return bb, False
            elif inId == Intrinsic.fshl:
                res = fshl(*ops[:-1])
            elif inId == Intrinsic.fshr:
                res = fshr(*ops[:-1])
            else:
                raise NotImplementedError(instr, Intrinsic.IndependentIntrinsics(inId))

            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res
            return bb, False

        gep = InstructionToGetElementPtrInst(instr)
        if gep is not None:
            raise NotImplementedError(instr)

        cmp = InstructionToICmpInst(instr)
        if cmp is not None:
            pred = cmp.getPredicate()
            op = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]
            src0, src1 = ops
            assert not src0._dtype.signed, ("Use only unsigned internally", cmp, src0)
            assert not src1._dtype.signed, ("Use only unsigned internally", cmp, src1)

            if src0._dtype != src1._dtype:
                # cases where force_vector, strict_sign or strict_width flag is different
                assert src0._dtype.bit_length() == src1._dtype.bit_length(), (
                    "Operands must be of compatible type", instr, src0._dtype, src1._dtype)
                src1 = src1._auto_cast(src0._dtype)

            res = op._evalFn(src0, src1)
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res
            return bb, False

        select = InstructionToSelectInst(instr)
        if select is not None:
            c, tVal, fVal = ops
            if c._is_full_valid():
                if c:
                    res = tVal
                else:
                    res = fVal
            else:
                res = tVal._dtype.from_py(None)
            regs[instr] = res
            return bb, False

        cast = InstructionToCastInst(instr)
        if cast is not None:
            opc = cast.getOpcode()
            o, = ops
            CastOps = Instruction.CastOps
            newWidth = cast.getType().getIntegerBitWidth()
            oWidth = o._dtype.bit_length()

            if opc == CastOps.ZExt:
                res = Concat(HBits(newWidth - oWidth).from_py(0), o)
            elif opc == CastOps.SExt:
                msb = o[oWidth - 1]
                res = Concat(*(msb for _ in range(newWidth - oWidth)), o)
            elif opc == CastOps.Trunc:
                res = o[newWidth:]
            else:
                raise NotImplementedError(instr)
            if res._dtype.signed is not None:
                res = res._convSign(None)
            regs[instr] = res
            return bb, False

        # resolve instruction type and execute it
        br = InstructionToBranchInst(instr)
        if br is not None:
            if instr.getNumOperands() == 1:
                nextBb = ops[0]
                if waveLog is not None:
                    waveLog.logChange(nowTime, simBlockLabel, nextBb, None)

                self._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
                bb = nextBb
                return bb, True
            else:
                assert instr.getNumOperands() == 3, instr
                cond, falseBlock, trueBlock = ops  # true/false is visually reversed in print, but ops are in this order
                assert cond._is_full_valid(), (br, v)
                if cond:
                    nextBb = trueBlock
                else:
                    nextBb = falseBlock

                if waveLog is not None:
                    waveLog.logChange(nowTime, simBlockLabel, nextBb, None)
                self._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
                bb = nextBb
                return bb, True

            raise NotImplementedError(instr)

        switchBr = InstructionToSwitchInst(instr)
        if switchBr is not None:
            c = ops[0].cast_sign(None)
            assert c._is_full_valid(), ("jump condition must be always valid", c, bb, instr)
            defDst = ops[1]
            for condVal, dst in grouper(2, islice(ops, 2, None)):
                assert isinstance(condVal, HConst), condVal
                assert isinstance(dst, BasicBlock), dst
                if c._eq(condVal):
                    if waveLog is not None:
                        waveLog.logChange(nowTime, simBlockLabel, dst, None)
                    self._runBlockPhis(bb, dst, waveLog, regs, nowTime)
                    bb = dst
                    return bb, True

            if waveLog is not None:
                waveLog.logChange(nowTime, simBlockLabel, defDst, None)
            self._runBlockPhis(bb, defDst, waveLog, regs, nowTime)
            bb = defDst
            return bb, True

        freeze = InstructionToFreezeInst(instr)
        if freeze:
            o, = ops
            regs[instr] = o
            return bb, False

        raise NotImplementedError(instr)

    def run(self, fnArgs: LlvmIrInterpretArgs, wallTime:Optional[int]=None):
        F = self.F
        waveLog = self.waveLog
        timeStep = self.timeStep
        if waveLog is not None:
            _, simCodelineLabel, simTimeLabel, simBlockLabel = self._prepareVcdWriter()
        else:
            simCodelineLabel = None
            simTimeLabel = None
            simBlockLabel = None

        bb: BasicBlock = F.getEntryBlock()
        regs: Dict[Instruction, HConst] = {}

        nowTime = -timeStep
        while True:
            for instr in bb:
                instr: Instruction
                nowTime += timeStep
                if waveLog is not None:
                    waveLog.logChange(nowTime, simTimeLabel, nowTime, None)
                    waveLog.logChange(nowTime, simCodelineLabel, instr, None)

                phi = InstructionToPHINode(instr)
                if phi is not None:
                    continue  # PHIs are evaluated before jump to this block, so we skip them

                bb, isJump = self._runLlvmIrFunctionInstr(waveLog, nowTime, regs, instr, bb, fnArgs, simBlockLabel)
                if wallTime is not None and nowTime >= wallTime:
                    raise StopSimumulation()
                if isJump:
                    break
