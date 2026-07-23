"""
:note: order of operands is the same as in Instruction.def and IntrinsicEnums.inc
    to have some consistent order  (same as in hfloattmp.h)
:note: most of the functions are used only internally and user python code should use only
    operators (e.g. '*' instead of fmul). However some functions have typechecks and can be used with any
    type, e.g. sin/cos/sqrt
"""

import math
import operator
from typing import Union, Optional, Callable

from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase, HwIOBase
from hwt.pyUtils.setList import SetList
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, IRBuilder, Value, Twine, Type, \
    Intrinsic, ICmpInst, LibFunc
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist
from hwtHls.ssa.translation.toLlvm import HOperatorDefLlvm
from pyMathBitPrecise.bit_utils import ValidityError
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOpsUtils import _evalFpFunction1, _getllvmFp1OpConstructor, \
    _evalFpFunction2, _getllvmFp2OpConstructor, _getllvmFp1LibFuncConstructor, \
    _F_CONST_CLS, _getllvmFCmpOpConstructor, _evalFpFunction1ValSpecific, \
    _getllvmFp1IntrinsicConstructor, _getllvmFp2IntrinsicConstructor, \
    _evalFpFunction2ValSpecific, _getllvmFp2LibFuncConstructor


# :see: https://llvm.org/docs/LangRef.html
# Instruction.def
def fneg(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1(lambda x:-x, OP_FNEG, op0)


OP_FNEG = HOperatorDefLlvm(fneg, _getllvmFp1OpConstructor(lambda b: b.CreateFNeg), False, idStr="OP_FNEG")


def fadd(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction2(lambda a, b: a + b, OP_FADD, op0, op1)


OP_FADD = HOperatorDefLlvm(fadd, _getllvmFp2OpConstructor(lambda b: b.CreateFAdd), False, idStr="OP_FADD")


def fsub(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction2(lambda a, b: a - b, OP_FSUB, op0, op1)


OP_FSUB = HOperatorDefLlvm(fsub, _getllvmFp2OpConstructor(lambda b: b.CreateFSub), False, idStr="OP_FSUB")


def fmul(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction2(lambda a, b: a * b, OP_FMUL, op0, op1)


OP_FMUL = HOperatorDefLlvm(fmul, _getllvmFp2OpConstructor(lambda b: b.CreateFMul), False, idStr="OP_FMUL")


def fdiv(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction2(lambda a, b: a / b, OP_FDIV, op0, op1)


OP_FDIV = HOperatorDefLlvm(fdiv, _getllvmFp2OpConstructor(lambda b: b.CreateFDiv), False, idStr="OP_FDIV")


# https://github.com/gpuweb/gpuweb/issues/1696
# FRem "The floating-point remainder whose sign matches the sign of Operand 1."
# FMod "The floating-point remainder whose sign matches the sign of Operand 2."
# :note: Remainder = Dividend – (Divisor * Quotient)
# https://www.delftstack.com/howto/cpp/cpp-modulo-negative/
# :attention: % modulo operator in C++ is actually a remainder, in python it is modulo
def frem(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction2(math.remainder, OP_FREM, op0, op1)


OP_FREM = HOperatorDefLlvm(frem, _getllvmFp2OpConstructor(lambda b: b.CreateFRem), False, idStr="OP_FREM")


def fmod(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]):
    return _evalFpFunction2(lambda a, b: a % b, OP_FMOD, op0, op1)


OP_FMOD = HOperatorDefLlvm(frem, _getllvmFp2LibFuncConstructor(LibFunc.LibFunc_fmod), False, idStr="OP_FMOD")

# :note: those are implemented using cast instead of custom instruction
# FPToUI # floating point -> UInt
# FPToSI # floating point -> SInt
# UIToFP  # UInt -> floating point
# SIToFP  # SInt -> floating point
# FPTrunc # Truncate floating point
# FPExt   # Extend floating point

# FCmp  #  Floating point comparison instr.


class HOperatorDefLlvmFcmpOrder(HOperatorDefLlvm):
    """
    Ordered FCMP operators (result of ordered cmp is false if any operand is NaN)
    """

    def __init__(self, ordPred: ICmpInst.Predicate,
                 ordPredFn: Callable[[ RtlSignalBase[HFloatTmp], RtlSignalBase[HFloatTmp]], RtlSignalBase[BIT]],
                 runSimplifyRules: Optional[Callable[["HlsNetNodeOperator", SetList["HlsNetNode"]], bool]]=None):
        self.ordPredFn = ordPredFn
        idStr = "OP_" + ordPred.name
        HOperatorDef.__init__(self, self._fcmp_apply_pred, allowsAssignTo=False, idStr=idStr,
                              hdlConvertoAstOp=None)
        self.llvmOperatorConstructor = _getllvmFCmpOpConstructor(ordPred)
        self.runSimplifyRules = runSimplifyRules
 
    def _fcmp_apply_pred(self,
                          op0: RtlSignalBase[HFloatTmp],
                          op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
        if isinstance(op0, _F_CONST_CLS) and isinstance(op1, _F_CONST_CLS):
            if _isNaN_const(op0) or _isNaN_const(op1):
                return b0
            return self.ordPredFn(op0, op1)
        else:
            assert op0._dtype == op1._dtype, (op0, op1)
            return HOperatorNode.withRes(self, (op0, op1), BIT)


# oeq: true if both operands are not a QNAN and op1 is equal to op2.
OP_FCMP_OEQ = HOperatorDefLlvmFcmpOrder(ICmpInst.Predicate.FCMP_OEQ, operator.eq)
# ogt: true if both operands are not a QNAN and op1 is greater than op2.
OP_FCMP_OGT = HOperatorDefLlvmFcmpOrder(ICmpInst.Predicate.FCMP_OGT, operator.gt)
# oge: true if both operands are not a QNAN and op1 is greater than or equal to op2.
OP_FCMP_OGE = HOperatorDefLlvmFcmpOrder(ICmpInst.Predicate.FCMP_OGE, operator.ge)
# olt: true if both operands are not a QNAN and op1 is less than op2.
OP_FCMP_OLT = HOperatorDefLlvmFcmpOrder(ICmpInst.Predicate.FCMP_OLT, operator.lt)
# ole: true if both operands are not a QNAN and op1 is less than or equal to op2.
OP_FCMP_OLE = HOperatorDefLlvmFcmpOrder(ICmpInst.Predicate.FCMP_OLE, operator.le)
# one: true if both operands are not a QNAN and op1 is not equal to op2.
OP_FCMP_ONE = HOperatorDefLlvmFcmpOrder(ICmpInst.Predicate.FCMP_ONE, operator.ne)
fcmp_oeq = OP_FCMP_OEQ._fcmp_apply_pred
fcmp_ogt = OP_FCMP_OGT._fcmp_apply_pred
fcmp_oge = OP_FCMP_OGE._fcmp_apply_pred
fcmp_olt = OP_FCMP_OLT._fcmp_apply_pred
fcmp_ole = OP_FCMP_OLE._fcmp_apply_pred
fcmp_one = OP_FCMP_ONE._fcmp_apply_pred


def isNaN(op0: RtlSignalBase[HFloatTmp]):
    _isNaN = _isNaN_const(op0)
    if _isNaN is not None:
        return b1 if _isNaN else b0

    return HOperatorNode.withRes(OP_FCMP_UNO, (op0, op0), BIT)


def isNotNaN(op0: RtlSignalBase[HFloatTmp]):
    _isNaN = _isNaN_const(op0)
    if _isNaN is not None:
        return b0 if _isNaN else b1

    return HOperatorNode.withRes(OP_FCMP_ORD, (op0, op0), BIT)


def fcmp_ord(op0: RtlSignalBase[HFloatTmp],
             op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    if _isNaN_const(op0) or _isNaN_const(op1):
        return b0

    return HOperatorNode.withRes(OP_FCMP_ORD, (op0, op0), BIT)


OP_FCMP_ORD = HOperatorDefLlvm(fcmp_ord, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_ORD), False, idStr="OP_FCMP_ORD")


def fcmp_uno(op0: RtlSignalBase[HFloatTmp],
             op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
    if _isNaN_const(op0) or _isNaN_const(op1):
        return b1

    return HOperatorNode.withRes(OP_FCMP_UNO, (op0, op0), BIT)


OP_FCMP_UNO = HOperatorDefLlvm(fcmp_uno, _getllvmFCmpOpConstructor(ICmpInst.Predicate.FCMP_UNO), False, idStr="OP_FCMP_UNO")


def _isNaN_const(op0: RtlSignalBase[HFloatTmp]) -> Optional[bool]:
    if isinstance(op0, float):
        return math.isnan(op0)
    elif isinstance(op0, HConst):
        return op0.isNaN()
    return None


class HOperatorDefLlvmFcmpUnorder(HOperatorDefLlvm):
    """
    Unordered variants of FCMP operators (result of unorderd cmp is true if any operand is NaN)
    """

    def __init__(self, unOrdPred: ICmpInst.Predicate,
                 ordPredFn: Callable[[ RtlSignalBase[HFloatTmp], RtlSignalBase[HFloatTmp]], RtlSignalBase[BIT]],
                 runSimplifyRules: Optional[Callable[["HlsNetNodeOperator", SetList["HlsNetNode"]], bool]]=None):
        self.ordPredFn = ordPredFn
        idStr = "OP_" + unOrdPred.name
        HOperatorDef.__init__(self, self._fcmp_UNO_or_pred, allowsAssignTo=False, idStr=idStr,
                              hdlConvertoAstOp=None)
        self.llvmOperatorConstructor = _getllvmFCmpOpConstructor(unOrdPred)
        self.runSimplifyRules = runSimplifyRules
 
    def _fcmp_UNO_or_pred(self,
                          op0: RtlSignalBase[HFloatTmp],
                          op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[BIT]:
        if _isNaN_const(op0) or _isNaN_const(op1):
            return b1
        elif self.ordPredFn is not None and isinstance(op0, _F_CONST_CLS) and isinstance(op1, _F_CONST_CLS):
            return self.ordPredFn(op0, op1)
        else:
            assert op0._dtype == op1._dtype, (op0, op1)
            return HOperatorNode.withRes(self, (op0, op1), BIT)


OP_FCMP_UEQ = HOperatorDefLlvmFcmpUnorder(ICmpInst.Predicate.FCMP_UEQ, operator.eq)
OP_FCMP_UGT = HOperatorDefLlvmFcmpUnorder(ICmpInst.Predicate.FCMP_UGT, operator.gt)
OP_FCMP_UGE = HOperatorDefLlvmFcmpUnorder(ICmpInst.Predicate.FCMP_UGE, operator.ge)
OP_FCMP_ULT = HOperatorDefLlvmFcmpUnorder(ICmpInst.Predicate.FCMP_ULT, operator.lt)
OP_FCMP_ULE = HOperatorDefLlvmFcmpUnorder(ICmpInst.Predicate.FCMP_ULE, operator.le)
OP_FCMP_UNE = HOperatorDefLlvmFcmpUnorder(ICmpInst.Predicate.FCMP_UNE, operator.ne)
fcmp_ueq = OP_FCMP_UEQ._fcmp_UNO_or_pred
fcmp_ugt = OP_FCMP_UGT._fcmp_UNO_or_pred
fcmp_uge = OP_FCMP_UGE._fcmp_UNO_or_pred
fcmp_ult = OP_FCMP_ULT._fcmp_UNO_or_pred
fcmp_ule = OP_FCMP_ULE._fcmp_UNO_or_pred
fcmp_une = OP_FCMP_UNE._fcmp_UNO_or_pred
#
# # IntrinsicEnums.inc


def ceil(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.ceil, OP_CEIL, "ceil", op0)


OP_CEIL = HOperatorDefLlvm(ceil, _getllvmFp1IntrinsicConstructor(Intrinsic.ceil), False, idStr="OP_CEIL")


def cos(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.cos, OP_FCOS, "cos", op0)


def _cos_runSimplifyRules(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    op = n.dependsOn[0]
    b = n.getHlsNetlistBuilder()
    for user in op.obj.usedBy[op.out_i]:
        uObj = user.obj
        if isinstance(uObj, HlsNetNodeOperator) and uObj.operator == OP_FSINCOS:
            cos, _ = uObj._outputs
            worklist.append(n)
            b.replaceOutput(n._outputs[0], cos, True)
            return True

    return False


OP_FCOS = HOperatorDefLlvm(cos, _getllvmFp1IntrinsicConstructor(Intrinsic.cos), False, idStr="OP_FCOS", runSimplifyRules=_cos_runSimplifyRules)


def cospi(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(lambda a: math.cos(a * math.pi), OP_FCOSPI, "cospi", op0)


def _cospi_runSimplifyRules(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    op = n.dependsOn[0]
    b = n.getHlsNetlistBuilder()
    for user in op.obj.usedBy[op.out_i]:
        uObj = user.obj
        if isinstance(uObj, HlsNetNodeOperator) and uObj.operator == OP_FSINCOSPI:
            cos, _ = uObj._outputs
            worklist.append(n)
            b.replaceOutput(n._outputs[0], cos, True)
            return True

    return False


OP_FCOSPI = HOperatorDefLlvm(cospi, _getllvmFp1LibFuncConstructor(LibFunc.LibFunc_cospi), False, idStr="OP_FCOSPI", runSimplifyRules=_cospi_runSimplifyRules)


def exp(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.exp, OP_FEXP, "exp", op0)


OP_FEXP = HOperatorDefLlvm(exp, _getllvmFp1IntrinsicConstructor(Intrinsic.exp), False, idStr="OP_FEXP")


def exp10(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(lambda a: math.pow(10., a), OP_FEXP10, "exp10", op0)


OP_FEXP10 = HOperatorDefLlvm(exp10, _getllvmFp1IntrinsicConstructor(Intrinsic.exp10), False, idStr="OP_FEXP10")


def exp2(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(lambda a: math.pow(2., a), OP_FEXP2, "exp2", op0)


OP_FEXP2 = HOperatorDefLlvm(exp2, _getllvmFp1IntrinsicConstructor(Intrinsic.exp2), False, idStr="OP_FEXP2")


def fabs(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    # todo for fixed point use (x + (x >> (x.width-1))) ^ (x >> (x.width-1))
    return _evalFpFunction1ValSpecific(math.fabs, OP_FABS, "fabs", op0)


OP_FABS = HOperatorDefLlvm(fabs, _getllvmFp1IntrinsicConstructor(Intrinsic.fabs), False, idStr="OP_FABS")


def floor(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.floor, OP_FLOOR, "floor", op0)


OP_FLOOR = HOperatorDefLlvm(floor, _getllvmFp1IntrinsicConstructor(Intrinsic.floor), False, idStr="OP_FLOOR")


# fma,                                       # llvm.fma
# fmuladd,                                   # llvm.fmuladd
# fptosi_sat,                                # llvm.fptosi.sat
# fptoui_sat,                                # llvm.fptoui.sat
# fptrunc_round,                             # llvm.fptrunc.round
# frexp,                                     # llvm.frexp  # splits a floating point value into a normalized fractional component and integral exponent
# ldexp,                                     # llvm.ldexp # reverse of frexp, joins mantissa and exponent into floating point number
def log(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.log, OP_FLOG, "log", op0)


OP_FLOG = HOperatorDefLlvm(log, _getllvmFp1IntrinsicConstructor(Intrinsic.log), False, idStr="OP_FLOG")


def log10(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.log10, OP_FLOG10, "log10", op0)


OP_FLOG10 = HOperatorDefLlvm(log10, _getllvmFp1IntrinsicConstructor(Intrinsic.log10), False, idStr="OP_FLOG10")


def log2(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.log2, OP_FLOG2, "log2", op0)


OP_FLOG2 = HOperatorDefLlvm(log2, _getllvmFp1IntrinsicConstructor(Intrinsic.log2), False, idStr="OP_FLOG2")

# nearbyint,                                 # llvm.nearbyint - round to nearest


def fpow(op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    if isinstance(op0, _F_CONST_CLS) and isinstance(op1, _F_CONST_CLS):
        try:
            return HFloatTmp.from_py(math.pow(float(op0), float(op1)))
        except ValidityError:
            return HFloatTmp.from_py(None)

    valSpecificFn = getattr(op0, "fpow", None)
    if valSpecificFn is not None:
        return valSpecificFn(op1)

    assert op0._dtype == op1._dtype, (op0, op1)

    return HOperatorNode.withRes(OP_FPOW, (op0, op1), op0._dtype)


OP_FPOW = HOperatorDefLlvm(fpow, _getllvmFp2IntrinsicConstructor(Intrinsic.pow), False, idStr="OP_FPOW")


def fpowi(op0: Union[RtlSignalBase[HFloatTmp], float], op1: RtlSignalBase[HBits]) -> RtlSignalBase[HFloatTmp]:
    """
    equivalent of float @llvm.powi.f32.i32(float %Val, i32 %power), 
    :returns: the first argument raised to the (positive or negative) power
    """
    if isinstance(op0, float):
        assert isinstance(op1, int)
        return math.pow(op0, op1)

    valSpecificFn = getattr(op0, "fpowi", None)
    if valSpecificFn is not None:
        return valSpecificFn(op1)

    assert op0._dtype == HFloatTmp, op0._dtype
    assert isinstance(op1._dtype, HBits), op1._dtype
    if not op1._dtype.signed:
        # zext so sign is always 0
        op1 = b0._concat(op1)

    if isinstance(op0, _F_CONST_CLS) and isinstance(op1, _F_CONST_CLS):
        try:
            return HFloatTmp.from_py(math.pow(float(op0), int(op1)))
        except ValidityError:
            return HFloatTmp.from_py(None)

    return HOperatorNode.withRes(OP_FPOWI, (op0, op1), op0._dtype)


def _llvmFpPowi(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
    doubleTy = Type.getDoubleTy(b.getContext())
    assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
    assert op1.getType().isIntegerTy(), (op1, "rhs of powi should be int")
    return b.CreateIntrinsic(doubleTy, Intrinsic.powi.value, [op0, op1], Name=name)


OP_FPOWI = HOperatorDefLlvm(fpowi, _llvmFpPowi, False, idStr="OP_FPOWI")

# shift left and right operands which do not have llvm equivalent (use mul by pow 2) and are used only by backed
# as specialized type of multiplication/division (for FP it is exponent add/sub, for Q it is shl/ashr)
OP_FP_SHL = HOperatorDefLlvm(None, None, False, idStr="OP_FP_SHL")
OP_FP_SHR = HOperatorDefLlvm(None, None, False, idStr="OP_FP_SHR")


# rint,                                      # llvm.rint round to nearest integer
def fround(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(round, OP_ROUND, "fround", op0)


OP_ROUND = HOperatorDefLlvm(fround, _getllvmFp1IntrinsicConstructor(Intrinsic.round), False, idStr="OP_ROUND")


def roundeven(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    valSpecificFn = getattr(op0, "roundeven", None)
    if valSpecificFn is not None:
        return valSpecificFn()
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_ROUNDEVEN, (op0,), op0._dtype)


OP_ROUNDEVEN = HOperatorDefLlvm(roundeven, _getllvmFp1IntrinsicConstructor(Intrinsic.roundeven), False, idStr="OP_ROUNDEVEN")


def _sincos(*args):
    raise NotImplementedError("use cos and sin separately this operator is intended only for backend")


OP_FSINCOS = HOperatorDefLlvm(_sincos, _sincos, False, idStr="OP_FSINCOS")


def _sincospi(*args):
    raise NotImplementedError("use cospi and sinpi separately this operator is intended only for backend")


OP_FSINCOSPI = HOperatorDefLlvm(_sincospi, _sincospi, False, idStr="OP_FSINCOSPI")


def _get_sin_runSimplifyRules(cosOp: HOperatorDefLlvm, sincosOp:HOperatorDefLlvm):

    def _sin_runSimplifyRules(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
        op = n.dependsOn[0]
        fcoss: list[HlsNetNodeOperator] = []
        sincos: Optional[HlsNetNodeOperator] = None
        b = n.getHlsNetlistBuilder()
        for user in op.obj.usedBy[op.out_i]:
            uObj = user.obj
            if isinstance(uObj, HlsNetNodeOperator):
                if uObj.operator == cosOp:
                    fcoss.append(uObj)
                elif uObj.operator == sincosOp:
                    sincos = uObj

        if fcoss or sincos is not None:
            addAllUsersToWorklist(worklist, n)
            if sincos is None:
                t = n._outputs[0]._dtype
                sincos = b.buildOpManyDst(sincosOp, n.operatorSpecialization, (t, t), op)

            cos, sin = sincos._outputs
            b.replaceOutput(n._outputs[0], sin, True)
            for fcos in fcoss:
                b.replaceOutput(fcos._outputs[0], cos, True)
            return True

        return False

    return _sin_runSimplifyRules


def sin(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.sin, OP_FSIN, "sin", op0)


OP_FSIN = HOperatorDefLlvm(sin, _getllvmFp1IntrinsicConstructor(Intrinsic.sin), False, idStr="OP_FSIN", runSimplifyRules=_get_sin_runSimplifyRules(OP_FCOS, OP_FSINCOS))


def sinpi(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(lambda a: math.sin(a * math.pi), OP_FSINPI, "sinpi", op0)


OP_FSINPI = HOperatorDefLlvm(sinpi, _getllvmFp1LibFuncConstructor(LibFunc.LibFunc_sinpi), False, idStr="OP_FSINPI", runSimplifyRules=_get_sin_runSimplifyRules(OP_FCOSPI, OP_FSINCOSPI))


def sqrt(op0: RtlSignalBase[Union[HFloatTmp, HBits]]) -> RtlSignalBase[Union[HFloatTmp, HBits]]:
    """
    Integer, floatingpoint or fixedpoint square root.

    If the input is of integer type, return integer square root on half width bits.
    If the input is of HFloatTmp type return floating/fixed point (depending on what HFloatTmp specification)
    of the same type.
    :note: there is no sqrt for int in llvm-21 ir.
        This code uses floatingpoint sqrt with casts which should let backend know that this is integer sqrt.
    """
    if isinstance(op0, _F_CONST_CLS):
        try:
            if isinstance(op0, HBitsConst):
                op0 = int(op0)
                try:
                    v = math.sqrt(op0)
                    return op0._dtype.from_py(v)
                except ValueError:
                    return op0._dtype.from_py(0, vld_mask=0)
            else:
                op0 = float(op0)
                try:
                    v = math.sqrt(op0)
                    return HFloatTmp.from_py(v)
                except ValueError:
                    v = math.nan
                    return HFloatTmp.from_py(v)
               
        except ValidityError:
            return HFloatTmp.from_py(None)

    elif isinstance(op0._dtype, HBits):
        t = op0._dtype
        assert not t.signed
        w = t.bit_length()
        if w % 2 != 0:
            w += 1  # width must be %2 == 0
        # w // 2 because sqrt reduces bitwidth ov value by this scale
        resTy = HBits(w // 2, signed=False)

        if isinstance(op0, HBitsConst):
            if op0._is_full_valid():
                val = int(math.isqrt(op0.val))
            else:
                val = None
            return resTy.from_py(val)
        else:
            if isinstance(op0, HwIOBase):
                op0 = op0._sig

            # reuse HFixedPointQ sqrt
            fixPTy = HFixedPointQ(w, 0, False)
            op0 = op0._reinterpret_cast(fixPTy)._explicit_cast(HFloatTmp)
            res = HOperatorNode.withRes(OP_FSQRT, (op0,), HFloatTmp)
            return res._auto_cast(fixPTy)._auto_cast(HFixedPointQ(w // 2, 0, False))._reinterpret_cast(resTy)

    valSpecificFn = getattr(op0, "sqrt", None)
    if valSpecificFn is not None:
        return valSpecificFn()

    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(OP_FSQRT, (op0,), op0._dtype)


OP_FSQRT = HOperatorDefLlvm(sqrt, _getllvmFp1IntrinsicConstructor(Intrinsic.sqrt), False, idStr="OP_FSQRT")


def fract(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    if isinstance(op0, _F_CONST_CLS):
        try:
            _op0 = float(op0)
            return HFloatTmp.from_py(_op0 - math.floor(_op0))
        except ValidityError:
            return HFloatTmp.from_py(None)

    assert op0._dtype == HFloatTmp, (op0)
    # LLVM does not have native fract operator
    return _op0 - floor(_op0)

# [todo] fract llvm.frexp AMDGPUCodeGenPrepareImpl::matchFractPat
# [todo] in llvm-18 tan and other are target library functions defined in TargetLibraryInfo.def, (used as LibFunc_tan etc)
#        later they become intrinsics
#        llvm.minnum
#        llvm.maxnum

# template = """
# def {fn}(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
#     return _evalFpFunction1ValSpecific(math.{fn}, OP_FASIN, "{fn}", op0)
#
#
# OP_F{FN} = HOperatorDefLlvm({fn}, _getllvmFp1LibFuncConstructor(LibFunc.LibFunc_{fn}), False, idStr="OP_F{FN}")
# """
# for f in ["asin", "sinh", "acos", "cosh", "tan", "atan", "tanh"]:
#     f:str
#     print(template.format(fn=f, FN=f.upper()))


def asin(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.asin, OP_FASIN, "asin", op0)


OP_FASIN = HOperatorDefLlvm(asin, _getllvmFp1IntrinsicConstructor(Intrinsic.asin), False, idStr="OP_FASIN")


def sinh(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.sinh, OP_FSINH, "sinh", op0)


OP_FSINH = HOperatorDefLlvm(sinh, _getllvmFp1IntrinsicConstructor(Intrinsic.sinh), False, idStr="OP_FSINH")


def acos(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.acos, OP_FACOS, "acos", op0)


OP_FACOS = HOperatorDefLlvm(acos, _getllvmFp1IntrinsicConstructor(Intrinsic.acos), False, idStr="OP_FACOS")


def cosh(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.cosh, OP_FCOSH, "cosh", op0)


OP_FCOSH = HOperatorDefLlvm(cosh, _getllvmFp1IntrinsicConstructor(Intrinsic.cosh), False, idStr="OP_FCOSH")


def tan(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.tan, OP_FTAN, "tan", op0)


OP_FTAN = HOperatorDefLlvm(tan, _getllvmFp1IntrinsicConstructor(Intrinsic.tan), False, idStr="OP_FTAN")


def tanpi(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    op0 = op0 * math.pi
    return tan(op0)


def _tanpiLLVM(*args):
    raise AssertionError("This operator should be used only by backend, llvm-21 does not have tanpi function and tan(x*pi) should be used instead")


OP_FTANPI = HOperatorDefLlvm(tanpi, _tanpiLLVM, False, idStr="OP_FTANPI")


def atan(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.atan, OP_FATAN, "atan", op0)


OP_FATAN = HOperatorDefLlvm(atan, _getllvmFp1IntrinsicConstructor(Intrinsic.atan), False, idStr="OP_FATAN")


def tanh(op0: RtlSignalBase[HFloatTmp]) -> RtlSignalBase[HFloatTmp]:
    return _evalFpFunction1ValSpecific(math.tanh, OP_FTANH, "tanh", op0)


OP_FTANH = HOperatorDefLlvm(tanh, _getllvmFp1IntrinsicConstructor(Intrinsic.tanh), False, idStr="OP_FTANH")


def atan2(y: RtlSignalBase[HFloatTmp], x: RtlSignalBase[HFloatTmp]):
    return _evalFpFunction2ValSpecific(math.atan2, OP_FATAN2, "atan2", y, x)


OP_FATAN2 = HOperatorDefLlvm(atan2, _getllvmFp2IntrinsicConstructor(Intrinsic.atan2), False, idStr="OP_FATAN2")
