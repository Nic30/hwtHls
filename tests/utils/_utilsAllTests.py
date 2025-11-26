#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.utils.alapAsapDiffExample_test import AlapAsapDiffExample_TC
from tests.utils.bitwiseOpsScheduling_test import BitwiseOpsScheduling_TC
from tests.utils.schedulingNodeFunctions_test import SchedulingNodeFunctions_TC

utils_TCs = [
    SchedulingNodeFunctions_TC,
    BitwiseOpsScheduling_TC,
    AlapAsapDiffExample_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*utils_TCs, printTopLongest=3))
