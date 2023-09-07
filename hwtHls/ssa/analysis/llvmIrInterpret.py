from datetime import datetime
from io import StringIO
import re
from typing import Tuple, Generator, Union, List, Optional, Dict

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.value import HValue
from hwtHls.llvm.llvmIr import Function, BasicBlock, BinaryOperator, InstructionToBranchInst, InstructionToCallInst, \
    InstructionToGetElementPtrInst, InstructionToICmpInst, InstructionToPHINode, ValueToBasicBlock, \
    ValueToConstantInt, ValueToFunction, ValueToInstruction, Instruction, InstructionToBinaryOperator, \
    InstructionToLoadInst, InstructionToStoreInst, ValueToArgument, TypeToPointerType, TypeToIntegerType, \
    Argument, LLVMStringContext, MDOperand, MetadataAsMDNode, MetadataAsValueAsMetadata, Value, User, UserToInstruction
from hwtHls.ssa.analysis.llvmMirInterpret import SimIoUnerflowErr
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtSimApi.constants import Time
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import VcdBitsFormatter, \
    LogValueFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter
from operator import and_, or_, xor, add, mul, sub, floordiv

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


def _prepareVcdWriter(waveLog: VcdWriter, strCtx: LLVMStringContext, fn: Function, timeStep:int, codelineOffset: int=6):
    waveLog.date(datetime.now())
    waveLog.timescale(1)
    instrCodeline: Dict[Instruction, int] = {}
    simCodelineLabel = object()
    simTimeLabel = object()
    simBlockLabel = object()
    with waveLog.varScope("__sim__") as simScope:
        simScope.addVar(simCodelineLabel, "codeline", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrCodelineFormatter(instrCodeline))
        simScope.addVar(simTimeLabel, "step", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrSimTimeFormatter(timeStep))
        simScope.addVar(simBlockLabel, "block", VCD_SIG_TYPE.ENUM, 0, VcdLlvmIrBBFormatter())
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

    with waveLog.varScope(fn.getName().str().replace(".", "_")) as fnScope:
        for bb in fn:
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


def runLlvmIrFunction(strCtx: LLVMStringContext, fn: Function, args: Tuple[Generator[Union[int, HValue], None, None], List[HValue], ...],
                      waveLog: Optional[VcdWriter]=None, timeStep=10 * Time.ns):
        _, simCodelineLabel, simTimeLabel, simBlockLabel = _prepareVcdWriter(waveLog, strCtx, fn, timeStep)
        return _runLlvmIrFunction(fn, args, waveLog, timeStep, simCodelineLabel, simTimeLabel, simBlockLabel)


