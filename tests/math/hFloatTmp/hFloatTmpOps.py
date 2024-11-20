from typing import Callable

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase
from hwtHls.llvm.llvmIr import IRBuilder, Value, Twine, Type, Intrinsic, ICmpInst
from hwtHls.ssa.translation.toLlvm import HOperatorDefLlvm
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


def _getllvmFpBinOpConstructor(constructFnGeter: Callable[[IRBuilder], Callable]):

    def _llvmFpBinOpConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        assert op1.getType() == doubleTy, (op1, "double should be used to represent HFloatTmp in first phase of compilation")
        return constructFnGeter(b)(op0, op1, name)

    return _llvmFpBinOpConstructor


def _getllvmFCmpOpConstructor(predicate: ICmpInst.Predicate):

    def _llvmFCmpOpConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        assert op1.getType() == doubleTy, (op1, "double should be used to represent HFloatTmp in first phase of compilation")
        return b.CreateFCmp(predicate, op0, op1, name)

    return _llvmFCmpOpConstructor


def _getllvmFpUnOpConstructor(constructFnGeter: Callable[[IRBuilder], Callable]):

    def _llvmFpUnOpConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        return constructFnGeter(b)(op0, name)

    return _llvmFpUnOpConstructor


def _getllvmFpUnIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmFpUnIntrinsicConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, op0
        return b.CreateIntrinsic(doubleTy, intrinsic.value, [op0, ], Name=name)

    return _llvmFpUnIntrinsicConstructor


def _getllvmFpBinIntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmFpBinIntrinsicConstructor(b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        assert op1.getType() == doubleTy, (op1, "double should be used to represent HFloatTmp in first phase of compilation")
        return b.CreateIntrinsic(doubleTy, intrinsic.value, [op0, op1], Name=name)

    return _llvmFpBinIntrinsicConstructor

# :see: https://llvm.org/docs/LangRef.html
# Instruction.def


def fneg(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, op0
    return HOperatorNode.withRes(OP_FNEG, (op0,), op0._dtype)


OP_FNEG = HOperatorDefLlvm(fneg, _getllvmFpBinOpConstructor(lambda b: b.CreateFNeg), False, idStr="OP_FNEG")


def fadd(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == op1._dtype, (op0._dtype, op1._dtype)
    assert op1._dtype == HFloatTmp, op1
    return HOperatorNode.withRes(OP_FADD, (op0, op1), op0._dtype)


OP_FADD = HOperatorDefLlvm(fadd, _getllvmFpBinOpConstructor(lambda b: b.CreateFAdd), False, idStr="OP_FADD")


def fsub(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, op0
    assert op1._dtype == HFloatTmp, op1
    return HOperatorNode.withRes(OP_FSUB, (op0, op1), op0._dtype)


OP_FSUB = HOperatorDefLlvm(fsub, _getllvmFpBinOpConstructor(lambda b: b.CreateFSub), False, idStr="OP_FSUB")


def fmul(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FMUL, (op0, op1), op0._dtype)


OP_FMUL = HOperatorDefLlvm(fadd, _getllvmFpBinOpConstructor(lambda b: b.CreateFMul), False, idStr="OP_FMUL")


def fdiv(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FDIV, (op0, op1), op0._dtype)


OP_FDIV = HOperatorDefLlvm(fadd, _getllvmFpBinOpConstructor(lambda b: b.CreateFDiv), False, idStr="OP_FDIV")


def frem(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FREM, (op0, op1), op0._dtype)


OP_FREM = HOperatorDefLlvm(fadd, _getllvmFpBinOpConstructor(lambda b: b.CreateFRem), False, idStr="OP_FREM")

# FPToUI # floating point -> UInt
# FPToSI # floating point -> SInt
# UIToFP  # UInt -> floating point
# SIToFP  # SInt -> floating point
# FPTrunc # Truncate floating point
# FPExt   # Extend floating point
# FCmp  #  Floating point comparison instr.


# oeq: true if both operands are not a QNAN and op1 is equal to op2.
def fcmp_oeq(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FCMP_OEQ, (op0, op1), op0._dtype)


OP_FCMP_OEQ = HOperatorDefLlvm(fcmp_oeq, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_OEQ), False, idStr="OP_FCMP_OEQ")


# ogt: true if both operands are not a QNAN and op1 is greater than op2.
def fcmp_ogt(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FCMP_OGT, (op0, op1), op0._dtype)


OP_FCMP_OGT = HOperatorDefLlvm(fcmp_ogt, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_OGT), False, idStr="OP_FCMP_OGT")


# oge: true if both operands are not a QNAN and op1 is greater than or equal to op2.
def fcmp_oge(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FCMP_OGE, (op0, op1), op0._dtype)


OP_FCMP_OGE = HOperatorDefLlvm(fcmp_oge, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_OGE), False, idStr="OP_FCMP_OGE")


# olt: true if both operands are not a QNAN and op1 is less than op2.
def fcmp_olt(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FCMP_OLT, (op0, op1), op0._dtype)


OP_FCMP_OLT = HOperatorDefLlvm(fcmp_olt, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_OLT), False, idStr="OP_FCMP_OLT")


