"""
LlvmIrInstrFunction takes wave logger, current time, and regs as inputs, and returns tuple bb, isJump
"""
from operator import and_, or_, xor, add, mul, sub, rshift, lshift
import re
from typing import Union, Any, Callable, Optional, Generator

from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import BasicBlock, Instruction, MDOperand, ValueToConstantInt, \
    MetadataToValueAsMetadata, LLVMStringContext, Argument, Value, UserToInstruction, \
    InstructionToLoadInst, User, InstructionToStoreInst, InstructionToGetElementPtrInst, StreamChannelFormatInfo
from pyDigitalWaveTools.vcd.writer import VcdWriter


LlvmIrInstrFunction = Callable[[Optional[VcdWriter], int, dict[Instruction, HConst]], tuple[BasicBlock, bool]]


class HwtHlsFpIntrisicName(str):

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {str(self):s}>"


LlvmIrInterpretArgs = tuple[Generator[Union[int, HConst], None, None], list[HConst], ...]


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


class SimIoOverflowErr(Exception):
    """
    This exception is raised when there is too much of data for some IO.
    This may mean that the simulation did finish or some internal buffer did overflow.
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


RE_NON_ID = re.compile('[^0-9a-zA-Z_]+')
AnyInstrOpcode = Union[Instruction.MemoryOps,
                       Instruction.OtherOps,
                       Instruction.TermOps,
                       Instruction.CastOps,
                       Instruction.BinaryOps]

BINARY_OPS_TO_FN: dict[Instruction.BinaryOps, Callable] = {
    Instruction.BinaryOps.And: and_,
    Instruction.BinaryOps.Or: or_,
    Instruction.BinaryOps.Xor: xor,
    Instruction.BinaryOps.Add: add,
    Instruction.BinaryOps.Sub: sub,
    Instruction.BinaryOps.Mul: mul,
    Instruction.BinaryOps.LShr: rshift,  # logical shift right
    Instruction.BinaryOps.Shl: lshift,
}


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



