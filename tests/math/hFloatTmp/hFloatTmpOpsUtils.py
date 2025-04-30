from typing import Callable

from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.mainBases import RtlSignalBase
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, IRBuilder, Value, Twine, Type, \
    Intrinsic, ICmpInst, LibFunc, getOrInsertLibFunc_1, getOrInsertLibFunc_2
from hwtHls.ssa.translation.toLlvm import HOperatorDefLlvm
from pyMathBitPrecise.bit_utils import ValidityError
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp

_F_CONST_CLS = (HConst, float, int)


def _getllvmFp2OpConstructor(constructFnGeter: Callable[[IRBuilder], Callable]):

    def _llvmFp2OpConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        assert op1.getType() == doubleTy, (op1, "double should be used to represent HFloatTmp in first phase of compilation")
        return constructFnGeter(b)(op0, op1, name)

    return _llvmFp2OpConstructor


def _getllvmFCmpOpConstructor(predicate: ICmpInst.Predicate):

    def _llvmFCmpOpConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        assert op1.getType() == doubleTy, (op1, "double should be used to represent HFloatTmp in first phase of compilation")
        return b.CreateFCmp(predicate, op0, op1, name)

    return _llvmFCmpOpConstructor


def _getllvmFp1OpConstructor(constructFnGeter: Callable[[IRBuilder], Callable]):

    def _llvmFp1OpConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        return constructFnGeter(b)(op0, name)

    return _llvmFp1OpConstructor


def _getllvmFp1IntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmFp1IntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, op0
        return b.CreateIntrinsic(doubleTy, intrinsic.value, [op0, ], Name=name)

    return _llvmFp1IntrinsicConstructor


def _getllvmFp2IntrinsicConstructor(intrinsic: Intrinsic):

    def _llvmFp2IntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, (op0, "double should be used to represent HFloatTmp in first phase of compilation")
        assert op1.getType() == doubleTy, (op1, "double should be used to represent HFloatTmp in first phase of compilation")
        return b.CreateIntrinsic(doubleTy, intrinsic.value, [op0, op1], Name=name)

    return _llvmFp2IntrinsicConstructor


def _getllvmFp1LibFuncConstructor(fnId: LibFunc):

    def _llvmFp1IntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, op0
        try:
            fn = getOrInsertLibFunc_1(ctx.module, ctx.getTargetLibraryInfo(), fnId, doubleTy, doubleTy)
        except Exception as e:
            raise Exception("Can not create", fnId, e)
        return b.CreateCall(fn, [op0, ], Name=name)

    return _llvmFp1IntrinsicConstructor


def _getllvmFp2LibFuncConstructor(fnId: LibFunc):

    def _llvmFp2IntrinsicConstructor(ctx: LlvmCompilationBundle, b:IRBuilder, instr: HOperatorNode, op0:Value, op1:Value, name: Twine) -> Value:
        doubleTy = Type.getDoubleTy(b.getContext())
        assert op0.getType() == doubleTy, op0
        assert op1.getType() == doubleTy, op1
        try:
            fn = getOrInsertLibFunc_2(ctx.module, ctx.getTargetLibraryInfo(), fnId, doubleTy, doubleTy, doubleTy)
        except Exception as e:
            raise Exception("Can not create", fnId, e)
        return b.CreateCall(fn, [op0, op1, ], Name=name)

    return _llvmFp2IntrinsicConstructor


def _evalFpFunction1(floatOp: Callable[[float], float], opDef: HOperatorDefLlvm, op0: RtlSignalBase[HFloatTmp]):
    if isinstance(op0, _F_CONST_CLS):
        try:
            return HFloatTmp.from_py(floatOp(float(op0)))
        except ValidityError:
            return HFloatTmp.from_py(None)

    assert op0._dtype == HFloatTmp, op0
    return HOperatorNode.withRes(opDef, (op0,), HFloatTmp)


def _evalFpFunction2(floatOp: Callable[[float, float], float], opDef: HOperatorDefLlvm, op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]):
    if isinstance(op0, _F_CONST_CLS) and isinstance(op1, _F_CONST_CLS):
        try:
            return HFloatTmp.from_py(floatOp(float(op0), float(op1)))
        except ValidityError:
            return HFloatTmp.from_py(None)
    if isinstance(op1, (float, int)):
        op1 = HFloatTmp.from_py(op1)

    assert op0._dtype == op1._dtype, (op0._dtype, op1._dtype)
    assert op1._dtype == HFloatTmp, op1
    return HOperatorNode.withRes(opDef, (op0, op1), HFloatTmp)


def _evalFpFunction1ValSpecific(floatOp: Callable[[float], float], opDef: HOperatorDefLlvm,
                                operatorFunctionAttributeName:str, op0: RtlSignalBase[HFloatTmp]):
    if isinstance(op0, _F_CONST_CLS):
        try:
            return HFloatTmp.from_py(floatOp(float(op0)))
        except ValidityError:
            return HFloatTmp.from_py(None)
    valSpecificFn = getattr(op0, operatorFunctionAttributeName, None)
    if valSpecificFn is not None:
        return valSpecificFn()
    assert op0._dtype == HFloatTmp, (op0)
    return HOperatorNode.withRes(opDef, (op0,), HFloatTmp)


def _evalFpFunction2ValSpecific(floatOp: Callable[[float], float], opDef: HOperatorDefLlvm,
                                operatorFunctionAttributeName:str,
                                op0: RtlSignalBase[HFloatTmp], op1: RtlSignalBase[HFloatTmp]):
    if isinstance(op0, _F_CONST_CLS) and isinstance(op1, _F_CONST_CLS):
        try:
            return HFloatTmp.from_py(floatOp(float(op0), float(op1)))
        except ValidityError:
            return HFloatTmp.from_py(None)

    valSpecificFn = getattr(op0, operatorFunctionAttributeName, None)
    if valSpecificFn is not None:
        return valSpecificFn(op1)

    if isinstance(op1, (float, int)):
        op1 = HFloatTmp.from_py(op1)

    assert op0._dtype == op1._dtype, (op0._dtype, op1._dtype)
    assert op1._dtype == HFloatTmp, op1
    return HOperatorNode.withRes(opDef, (op0, op1), HFloatTmp)
