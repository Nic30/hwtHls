#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.math.fixp.cordicAngleNormalization_test import CordicAngleNormalization_TC
from tests.math.fixp.cordic_test import Cordic_TC
from tests.math.fixp.fixpConstCast_test import HFixedPointQ_HConst_TC
from tests.math.fixp.fixpOperatorsCast_test import FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC
from tests.math.fixp.fixpOperatorsCmp_test import FixpOpCmp_TCs
from tests.math.fixp.fixpOperatorsCommonArithExpr_test import FixpOpCommonArithExpr_TCs
from tests.math.fixp.fixpOperatorsCommonArith_test import FixpOpCommonArith_TCs
from tests.math.fixp.fixpOperatorsLogExp_test import FixpOpLogExp_TCs
from tests.math.fixp.fixpOperatorsTrigonometric_test import FixpOpTrigonometric_TCs
from tests.math.fixp.fixpSqrt_test import FixpOpSqrt_TCs
from tests.testCaseUtils import testSuiteFromTCs


llvmMathFixp_TCs = [
    HFixedPointQ_HConst_TC,
    FixpResizeRoundHalfEvenSaturateSigned_3_2_to_3_1_TC,
    *FixpOpCmp_TCs,
    *FixpOpCommonArith_TCs,
    *FixpOpCommonArithExpr_TCs,
    *FixpOpLogExp_TCs,
    *FixpOpSqrt_TCs,
    *FixpOpTrigonometric_TCs,
    Cordic_TC,
    CordicAngleNormalization_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*llvmMathFixp_TCs))
