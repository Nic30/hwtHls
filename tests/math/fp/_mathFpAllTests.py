#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.math.fp.fpFromInt_test import IEEE754FpFromInt_TC
from tests.math.fp.fpToInt_test import IEEE754FpToInt_TC
from tests.math.fp.fpadd_test import IEEE754FpAdd_TC, IEEE754FpSub_TC
from tests.math.fp.fpcmp_test import IEEE754FpCmp_TC
from tests.math.fp.fpmul_test import IEEE754FpMultipier_TC
from tests.math.fp.fptypes_test import IEEE754Fp_TC

llvmMathFp_TCs = [
    IEEE754Fp_TC,
    IEEE754FpCmp_TC,
    IEEE754FpFromInt_TC,
    IEEE754FpToInt_TC,
    IEEE754FpAdd_TC,
    IEEE754FpSub_TC,
    IEEE754FpMultipier_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*llvmMathFp_TCs))
