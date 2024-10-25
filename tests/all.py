#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from unittest import TestLoader, TextTestRunner, TestSuite

from tests.adt.collections.hashTable_test import HashTable_TC
from tests.bitOpt.abc_NtkExpandExternalCombLoops_test import Abc_NtkExpandExternalCombLoops_TC
from tests.bitOpt.abc_test import AbcTC
from tests.bitOpt.andShiftInLoop_test import AndShiftInLoop_TC
from tests.bitOpt.cmpReduction_test import CmpReduction_TC
from tests.bitOpt.countBits_test import CountBitsTC
from tests.bitOpt.divNonRestoring_test import DivNonRestoring_TC
from tests.bitOpt.popcount_test import PopcountTC
from tests.bitOpt.shifter_test import ShifterTC
from tests.floatingpoint.add_test import IEEE754FpAdder_TC
from tests.floatingpoint.cmp_test import IEEE754FpCmp_TC
from tests.floatingpoint.fptypes_test import IEEE754Fp_TC
from tests.floatingpoint.fromInt_test import IEEE754FpFromInt_TC
from tests.math.fp.mul_test import IEEE754FpMultipier_TC
from tests.floatingpoint.toInt_test import IEEE754FpToInt_TC
from tests.frontend.ast.bitonicSort import BitonicSorterHLS_TCs
from tests.frontend.ast.exprTree3 import HlsAstExprTree3_example_TC
from tests.frontend.ast.ifstm import HlsSimpleIfStatement_TC
from tests.frontend.ast.loopAfterLoop import LoopAfterLoop_TC
from tests.frontend.ast.loopFollowedByIf import LoopFollowedByIf_TC
from tests.frontend.ast.mac import HlsMAC_example_TC
from tests.frontend.ast.readIf import HlsAstReadIfTc
from tests.frontend.ast.slicing import HlsSlicingTC
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.frontend.ast.twoTimesA import TwoTimesA_TC
from tests.frontend.ast.whileIf_test import HlsAstWhileIf_TC
from tests.frontend.ast.whileTrue_test import HlsAstWhileTrue_TC
from tests.frontend.pyBytecode.basics_test import FromPythonBasics_TC
from tests.frontend.pyBytecode.binToBcd_test import BinToBcd_TC
from tests.frontend.pyBytecode.errors_test import PyBytecodeErrors_TC
from tests.frontend.pyBytecode.fnClosue_test import FnClosure_TC
from tests.frontend.pyBytecode.hwrange_test import HlsPythonHwrange_TC
from tests.frontend.pyBytecode.pragmaInline_test import PyBytecodeInline_TC
from tests.frontend.pyBytecode.preprocLoopMultiExit_test import PreprocLoopMultiExit_TCs
from tests.frontend.pyBytecode.pyArrHwIndex_test import PyArrHwIndex_TC
from tests.frontend.pyBytecode.pyArrShift_test import PyArrShift_TC
from tests.frontend.pyBytecode.pyExceptionRaise_test import PyBytecodePyException_TC
from tests.frontend.pyBytecode.readNonBlocking_test import ReadNonBlocking_TC
from tests.frontend.pyBytecode.stmFor_test import StmFor_TC
from tests.frontend.pyBytecode.stmIf_test import StmIf_TC
from tests.frontend.pyBytecode.stmWhile_test import StmWhile_ll_TC, StmWhile_sim_TC
from tests.frontend.pyBytecode.tupleAssign import HlsPythonTupleAssign_TC
from tests.frontend.pyBytecode.varReference import VarReference_TC
from tests.frontend.pyBytecode.variableChain_test import VariableChain_TC
from tests.hlsNetlist.bitwiseOpsAggregation_test import HlsNetlistBitwiseOpsTC
from tests.hlsNetlist.breakHandshakeCycles_test import BreakHandshakeCycles_TC
from tests.hlsNetlist.netlistReduceMux_test import HlsNetlistReduceMuxTC
from tests.hlsNetlist.readNonBlocking_test import ReadNonBockingTC
from tests.hlsNetlist.readSync_test import HlsNetlistReadSyncTC
from tests.hlsNetlist.simplifyBackedgeWritePropagation_test import HlsCycleDelayHwModule
from tests.hlsNetlist.syncLowering_exprExtraction_negations_test import RtlArchPassSyncLowering_exprExtraction_negations_TC
from tests.hlsNetlist.syncLowering_exprExtraction_test import RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC
from tests.hlsNetlist.wire_test import HlsNetlistWireTC
from tests.io.amba.axi4Lite.axi4LiteCopy_test import Axi4LiteCopy_TC
from tests.io.amba.axi4Lite.axi4LiteRead_test import Axi4LiteRead_TC
from tests.io.amba.axi4Lite.axi4LiteWrite_test import Axi4LiteWrite_TC
from tests.io.amba.axi4Stream.axi4sCopyByteByByte_test import Axi4SPacketCopyByteByByteTC
from tests.io.amba.axi4Stream.axi4sPacketCntr_test import Axi4SPacketCntrTC
from tests.io.amba.axi4Stream.axi4sParseEth_test import Axi4SParseEthTC
from tests.io.amba.axi4Stream.axi4sParseIf_test import Axi4SParseIfTC
from tests.io.amba.axi4Stream.axi4sParseLinear_test import Axi4SParseLinearTC
from tests.io.amba.axi4Stream.axi4sPingResponder import Axi4SPingResponderTC
from tests.io.amba.axi4Stream.axi4sWriteByte_test import Axi4SWriteByteTC
from tests.io.bram.bramRead_test import BramRead_TC
from tests.io.bram.bramWrite_test import BramWrite_TC
from tests.io.bram.counterArray_test import BramCounterArray_TC
from tests.io.bram.readSizeFromRamAndSendSequence_test import ReadSizeFromRamAndSendSequence_TC
from tests.io.flushing_test import Flushing_TC
from tests.io.ioFsm2_test import IoFsm2_TC
from tests.io.ioFsm_test import IoFsm_TC
from tests.io.readAtleastOne_test import ReadAtleastOne_TC
from tests.llvmIr.PruneLoopPhiDeadIncomingValuesPass_test import PruneLoopPhiDeadIncomingValuesPass_TC
from tests.llvmIr.SimplifyCFG2Pass_test import SimplifyCFG2Pass_TC
from tests.llvmIr.bitWidthReductionPass_Cmp_test import BitWidthReductionPass_Cmp_example_TC
from tests.llvmIr.bitWidthReductionPass_PHI_test import BitwidthReductionPass_PHI_TC
from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC
from tests.llvmIr.llvmLoopUnroll_test import LlvmLoopUnroll_TC
from tests.llvmIr.loopFlattenUsingIfPass_test import LoopFlattenUsingIfPass_TC
from tests.llvmIr.loopUnrotatePass_test import LoopUnrotatePass_TC
from tests.llvmIr.rewriteExtractOnMergeValues_test import RewriteExtractOnMergeValuesPass_TC
from tests.llvmIr.selectPruningPass_test import SelectPruningPass_TC
from tests.llvmIr.slicesMergePass_test import SlicesMergePass_TC
from tests.llvmIr.slicesToIndependentVariablesPass_test import SlicesToIndependentVariablesPass_TC
from tests.llvmMir.earlyIfConverter_test import EarlyIfConverter_TC
from tests.llvmMir.vregIfConverter_test import VRegIfConverter_TC
from tests.syntehesisChecks_test import HlsSynthesisChecksTC
from tests.utils.alapAsapDiffExample import AlapAsapDiffExample_TC
from tests.utils.bitwiseOpsScheduling_test import BitwiseOpsScheduling_TC
from tests.utils.phiConstructions_test import PhiConstruction_TC
from tests.utils.schedulingNodeFunctions_test import SchedulingNodeFunctions_TC
from tests.crypto.md5_test import Md5_TC


