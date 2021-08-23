#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest import TestLoader, TextTestRunner, TestSuite

from hwtHls.examples.alapAsapDiffExample import AlapAsapDiffExample_TC
from hwtHls.examples.bitonicSort import BitonicSorterHLS_TCs
from hwtHls.examples.hls_expr_tree3 import HlsExprTree3_example_TC
from hwtHls.examples.mac import HlsMAC_example_TC
from hwtHls.scheduler.list_schedueling_test import ListSchedueling_TC
from hwtHls.tests.connection import HlsSlicingTC


def testSuiteFromTCs(*tcs):
    loader = TestLoader()
    for tc in tcs:
        tc._multiprocess_can_split_ = True
    loadedTcs = [loader.loadTestsFromTestCase(tc) for tc in tcs]
    suite = TestSuite(loadedTcs)
    return suite


suite = testSuiteFromTCs(
    HlsSlicingTC,
    HlsMAC_example_TC,
    *BitonicSorterHLS_TCs,
    HlsExprTree3_example_TC,
    AlapAsapDiffExample_TC,
    ListSchedueling_TC,
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
