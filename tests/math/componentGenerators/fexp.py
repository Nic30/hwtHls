import math

from hwt.pyUtils.typingFuture import override
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary
from tests.math.componentGenerators.flog import ComponentGeneratorFLOG2
from tests.math.fixp.fixpexp import FixpExpTabularizedHwModule, \
    FixpExp2TabularizedHwModule, FixpExp10TabularizedHwModule
from tests.math.hFloatTmp.hFloatTmpOps import OP_FEXP, OP_FEXP2, OP_FEXP10


class ComponentGeneratorFEXP_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.exp(x)


class ComponentGeneratorFEXP2_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return math.exp2(x)


class ComponentGeneratorFEXP10_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary):

    @override
    @staticmethod
    def evalFn(x: float) -> float:
        return 10.0 ** x


class ComponentGeneratorFEXP(ComponentGeneratorFLOG2):
    opDef = OP_FEXP
    FIXP_HWMODULE_CLS = FixpExpTabularizedHwModule


class ComponentGeneratorFEXP2(ComponentGeneratorFLOG2):
    opDef = OP_FEXP2
    FIXP_HWMODULE_CLS = FixpExp2TabularizedHwModule


class ComponentGeneratorFEXP10(ComponentGeneratorFLOG2):
    opDef = OP_FEXP10
    FIXP_HWMODULE_CLS = FixpExp10TabularizedHwModule
