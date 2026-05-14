from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue

"""
Special operators for HlsNetlist
:var OP_SHIFT_ONEHOT: shift which has shift amount in one-hot format (shift amount is split to multiple inputs of 1b width as in HlsNetNodeMux)
:var OP_SHIFT_BIN: shift which has shift amount in binary format
:var OP_MUL_HL: 
:note: Nodes with shift operator have shiftAmountMap which can be used to prune shift variants
"""
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.bits import HBits
from pyMathBitPrecise.bit_utils import to_signed, to_unsigned


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
    if isinstance(op0, HBitsConst) and isinstance(op1, HBitsConst):
        resTy = HBits(resultWidth)
        if not op0._is_full_valid() or not op1._is_full_valid():
            return resTy.from_py(None)
        op0 = int(op0)
        if isSigned0:
            op0 = to_signed(op0, width0)
        op1 = int(op1)
        if isSigned1:
            op1 = to_signed(op1, width1)
        res = op0 * op1
        if isSigned0 or isSigned1:
            res = to_unsigned(res, resultWidth)
        return resTy.from_py(res)

    raise NotImplementedError("This opeerator should be used only as contant in backend")


OP_MUL_HL = HOperatorDef(_mul_hl, False, idStr="OP_MUL_HL")
