from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue

"""
Special operators for HlsNetlist
:var OP_SHIFT_ONEHOT: shift which has shift amount in one-hot format (shift amount is split to multiple inputs of 1b width as in HlsNetNodeMux)
:var OP_SHIFT_BIN: shift which has shift amount in binary format
:var OP_MUL_HL: 
:note: Nodes with shift operator have shiftAmountMap which can be used to prune shift variants
"""


def _shift_onehot(op0: AnyHBitsValue, op1: AnyHBitsValue):
    raise NotImplementedError("This operator should be used only as contant in backend")


OP_SHIFT_ONEHOT = HOperatorDef(_shift_onehot, False, idStr="OP_SHIFT_ONEHOT")


def _shift_bin(op0: AnyHBitsValue, op1: AnyHBitsValue):
    raise NotImplementedError("This operator should be used only as contant in backend")


OP_SHIFT_BIN = HOperatorDef(_shift_bin, False, idStr="OP_SHIFT_BIN")


# paired DIV+REM instructions, inferred from div/rem on same operands
def _udivrem(a: AnyHBitsValue, b: AnyHBitsValue):
    a = a._unsigned()
    b = b._unsigned()
    return (a // b, a % b)


OP_UDIVREM = HOperatorDef(_udivrem, False, idStr="OP_UDIVREM")


def _sdivrem(a: AnyHBitsValue, b: AnyHBitsValue):
    a = a._signed()
    b = b._signed()
    return (a // b, a % b)


OP_SDIVREM = HOperatorDef(_sdivrem, False, idStr="OP_SDIVREM")


def _mul_hl(op0: AnyHBitsValue, op1: AnyHBitsValue, isSigned0:bool, width0:int, isSigned1:bool, width1:int, resultWidth:int):
    raise NotImplementedError("This opeerator should be used only as contant in backend")


OP_MUL_HL = HOperatorDef(_mul_hl, False, idStr="OP_MUL_HL")