# ole: true if both operands are not a QNAN and op1 is less than or equal to op2.
def fcmp_ole(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FCMP_OLE, (op0, op1), op0._dtype)


OP_FCMP_OLE = HOperatorDefLlvm(fcmp_ole, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_OLE), False, idStr="OP_FCMP_OLE")


# one: true if both operands are not a QNAN and op1 is not equal to op2.
def fcmp_one(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FCMP_ONE, (op0, op1), op0._dtype)


OP_FCMP_ONE = HOperatorDefLlvm(fcmp_one, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_ONE), False, idStr="OP_FCMP_ONE")
#
# # IntrinsicEnums.inc


def ceil(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_CEIL, (op0,), op0._dtype)


OP_CEIL = HOperatorDefLlvm(ceil, _getllvmFpUnIntrinsicConstructor(Intrinsic.ceil), False, idStr="OP_CEIL")


def cos(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FCOS, (op0,), op0._dtype)


OP_FCOS = HOperatorDefLlvm(cos, _getllvmFpUnIntrinsicConstructor(Intrinsic.cos), False, idStr="OP_FCOS")


def exp(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FEXP, (op0,), op0._dtype)


OP_FEXP = HOperatorDefLlvm(exp, _getllvmFpUnIntrinsicConstructor(Intrinsic.exp), False, idStr="OP_FEXP")


def exp10(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FEXP10, (op0,), op0._dtype)


OP_FEXP10 = HOperatorDefLlvm(exp10, _getllvmFpUnIntrinsicConstructor(Intrinsic.exp10), False, idStr="OP_FEXP10")


def exp2(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FEXP2, (op0,), op0._dtype)


OP_FEXP2 = HOperatorDefLlvm(exp2, _getllvmFpUnIntrinsicConstructor(Intrinsic.exp2), False, idStr="OP_FEXP2")


def fabs(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FABS, (op0,), op0._dtype)


OP_FABS = HOperatorDefLlvm(fabs, _getllvmFpUnIntrinsicConstructor(Intrinsic.fabs), False, idStr="OP_FABS")


def floor(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FLOOR, (op0,), op0._dtype)


OP_FLOOR = HOperatorDefLlvm(floor, _getllvmFpUnIntrinsicConstructor(Intrinsic.floor), False, idStr="OP_FLOOR")


# fma,                                       # llvm.fma
# fmuladd,                                   # llvm.fmuladd
# fptosi_sat,                                # llvm.fptosi.sat
# fptoui_sat,                                # llvm.fptoui.sat
# fptrunc_round,                             # llvm.fptrunc.round
# frexp,                                     # llvm.frexp  # splits a floating point value into a normalized fractional component and integral exponent
# fshl,                                      # llvm.fshl
# fshr,                                      # llvm.fshr
# ldexp,                                     # llvm.ldexp # reverse of frexp, joins mantissa and exponent into floating point number
def log(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FLOG, (op0,), op0._dtype)


OP_FLOG = HOperatorDefLlvm(log, _getllvmFpUnIntrinsicConstructor(Intrinsic.log), False, idStr="OP_FLOG")


def log10(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FLOG10, (op0,), op0._dtype)


OP_FLOG10 = HOperatorDefLlvm(log10, _getllvmFpUnIntrinsicConstructor(Intrinsic.log10), False, idStr="OP_FLOG10")


def log2(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FLOG2, (op0,), op0._dtype)


OP_FLOG2 = HOperatorDefLlvm(log2, _getllvmFpUnIntrinsicConstructor(Intrinsic.log2), False, idStr="OP_FLOG2")

# nearbyint,                                 # llvm.nearbyint - round to nearest


def fpow(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == op1._dtype, (op0, op1)
    return HOperatorNode.withRes(OP_FPOW, (op0, op1), op0._dtype)


OP_FPOW = HOperatorDefLlvm(fadd, _getllvmFpBinIntrinsicConstructor(Intrinsic.pow), False, idStr="OP_FPOW")


# powi,                                      # llvm.powi
# rint,                                      # llvm.rint
def round(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_ROUND, (op0,), op0._dtype)


OP_ROUND = HOperatorDefLlvm(round, _getllvmFpUnIntrinsicConstructor(Intrinsic.round), False, idStr="OP_ROUND")


def roundeven(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_ROUNDEVEN, (op0,), op0._dtype)


OP_ROUNDEVEN = HOperatorDefLlvm(round, _getllvmFpUnIntrinsicConstructor(Intrinsic.roundeven), False, idStr="OP_ROUNDEVEN")


def sin(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FSIN, (op0,), op0._dtype)


OP_FSIN = HOperatorDefLlvm(sin, _getllvmFpUnIntrinsicConstructor(Intrinsic.sin), False, idStr="OP_FSIN")


def sqrt(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FSQRT, (op0,), op0._dtype)


OP_FSQRT = HOperatorDefLlvm(sqrt, _getllvmFpUnIntrinsicConstructor(Intrinsic.sqrt), False, idStr="OP_FSQRT")

# [todo] fract llvm.frexp AMDGPUCodeGenPrepareImpl::matchFractPat
#             asin, csin
#             acos, cosh
#        tan, atan, tanh
#        llvm.minnum
#        llvm.maxnum
