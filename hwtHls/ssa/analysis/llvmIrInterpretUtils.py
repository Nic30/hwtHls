"""
LlvmIrInstrFunction takes wave logger, current time, and regs as inputs, and returns tuple bb, isJump
"""

from io import StringIO
from operator import and_, or_, xor, add, mul, sub, floordiv, rshift, lshift, mod, truediv
import re
from typing import Union, Dict, Any, Callable, Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import Function, BasicBlock, Instruction, MDOperand, ValueToConstantInt, \
    MetadataToValueAsMetadata, LLVMStringContext, Argument, Value, UserToInstruction, \
    InstructionToLoadInst, User, InstructionToStoreInst, InstructionToGetElementPtrInst, StreamChannelFormatInfo,\
    HwtHlsIoMetadata_get, HwtHlsIoMetadata
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import VcdBitsFormatter, \
    LogValueFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter


LlvmIrInstrFunction = Callable[[Optional[VcdWriter], int, dict[Instruction, HConst]], tuple[BasicBlock, bool]]


class PtrAddrTuple(tuple[Any, Union[int, HConst]]):
    """
    Tuple (basePointer, index)
    """
    pass


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
def floorsdiv(a: HBitsConst, b: HBitsConst):
    return (a._signed() // b._signed())._vec()


def srem(a: HBitsConst, b: HBitsConst):
    return (a._signed() % b._signed())._vec()


RE_NON_ID = re.compile('[^0-9a-zA-Z_]+')
BINARY_OPS_TO_FN = {
    Instruction.BinaryOps.And: and_,
    Instruction.BinaryOps.Or: or_,
    Instruction.BinaryOps.Xor: xor,
    Instruction.BinaryOps.Add: add,
    Instruction.BinaryOps.Sub: sub,
    Instruction.BinaryOps.Mul: mul,
    Instruction.BinaryOps.UDiv: floordiv,
    Instruction.BinaryOps.SDiv: floorsdiv,
    Instruction.BinaryOps.URem: mod,
    Instruction.BinaryOps.SRem: srem,
    Instruction.BinaryOps.LShr: rshift,  # logical shift right
    Instruction.BinaryOps.Shl: lshift,
    Instruction.BinaryOps.Shl: lshift,
    Instruction.BinaryOps.FAdd: add,
    Instruction.BinaryOps.FSub: sub,
    Instruction.BinaryOps.FDiv: truediv,
    Instruction.BinaryOps.FMul: mul,

}


class VcdLlvmIrBBFormatter(LogValueFormatter):

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: BasicBlock, updater, t: int, out: StringIO):
        # val = newVal.getName().str()
        name = newVal.printAsOperand()[len("label "):]
        name = RE_NON_ID.sub("_", name)
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


def _getMetadataInt(v: MDOperand) -> int:
    return int(ValueToConstantInt(MetadataToValueAsMetadata(v.get()).getValue()).getValue())


def _findLoadOrStoreWidthForValue(strCtx: LLVMStringContext, v: Value) -> int:
    if isinstance(v, Argument):
        v: Argument
        streamInfo = StreamChannelFormatInfo.findOptionalInMetadata(v)
        if streamInfo:
            return streamInfo.getWidthOfBusWord()

    for u in v.users():
        u: User
        userInstr = UserToInstruction(u)
        assert userInstr is not None, (v, u)
        ld = InstructionToLoadInst(userInstr)
        if ld is not None:
            return ld.getType().getScalarSizeInBits()

        st = InstructionToStoreInst(userInstr)
        if st is not None:
            return st.getOperand(0).getType().getScalarSizeInBits()

        gep = InstructionToGetElementPtrInst(userInstr)
        if gep is not None:
            raise NotImplementedError()

        raise NotImplementedError(userInstr)

    raise AssertionError("value has no use can not infer pointee width", v)


def _prepareWaveWriterTopIo(waveLog: VcdWriter, strCtx: LLVMStringContext, fn: Function):
    with waveLog.varScope("args") as argScope:
        ioMetadatas = HwtHlsIoMetadata_get(fn)
        assert fn.arg_size() == len(ioMetadatas)
        for arg, ioMetadata in zip(fn.args(), ioMetadatas):
            arg: Argument
            ioMetadata: HwtHlsIoMetadata
            if ioMetadata.addrWidth != 0:
                raise NotImplementedError(arg, ioMetadata.addrWidth)
            name = RE_NON_ID.sub("_", arg.getName().str())
            assert name, arg
            argWidth = _findLoadOrStoreWidthForValue(strCtx, arg)
            argScope.addVar(arg, name, VCD_SIG_TYPE.WIRE, argWidth, VcdBitsFormatter())

