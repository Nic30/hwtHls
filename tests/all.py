#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

from hwtLib.tests.all import unittestMain
from tests.adt.collections.hashTable_test import HashTable_TC
from tests.bitOpt._bitOptAllTests import bitOpt_TCs
from tests.crypto.md5_test import Md5_TC
from tests.frontend._frontendAllTests import frontend_TCs
from tests.io._ioAllTests import io_TCs
from tests.llvmIr._llvmIrAllTests import llvmIr_TCs
from tests.llvmMir._llvmMirAllTests import llvmMir_TCs
from tests.math._mathAllTests import llvmMath_TCs
from tests.syntehesisChecks_test import HlsSynthesisChecksTC
from tests.testCaseUtils import testSuiteFromTCs
from tests.threads._threadsAllTests import threads_TCs


suite = testSuiteFromTCs(
    *bitOpt_TCs,
    *frontend_TCs,
    *io_TCs,
    *llvmIr_TCs,
    *llvmMir_TCs,
    *llvmMath_TCs,
    *threads_TCs,
    HlsSynthesisChecksTC,
    Md5_TC,
    HashTable_TC,
)

if __name__ == '__main__':
    sys.setrecursionlimit(int(1e5))  # see bitOpt_TCs
    unittestMain(suite)

