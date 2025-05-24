from tests.math.componentGenerators.flog2 import ComponentGeneratorFLOG2
from tests.math.fixp.fixpexp import FixpExpTabularizedHwModule, \
    FixpExp2TabularizedHwModule, FixpExp10TabularizedHwModule


class ComponentGeneratorFEXP(ComponentGeneratorFLOG2):

    FIXP_HWMODULE_CLS = FixpExpTabularizedHwModule


class ComponentGeneratorFEXP2(ComponentGeneratorFLOG2):

    FIXP_HWMODULE_CLS = FixpExp2TabularizedHwModule


class ComponentGeneratorFEXP10(ComponentGeneratorFLOG2):

    FIXP_HWMODULE_CLS = FixpExp10TabularizedHwModule
