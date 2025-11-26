#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.testCaseUtils import testSuiteFromTCs
from tests.threads.ThreadHwtComponent_test import ThreadHwtComponentReg_rtl_TC


threads_TCs = [
    ThreadHwtComponentReg_rtl_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*threads_TCs, printTopLongest=3))
