#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest import TestLoader, TextTestRunner, TestSuite

from hwtHls.tests.bitonicSort import BitonicSorterHLS_TCs
from hwtHls.tests.mac import HlsMAC_example_TC
from hwtHls.tests.alapAsapDiffExample import AlapAsapDiffExample_TC
from hwtHls.tests.concatOfSlices_test import ConcatOfSlicesTC
from hwtHls.tests.expr_tree3 import HlsExprTree3_example_TC
from hwtHls.tests.list_schedueling_test import ListSchedueling_TC
from hwtHls.tests.read_if import ReadIfTc
from hwtHls.tests.slicing import HlsSlicingTC
from hwtHls.tests.syntehesis_checks import HlsSynthesisChecksTC
from hwtHls.tests.trivial_test import HlsStreamMachineTrivial_TC
from hwtHls.tests.twoTimesA import TwoTimesA_TC
from hwtHls.tests.while_if_test import HlsStreamMachineWhileIf_TC


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
    ListSchedueling_TC,
    HlsSynthesisChecksTC,
    TwoTimesA_TC,
    HlsStreamMachineTrivial_TC,
    HlsStreamMachineWhileIf_TC,
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
