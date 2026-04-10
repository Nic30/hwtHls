#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.math.addMasked_test import AddMasked_TC
from tests.math.componentGenerators._mul.mulChained_test import PipelinedMultiplierChained_TCs
from tests.math.componentGenerators._mul.mulSequential_test import PipelinedMultiplierSequential_TCs
from tests.math.componentGenerators._mul.mulToom2_5_test import PipelinedMultiplierToom2_5_TCs
from tests.math.componentGenerators._mul.mulToom2_test import PipelinedMultiplierToom2_TCs
from tests.math.countBits_test import CountBitsTC
from tests.math.ctpop_test import Ctpop_TC
from tests.math.divremRestoring_test import DivRemRestoring_TCs
from tests.math.fixp._mathFixpAllTests import llvmMathFixp_TCs
from tests.math.fp._mathFpAllTests import llvmMathFp_TCs
from tests.math.hFloatTmp.hFloatTmpConstToLlvm_test import HFloatTmpConstToLlvm_TC
from tests.math.icmp_test import Icmp_TC
from tests.math.prefixSum_test import PrefixSumTC
from tests.testCaseUtils import testSuiteFromTCs


#from tests.math.componentGenerators._div.divSrt2_test import DivSrt2_TC
#from tests.math.componentGenerators._div.divSrt4_test import DivSrt4_TC
llvmMath_TCs = [
    Icmp_TC,
    CountBitsTC,
    Ctpop_TC,
    AddMasked_TC,
    *PipelinedMultiplierSequential_TCs,
    *PipelinedMultiplierChained_TCs,
    *PipelinedMultiplierToom2_TCs,
    *PipelinedMultiplierToom2_5_TCs,
    HFloatTmpConstToLlvm_TC,
    *llvmMathFixp_TCs,
    *llvmMathFp_TCs,
    *DivRemRestoring_TCs,
    #DivSrt2_TC,
    #DivSrt4_TC,
    PrefixSumTC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*llvmMath_TCs), printTopLongest=3)