def testSuiteFromTCs(*tcs):
    for tc in tcs:
        tc._multiprocess_can_split_ = True
    loader = TestLoader()
    loadedTcs = [loader.loadTestsFromTestCase(tc) for tc in tcs]
    suite = TestSuite(loadedTcs)
    return suite


suite = testSuiteFromTCs(
    AbcTC,
    Abc_NtkExpandExternalCombLoops_TC,
    SchedulingNodeFunctions_TC,
    HlsNetlistWireTC,
    HlsNetlistBitwiseOpsTC,
    HlsNetlistReduceMuxTC,
    #HlsNetlistPassInjectVldMaskToSkipWhenConditionsTC,
    HlsNetlistReadSyncTC,
    RtlArchPassSyncLowering_exprExtraction_1Pipeline_TC,
    RtlArchPassSyncLowering_exprExtraction_negations_TC,
    BreakHandshakeCycles_TC,
    Flushing_TC,
    SlicesToIndependentVariablesPass_TC,
    HlsSlicingTC,
    BitwiseOpsScheduling_TC,
    CountBitsTC,
    PopcountTC,
    ReadNonBockingTC,
    HlsCycleDelayHwModule,
    HlsPythonTupleAssign_TC,
    SimplifyCFG2Pass_TC,
    LoopUnrotatePass_TC,
    LoopFlattenUsingIfPass_TC,
    PruneLoopPhiDeadIncomingValuesPass_TC,
    RewriteExtractOnMergeValuesPass_TC,
    SlicesMergePass_TC,
    BitwidthReductionPass_TC,
    BitwidthReductionPass_PHI_TC,
    BitWidthReductionPass_Cmp_example_TC,
    SelectPruningPass_TC,
    CmpReduction_TC,
    EarlyIfConverter_TC,
    VRegIfConverter_TC,
    VarReference_TC,
    HlsPythonHwrange_TC,
    IEEE754Fp_TC,
    IEEE754FpCmp_TC,
    IEEE754FpFromInt_TC,
    IEEE754FpToInt_TC,
    IEEE754FpAdder_TC,
    IEEE754FpMultipier_TC,
    Md5_TC,
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
    ShifterTC,
    DivNonRestoring_TC,
    BinToBcd_TC,
    IoFsm_TC,
    IoFsm2_TC,
    LoopAfterLoop_TC,
    LoopFollowedByIf_TC,
    PhiConstruction_TC,
    FromPythonBasics_TC,
    PyBytecodeErrors_TC,
    PyBytecodePyException_TC,
    PyBytecodeInline_TC,
    PyArrShift_TC,
    *PreprocLoopMultiExit_TCs,
    FnClosure_TC,
    StmIf_TC,
    StmFor_TC,
    StmWhile_ll_TC,
    StmWhile_sim_TC,
    PyArrHwIndex_TC,
    VariableChain_TC,
    Axi4SPacketCntrTC,
    Axi4SParseEthTC,
    Axi4SParseLinearTC,
    Axi4SParseIfTC,
    Axi4SWriteByteTC,
    Axi4SPacketCopyByteByByteTC,
    BramRead_TC,
    BramWrite_TC,
    HashTable_TC,
    LlvmLoopUnroll_TC,
    Axi4SPingResponderTC,
    Axi4LiteRead_TC,
    Axi4LiteWrite_TC,
    Axi4LiteCopy_TC,
    BramCounterArray_TC,
    ReadSizeFromRamAndSendSequence_TC,
    ReadNonBlocking_TC,
    ReadAtleastOne_TC,
)


def main():
    # runner = TextTestRunner(verbosity=2, failfast=True)
    runner = TextTestRunner(verbosity=2)

    if len(sys.argv) > 1 and sys.argv[1] == "--singlethread":
        useParallelTest = False
    else:
        try:
            from concurrencytest import ConcurrentTestSuite, fork_for_tests
            useParallelTest = True
        except ImportError:
            # concurrencytest is not installed, use regular test runner
            useParallelTest = False
    #useParallelTest = False

    if useParallelTest:
        concurrent_suite = ConcurrentTestSuite(suite, fork_for_tests())
        res = runner.run(concurrent_suite)
    else:
        res = runner.run(suite)
    if not res.wasSuccessful():
        sys.exit(1)


if __name__ == '__main__':
    main()

