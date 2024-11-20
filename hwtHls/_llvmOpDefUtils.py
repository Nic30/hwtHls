from typing import Callable

from hwt.hdl.operator import HOperatorNode
from hwtHls.llvm.llvmIr import Intrinsic, IRBuilder, Value, Twine, Type


def _getllvmIntUnaryIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntUnaryIntrinsicConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        return b.CreateIntrinsic(op0.getType(), intrinsic.value, [op0, ], Name=name)

    return _llvmIntUnaryIntrinsicConstructor


def _getllvmIntExtConstructor(isSigned: bool):

    def _llvmIntExtConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        resTy = Type.getIntNTy(b.getContext(), instr.result._dtype.bit_length())
        if isSigned:
            return b.CreateSExt(op0, resTy, name)
        else:
            return b.CreateZExt(op0, resTy, name)

    return _llvmIntExtConstructor


def _getllvmIntBinaryIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntBinaryIntrinsicConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        return b.CreateIntrinsic(op0.getType(), intrinsic.value, [op0, op1], Name=name)

    return _llvmIntBinaryIntrinsicConstructor


def _getllvmIntBitcountIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntBitcountIntrinsicConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, is_zero_poison: Value, name: Twine) -> Value:
        sliceOut = instr.result._dtype.bit_length()
        resTy = op0.getType()
        res = b.CreateIntrinsic(resTy, intrinsic.value, [op0, is_zero_poison], Name=name)
        return b.CreateBitRangeGetConst(res, 0, sliceOut)

    return _llvmIntBitcountIntrinsicConstructor


def _getllvmIntFShIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntFShIntrinsicConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, op2:Value, name: Twine) -> Value:
        return b.CreateIntrinsic(op0.getType(), intrinsic.value, [op0, op1, op2], Name=name)

    return _llvmIntFShIntrinsicConstructor


def _getllvmIntBinOpConstructor(fnGetter: Callable[[IRBuilder], Callable[[Value, Value, Twine], Value]]):

    def _llvmIntShiftConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, op1: Value, name: Twine) -> Value:
        fn = fnGetter(b)
        return fn(op0, op1, Name=name)

    return _llvmIntShiftConstructor