def _runLlvmIrFunctionInstr(waveLog: Optional[VcdWriter],
                            nowTime: int,
                            regs: Dict[Instruction, HValue],
                            instr: Instruction, predBb: BasicBlock, bb: BasicBlock,
                            fnArgs: Tuple[Generator[Union[int, HValue], None, None], List[HValue], ...],
                            simBlockLabel: Optional[object]) -> Tuple[Optional[BasicBlock], BasicBlock, bool]:
    """
    :return: predBb, bb, isJump
    """
    # check for instructions hich require special handling of operands
    phi = InstructionToPHINode(instr)
    if phi is not None:
        # special case for PHIs because they may have operands which are undefined
        v = phi.getIncomingValueForBlock(predBb)
        assert v is not None, phi
        vvConst = ValueToConstantInt(v)
        if vvConst is not None:
            pyT = Bits(vvConst.getType().getIntegerBitWidth())
            v = int(vvConst.getValue())
            if v < 0:  # convert to unsigned
                v = pyT.all_mask() + v + 1
            v = pyT.from_py(v)
            if waveLog is not None:
                waveLog.logChange(nowTime, phi, v, None)
            regs[phi] = v
            return predBb, bb, False

        vvInstr = ValueToInstruction(v)
        if vvInstr is not None:
            v = regs[vvInstr]
            if waveLog is not None:
                waveLog.logChange(nowTime, phi, v, None)
            regs[phi] = v
            return predBb, bb, False
        raise NotImplementedError("NotImplemented type of value", phi, v)

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
                raise SimIoUnerflowErr()
            assert isinstance(res, HValue) and res._dtype.bit_length() == instr.getType().getIntegerBitWidth(), (instr, res)
            if waveLog is not None:
                waveLog.logChange(nowTime, load, res, None)
            regs[instr] = res
            return predBb, bb, False
        else:
            raise NotImplementedError(instr, srcPtr)

    store = InstructionToStoreInst(instr)
    if store is not None:
        v, dstPtr = store.iterOperandValues()
        vAsConst = ValueToConstantInt(v)
        if vAsConst is not None:
            pyT = Bits(vAsConst.getType().getIntegerBitWidth())
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
            return predBb, bb, False
        else:
            raise NotImplementedError(instr)

    # prepare values for argumens
    ops: List[Union[HValue, BasicBlock, Function]] = []
    for v in instr.iterOperandValues():
        vAsConst = ValueToConstantInt(v)
        if vAsConst is not None:
            pyT = Bits(vAsConst.getType().getIntegerBitWidth())
            v = int(vAsConst.getValue())
            if v < 0:  # convert to unsigned
                v = pyT.all_mask() + v + 1
            v = pyT.from_py(v)
            ops.append(v)
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

    # print("        ", repr(ops))
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
        return predBb, bb, False

    # resolve instruction type and execute it
    br = InstructionToBranchInst(instr)
    if br is not None:
        if instr.getNumOperands() == 1:
            nextBbb = ops[0]
            predBb = bb
            bb = nextBbb
            if waveLog is not None:
                waveLog.logChange(nowTime, simBlockLabel, bb, None)
            return predBb, bb, True
        else:
            assert instr.getNumOperands() == 3, instr
            cond, falseBlock, trueBlock = ops  # true/false is visually reversed in print, but ops are in this order
            assert cond._is_full_valid(), (br, v)
            predBb = bb
            if cond:
                bb = trueBlock
            else:
                bb = falseBlock
            if waveLog is not None:
                waveLog.logChange(nowTime, simBlockLabel, bb, None)
            return predBb, bb, True

        raise NotImplementedError(instr)

    call = InstructionToCallInst(instr)
    if call is not None:
        fn = ops[-1]
        fnName = fn.getName().str()
        if fnName.startswith("hwtHls.bitRangeGet"):
            resW = instr.getType().getIntegerBitWidth()
            bitVector, index, _ = ops
            if resW == 1:
                res = bitVector[index]
            else:
                res = bitVector[(index + resW): index]
        elif fnName.startswith("hwtHls.bitConcat"):
            res = Concat(*reversed(ops[:-1]))
            assert res._dtype.bit_length() == instr.getType().getIntegerBitWidth(), (
                instr, res._dtype, [o._dtype for o in ops[:-1]])
        else:
            raise NotImplementedError(instr)

        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res
        return predBb, bb, False

    gep = InstructionToGetElementPtrInst(instr)
    if gep is not None:
        raise NotImplementedError(instr)

    cmp = InstructionToICmpInst(instr)
    if cmp is not None:
        pred = cmp.getPredicate()
        op = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]
        src0, src1 = ops
        if src0._dtype.signed is not None:
            src0 = src0.cast_sign(None)
        if src1._dtype.signed is not None:
            src1 = src1.cast_sign(None)
        res = op._evalFn(src0, src1)
        if waveLog is not None:
            waveLog.logChange(nowTime, instr, res, None)
        regs[instr] = res
        return predBb, bb, False

    raise NotImplementedError(instr)


def _runLlvmIrFunction(fn: Function,
                       fnArgs: Tuple[Generator[Union[int, HValue], None, None], List[HValue], ...],
                       waveLog: Optional[VcdWriter],
                       timeStep: int,
                       simCodelineLabel: Optional[object],
                       simTimeLabel: Optional[object],
                       simBlockLabel: Optional[object]):
    predBb: Optional[BasicBlock] = None
    bb: BasicBlock = fn.getEntryBlock()
    regs: Dict[Instruction, HValue] = {}
    nowTime = -timeStep
    while True:
        for instr in bb:
            instr: Instruction
            nowTime += timeStep
            if waveLog is not None:
                waveLog.logChange(nowTime, simTimeLabel, nowTime, None)
                waveLog.logChange(nowTime, simCodelineLabel, instr, None)
            predBb, bb, isJump = _runLlvmIrFunctionInstr(waveLog, nowTime, regs, instr, predBb, bb, fnArgs, simBlockLabel)
            if isJump:
                break
