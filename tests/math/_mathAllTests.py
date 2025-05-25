#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.math.componentGenerators._div.divSrt2_test import DivSrt2_TC
from tests.math.componentGenerators._div.divSrt4_test import DivSrt4_TC
from tests.math.componentGenerators._mul.mulChained_test import PipelinedMultiplierChained_TCs
from tests.math.componentGenerators._mul.mulSequential_test import PipelinedMultiplierSequential_TCs
from tests.math.componentGenerators._mul.mulToom2_5_test import PipelinedMultiplierToom2_5_TCs
from tests.math.componentGenerators._mul.mulToom2_test import PipelinedMultiplierToom2_TCs
from tests.math.countBits_test import CountBitsTC
from tests.math.ctpop_test import Ctpop_TC
from tests.math.fixp.cordicAngleNormalization_test import CordicAngleNormalization_TC
from tests.math.fixp.cordic_test import Cordic_TC
from tests.math.fixp.fixpConstCast_test import HFixedPointQ_HConst_TC
from tests.math.fixp.fixpOperatorsCast_test import FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC
from tests.math.fixp.fixpOperatorsCmp_test import FixpOpCmp_TCs
from tests.math.fixp.fixpOperatorsCommonArithExpr_test import FixpOpCommonArithExpr_TCs
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpOpCommonArith_TCs
from tests.math.fixp.fixpOperatorsLogExp_test import FixpOpLogExp_TCs
from tests.math.fixp.fixpOperatorsTrigonometric_test import FixpOpTrigonometric_TCs
from tests.math.fp.fpFromInt_test import IEEE754FpFromInt_TC
from tests.math.fp.fpToInt_test import IEEE754FpToInt_TC
from tests.math.fp.fpadd_test import IEEE754FpAdder_TC
from tests.math.fp.fpcmp_test import IEEE754FpCmp_TC
from tests.math.fp.fpmul_test import IEEE754FpMultipier_TC
from tests.math.fp.fptypes_test import IEEE754Fp_TC
from tests.math.hFloatTmp.hFloatTmpConstToLlvm_test import HFloatTmpConstToLlvm_TC
from tests.math.divremRestoring_test import DivRemRestoring_TCs

llvmMir_TCs = [
    CountBitsTC,
    Ctpop_TC,
    *PipelinedMultiplierSequential_TCs,
    *PipelinedMultiplierChained_TCs,
    *PipelinedMultiplierToom2_TCs,
    *PipelinedMultiplierToom2_5_TCs,
    IEEE754Fp_TC,
    HFloatTmpConstToLlvm_TC,
    HFixedPointQ_HConst_TC,
    FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC,
    *FixpOpCmp_TCs,
    *FixpOpCommonArith_TCs,
    *FixpOpCommonArithExpr_TCs,
    *FixpOpLogExp_TCs,
    *FixpOpTrigonometric_TCs,
    IEEE754FpCmp_TC,
    IEEE754FpFromInt_TC,
    IEEE754FpToInt_TC,
    IEEE754FpAdder_TC,
    IEEE754FpMultipier_TC,
    Cordic_TC,
    CordicAngleNormalization_TC,
    *DivRemRestoring_TCs,
    DivSrt2_TC,
    DivSrt4_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*llvmMir_TCs))
