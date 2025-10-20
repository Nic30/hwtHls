from hwt.pyUtils.typingFuture import override
from hwtHls.code import OP_LSHR, OP_ASHR
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForUnSpecializedHwtHlsFpIntrinsicBinary_FloatInt
from tests.math.componentGenerators.fpshl import ComponentGeneratorFP_SHL


class ComponentGeneratorFP_SHR_UNSPECIALIZED(ComponentGeneratorForUnSpecializedHwtHlsFpIntrinsicBinary_FloatInt):
    """
    :see: :class:`ComponentGeneratorFP_SHL_UNSPECIALIZED`
    """

    @override
    @staticmethod
    def evalFn(v: float, sh:int) -> float:
        return v * (2.0 ** -sh)


class ComponentGeneratorFP_SHR(ComponentGeneratorFP_SHL):
    """
    :see: :class:`ComponentGeneratorFP_SHL`
    """
    INT_OP = (OP_ASHR, OP_LSHR)
    evalFn = staticmethod(ComponentGeneratorFP_SHR_UNSPECIALIZED.evalFn)

