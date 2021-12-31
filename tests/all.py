#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest import TestLoader, TextTestRunner, TestSuite

from tests.alapAsapDiffExample import AlapAsapDiffExample_TC
from tests.bitonicSort import BitonicSorterHLS_TCs
from tests.concatOfSlices_test import ConcatOfSlicesTC
from tests.expr_tree3 import HlsExprTree3_example_TC
from tests.ioFsm_test import IoFsm_TC
from tests.mac import HlsMAC_example_TC
from tests.read_if import ReadIfTc
from tests.slicing import HlsSlicingTC
from tests.syntehesis_checks import HlsSynthesisChecksTC
from tests.trivial_test import HlsStreamMachineTrivial_TC
from tests.twoTimesA import TwoTimesA_TC
from tests.while_if_test import HlsStreamMachineWhileIf_TC


def testSuiteFromTCs(*tcs):
    loader = TestLoader()
    for tc in tcs:
        tc._multiprocess_can_split_ = True
    loadedTcs = [loader.loadTestsFromTestCase(tc) for tc in tcs]
    suite = TestSuite(loadedTcs)
    return suite


suite = testSuiteFromTCs(
    ConcatOfSlicesTC,
    HlsSlicingTC,
    ReadIfTc,
    HlsMAC_example_TC,
    *BitonicSorterHLS_TCs,
    HlsExprTree3_example_TC,
    AlapAsapDiffExample_TC,
    HlsSynthesisChecksTC,
    TwoTimesA_TC,
    HlsStreamMachineTrivial_TC,
    HlsStreamMachineWhileIf_TC,
    IoFsm_TC,
)

if __name__ == '__main__':
    runner = TextTestRunner(verbosity=2)

    try:
        from concurrencytest import ConcurrentTestSuite, fork_for_tests
        useParallerlTest = True
    except ImportError:
        # concurrencytest is not installed, use regular test runner
        useParallerlTest = False

    if useParallerlTest:
        # Run same tests across 4 processes
        concurrent_suite = ConcurrentTestSuite(suite, fork_for_tests())
        runner.run(concurrent_suite)
    else:
        runner.run(suite)
