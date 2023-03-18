#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from unittest import TestLoader, TextTestRunner, TestSuite

from tests.bitOpt.abc_test import AbcTC
from tests.bitOpt.andShiftInLoop import AndShiftInLoop_TC
from tests.bitOpt.bitWidthReductionCmp_test import BitWidthReductionCmp_example_TC
from tests.bitOpt.cmpReduction_test import CmpReduction_TC
from tests.bitOpt.slicesToIndependentVariablesPass_test import SlicesToIndependentVariablesPass_TC
from tests.frontend.ast.bitonicSort import BitonicSorterHLS_TCs
from tests.frontend.ast.exprTree3 import HlsAstExprTree3_example_TC
from tests.frontend.ast.ifstm import HlsSimpleIfStatement_TC
from tests.frontend.ast.mac import HlsMAC_example_TC
from tests.frontend.ast.readIf import HlsAstReadIfTc
from tests.frontend.ast.slicing import HlsSlicingTC
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.frontend.ast.twoTimesA import TwoTimesA_TC
from tests.frontend.ast.whileIf_test import HlsAstWhileIf_TC
from tests.frontend.ast.whileTrue_test import HlsAstWhileTrue_TC
from tests.frontend.pyBytecode.basics_test import FromPythonBasics_TC
from tests.frontend.pyBytecode.counterArray_test import CounterArray_TC
from tests.frontend.pyBytecode.errors_test import PyBytecodeErrors_TC
from tests.frontend.pyBytecode.fnClosue_test import FnClosure_TC
from tests.frontend.pyBytecode.hashTable_test import HashTable_TC
from tests.frontend.pyBytecode.llvmLoopUnroll_test import LlvmLoopUnroll_TC
from tests.frontend.pyBytecode.pragmaInline_test import PyBytecodeInline_TC
from tests.frontend.pyBytecode.preprocLoopMultiExit_test import PreprocLoopMultiExit_TCs
from tests.frontend.pyBytecode.pyArrHwIndex_test import PyArrHwIndex_TC
from tests.frontend.pyBytecode.pyArrShift_test import PyArrShift_TC
from tests.frontend.pyBytecode.readNonBlocking_test import ReadNonBlocking_TC
from tests.frontend.pyBytecode.stmFor_test import StmFor_TC
from tests.frontend.pyBytecode.stmIf_test import StmIf_TC
from tests.frontend.pyBytecode.stmWhile_test import StmWhile_TC
from tests.frontend.pyBytecode.tupleAssign import HlsPythonTupleAssign_TC
from tests.frontend.pyBytecode.variableChain_test import VariableChain_TC
from tests.hlsNetlist.bitwiseOpsAggregation import HlsNetlistBitwiseOpsTC
from tests.hlsNetlist.discoverSyncIsland_test import HlsNetlistDiscoverSyncIslandTC
from tests.hlsNetlist.netlistReduceCmpInAnd_test import HlsNetlistReduceCmpInAndTC
from tests.hlsNetlist.readNonBlocking import ReadNonBockingTC
from tests.hlsNetlist.readSync import HlsNetlistReadSyncTC
from tests.hlsNetlist.simplifyBackedgeWritePropagation_test import HlsCycleDelayUnit
from tests.hlsNetlist.wire import HlsNetlistWireTC
from tests.io.amba.axi4Lite.axi4LiteRead_test import Axi4LiteRead_TC
from tests.io.amba.axi4Lite.axi4LiteWrite_test import Axi4LiteWrite_TC
from tests.io.amba.axiStream.axisPacketCntr_test import AxiSPacketCntrTC
from tests.io.amba.axiStream.axisParseEth_test import AxiSParseEthTC
from tests.io.amba.axiStream.axisParseIf_test import AxiSParseIfTC
from tests.io.amba.axiStream.axisParseLinear_test import AxiSParseLinearTC
from tests.io.amba.axiStream.axisWriteByte_test import AxiSWriteByteTC
from tests.io.amba.axiStream.pingResponder import PingResponderTC
from tests.io.bram.bramRead_test import BramRead_TC
from tests.io.bram.bramWrite_test import BramWrite_TC
from tests.io.ioFsm_test import IoFsm_TC
from tests.io.readAtleastOne_test import ReadAtleastOne_TC
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
    HlsNetlistDiscoverSyncIslandTC,
    HlsNetlistReduceCmpInAndTC,
    SlicesToIndependentVariablesPass_TC,
    HlsSlicingTC,
    ReadNonBockingTC,
    HlsCycleDelayUnit,
    HlsPythonTupleAssign_TC,
    BitWidthReductionCmp_example_TC,
    CmpReduction_TC,
    HlsNetlistReadSyncTC,
    HlsAstReadIfTc,
    HlsMAC_example_TC,
    *BitonicSorterHLS_TCs,
    HlsAstExprTree3_example_TC,
    HlsSimpleIfStatement_TC,
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
    StmWhile_TC,
    PyArrHwIndex_TC,
    VariableChain_TC,
    AxiSPacketCntrTC,
    AxiSParseEthTC,
    AxiSParseLinearTC,
    AxiSParseIfTC,
    AxiSWriteByteTC,
    BramRead_TC,
    BramWrite_TC,
    HashTable_TC,
    LlvmLoopUnroll_TC,
    PingResponderTC,
    Axi4LiteRead_TC,
    Axi4LiteWrite_TC,
    CounterArray_TC,
    ReadNonBlocking_TC,
    ReadAtleastOne_TC,
)


def main():
    # runner = TextTestRunner(verbosity=2, failfast=True)
    runner = TextTestRunner(verbosity=2)

    try:
        from concurrencytest import ConcurrentTestSuite, fork_for_tests
        useParallelTest = True
    except ImportError:
        # concurrencytest is not installed, use regular test runner
        useParallelTest = False
    # useParallelTest = False

    if useParallelTest:
        concurrent_suite = ConcurrentTestSuite(suite, fork_for_tests())
        res = runner.run(concurrent_suite)
    else:
        res = runner.run(suite)
    if not res.wasSuccessful():
        sys.exit(1)


if __name__ == '__main__':
    main()

