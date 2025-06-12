from typing import Callable

from hwt.hdl.operator import HOperatorNode
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Intrinsic, IRBuilder, Value, Twine, Type


def _getllvmIntUnaryIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntUnaryIntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        return b.CreateIntrinsic(op0.getType(), intrinsic.value, [op0, ], Name=name)

    return _llvmIntUnaryIntrinsicConstructor


def _llvmIntSExtConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
    resTy = Type.getIntNTy(b.getContext(), instr.result._dtype.bit_length())
    return b.CreateSExt(op0, resTy, name)


def _llvmIntZExtConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
    resTy = Type.getIntNTy(b.getContext(), instr.result._dtype.bit_length())
    return b.CreateZExt(op0, resTy, name)


def _getllvmIntBinaryIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntBinaryIntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        return b.CreateIntrinsic(op0.getType(), intrinsic.value, [op0, op1], Name=name)

    return _llvmIntBinaryIntrinsicConstructor


def _getllvmIntBitcountIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntBitcountIntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, is_zero_poison: Value, name: Twine) -> Value:
        sliceOut = instr.result._dtype.bit_length()
        resTy = op0.getType()
        res = b.CreateIntrinsic(resTy, intrinsic.value, [op0, is_zero_poison], Name=name)
        return b.CreateBitRangeGetConst(res, 0, sliceOut)

    return _llvmIntBitcountIntrinsicConstructor


def _llvmIntCtpopIntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
    sliceOut = instr.result._dtype.bit_length()
    resTy = op0.getType()
    res = b.CreateIntrinsic(resTy, Intrinsic.ctpop.value, [op0, ], Name=name)
    return b.CreateBitRangeGetConst(res, 0, sliceOut)


def _getllvmIntFShIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmIntFShIntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, op2:Value, name: Twine) -> Value:
        return b.CreateIntrinsic(op0.getType(), intrinsic.value, [op0, op1, op2], Name=name)

    return _llvmIntFShIntrinsicConstructor


def _getllvmIntBinOpConstructor(fnGetter: Callable[[IRBuilder], Callable[[Value, Value, Twine], Value]]):

    def _llvmIntShiftConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1: Value, name: Twine) -> Value:
        fn = fnGetter(b)
        return fn(op0, op1, Name=name)

    return _llvmIntShiftConstructor

