#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from hwtLib.tests.all import unittestMain
from tests.llvmMir.HwtFpgaGenPreToNetlistGICombiner_test import HwtFpgaPreToNetlistGICombiner_TC
from tests.llvmMir.HwtFpgaPreRegAllocGICombiner_test import HwtFpgaPreRegAllocGICombiner_TC
from tests.llvmMir.earlyIfConverter_test import EarlyIfConverter_TC
from tests.llvmMir.vregIfConverter_test import VRegIfConverter_TC
from tests.testCaseUtils import testSuiteFromTCs


llvmMir_TCs = [
    EarlyIfConverter_TC,
    VRegIfConverter_TC,
    HwtFpgaPreRegAllocGICombiner_TC,
    HwtFpgaPreToNetlistGICombiner_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*llvmMir_TCs))
