#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from unittest import TestLoader, TextTestRunner, TestSuite

from tests.bitOpt.bitWidthReductionCmp_test import BitWidthReductionCmp_example_TC
from tests.io.axiStream.axisParseEth_test import AxiSParseEthTC
from tests.io.axiStream.axisParseIf_test import AxiSParseIfTC
from tests.io.axiStream.axisParseLinear_test import AxiSParseLinearTC
from tests.io.ioFsm_test import IoFsm_TC
from tests.pythonFrontend.basics_test import FromPythonBasics_TC
from tests.pythonFrontend.fnClosue_test import FnClosure_TC
from tests.pythonFrontend.stmFor_test import StmFor_TC
from tests.pythonFrontend.stmIf_test import StmIf_TC
from tests.pythonFrontend.variableChain_test import VariableChain_TC
from tests.syntaxElements.bitonicSort import BitonicSorterHLS_TCs
from tests.syntaxElements.expr_tree3 import HlsExprTree3_example_TC
from tests.syntaxElements.mac import HlsMAC_example_TC
from tests.syntaxElements.read_if import ReadIfTc
from tests.syntaxElements.slicing import HlsSlicingTC
from tests.syntaxElements.trivial_test import HlsStreamMachineTrivial_TC
from tests.syntaxElements.twoTimesA import TwoTimesA_TC
from tests.syntaxElements.while_if_test import HlsStreamMachineWhileIf_TC
from tests.syntehesis_checks import HlsSynthesisChecksTC
from tests.utils.alapAsapDiffExample import AlapAsapDiffExample_TC
from tests.utils.concatOfSlices_test import ConcatOfSlicesTC


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
    BitWidthReductionCmp_example_TC,
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
    FromPythonBasics_TC,
    FnClosure_TC,
    StmIf_TC,
    StmFor_TC,
    VariableChain_TC,
    AxiSParseEthTC,
    AxiSParseLinearTC,
    AxiSParseIfTC,
)


def main():
    # runner = TextTestRunner(verbosity=2, failfast=True)
    runner = TextTestRunner(verbosity=2)

    try:
        from concurrencytest import ConcurrentTestSuite, fork_for_tests
        useParallerlTest = True
    except ImportError:
        # concurrencytest is not installed, use regular test runner
        useParallerlTest = False
    # useParallerlTest = False

    if useParallerlTest:
        concurrent_suite = ConcurrentTestSuite(suite, fork_for_tests())
        res = runner.run(concurrent_suite)
    else:
        res = runner.run(suite)
    if not res.wasSuccessful():
        sys.exit(1)


if __name__ == '__main__':
    main()

