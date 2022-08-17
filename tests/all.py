#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from unittest import TestLoader, TextTestRunner, TestSuite

from tests.bitOpt.abc_test import AbcTC
from tests.bitOpt.andShiftInLoop import AndShiftInLoop_TC
from tests.bitOpt.bitWidthReductionCmp_test import BitWidthReductionCmp_example_TC
from tests.bitOpt.sliceBreak_test import SliceBreak_TC
from tests.frontend.ast.bitonicSort import BitonicSorterHLS_TCs
from tests.frontend.ast.exprTree3 import HlsAstExprTree3_example_TC
from tests.frontend.ast.mac import HlsMAC_example_TC
from tests.frontend.ast.readIf import HlsAstReadIfTc
from tests.frontend.ast.slicing import HlsSlicingTC
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.frontend.ast.twoTimesA import TwoTimesA_TC
from tests.frontend.ast.whileIf_test import HlsAstWhileIf_TC
from tests.frontend.ast.whileTrue_test import HlsAstWhileTrue_TC
from tests.frontend.pyBytecode.basics_test import FromPythonBasics_TC
from tests.frontend.pyBytecode.errors_test import PyBytecodeErrors_TC
from tests.frontend.pyBytecode.fnClosue_test import FnClosure_TC
from tests.frontend.pyBytecode.llvmLoopUnroll_test import LlvmLoopUnroll_TC
from tests.frontend.pyBytecode.pragmaInline_test import PyBytecodeInline_TC
from tests.frontend.pyBytecode.preprocLoopMultiExit_test import PreprocLoopMultiExit_TCs
from tests.frontend.pyBytecode.pyArrHwIndex_test import PyArrHwIndex_TC
from tests.frontend.pyBytecode.pyArrShift_test import PyArrShift_TC
from tests.frontend.pyBytecode.stmFor_test import StmFor_TC
from tests.frontend.pyBytecode.stmIf_test import StmIf_TC
from tests.frontend.pyBytecode.variableChain_test import VariableChain_TC
from tests.hlsNetlist.bitwiseOpsAggregation import HlsNetlistBitwiseOpsTC
from tests.hlsNetlist.readSync import HlsNetlistReadSyncTC
from tests.hlsNetlist.wire import HlsNetlistWireTC
from tests.io.axiStream.axisPacketCntr_test import AxiSPacketCntrTC
from tests.io.axiStream.axisParseEth_test import AxiSParseEthTC
from tests.io.axiStream.axisParseIf_test import AxiSParseIfTC
from tests.io.axiStream.axisParseLinear_test import AxiSParseLinearTC
from tests.io.axiStream.axisWriteByte_test import AxiSWriteByteTC
from tests.io.bram.bramRead_test import BramRead_TC
from tests.io.ioFsm_test import IoFsm_TC
from tests.syntehesis_checks import HlsSynthesisChecksTC
from tests.utils.alapAsapDiffExample import AlapAsapDiffExample_TC
from tests.utils.phiConstructions_test import PhiConstruction_TC


def testSuiteFromTCs(*tcs):
    loader = TestLoader()
    for tc in tcs:
        tc._multiprocess_can_split_ = True
    loadedTcs = [loader.loadTestsFromTestCase(tc) for tc in tcs]
    suite = TestSuite(loadedTcs)
    return suite


suite = testSuiteFromTCs(
    AbcTC,
    HlsNetlistWireTC,
    HlsNetlistBitwiseOpsTC,
    SliceBreak_TC,
    HlsSlicingTC,
    BitWidthReductionCmp_example_TC,
    HlsNetlistReadSyncTC,
    HlsAstReadIfTc,
    HlsMAC_example_TC,
    *BitonicSorterHLS_TCs,
    HlsAstExprTree3_example_TC,
    AlapAsapDiffExample_TC,
    HlsSynthesisChecksTC,
    TwoTimesA_TC,
    AndShiftInLoop_TC,
    HlsAstTrivial_TC,
    HlsAstWhileIf_TC,
    HlsAstWhileTrue_TC,
    IoFsm_TC,
    PhiConstruction_TC,
    FromPythonBasics_TC,
    PyBytecodeErrors_TC,
    PyBytecodeInline_TC,
    PyArrShift_TC,
    *PreprocLoopMultiExit_TCs,
    FnClosure_TC,
    StmIf_TC,
    StmFor_TC,
    PyArrHwIndex_TC,
    VariableChain_TC,
    AxiSPacketCntrTC,
    AxiSParseEthTC,
    AxiSParseLinearTC,
    AxiSParseIfTC,
    AxiSWriteByteTC,
    BramRead_TC,
    LlvmLoopUnroll_TC,
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
    useParallerlTest = False

    if useParallerlTest:
        concurrent_suite = ConcurrentTestSuite(suite, fork_for_tests())
        res = runner.run(concurrent_suite)
    else:
        res = runner.run(suite)
    if not res.wasSuccessful():
        sys.exit(1)


if __name__ == '__main__':
    main()

