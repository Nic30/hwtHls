#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.bitOpt.abc_NtkExpandExternalCombLoops_test import Abc_NtkExpandExternalCombLoops_TC
from tests.bitOpt.abc_test import AbcTC
from tests.bitOpt.andShiftInLoop_test import AndShiftInLoop_TC
from tests.bitOpt.cmpReduction_test import CmpReduction_TC
from tests.bitOpt.shifter_test import ShifterTC
from tests.testCaseUtils import testSuiteFromTCs


bitOpt_TCs = [
    AbcTC,
    Abc_NtkExpandExternalCombLoops_TC,
    CmpReduction_TC,
    AndShiftInLoop_TC,
    ShifterTC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*bitOpt_TCs))

