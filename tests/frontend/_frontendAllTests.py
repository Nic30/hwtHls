#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.frontend.basics_test import FromPythonBasics_TC
from tests.frontend.binToBcd_test import BinToBcd_TC
from tests.frontend.bitonicSort import BitonicSorterHLS_TCs
from tests.frontend.errors_test import PyBytecodeErrors_TC
from tests.frontend.exprTree3_test import HlsAstExprTree3_example_TC
from tests.frontend.fnCall_test import FnCall_TC
from tests.frontend.fnClosue_test import FnClosure_TC
from tests.frontend.hStructAssign_test import HStructAssign_TC
from tests.frontend.hwenumerate_test import HlsPythonHwenumerate_TC
from tests.frontend.hwrange_test import HlsPythonHwrange_TC
from tests.frontend.ifstm_test import HlsSimpleIfStatement_TC
from tests.frontend.loopAfterLoop_test import LoopAfterLoop_TC
from tests.frontend.loopFollowedByIf_test import LoopFollowedByIf_TC
from tests.frontend.mac_test import HlsMAC_example_TC
from tests.frontend.pragmaInline_test import PyBytecodeInline_TC
from tests.frontend.preprocLoopMultiExit_test import PreprocLoopMultiExit_TCs
from tests.frontend.pyArrHwIndex_test import PyArrHwIndex_TC
from tests.frontend.pyArrShift_test import PyArrShift_TC
from tests.frontend.pyExceptionRaise_test import PyBytecodePyException_TC
from tests.frontend.readHwIOArray_test import ReadHwIOArray_TC
from tests.frontend.readIf_test import HlsAstReadIfTc
from tests.frontend.readNonBlocking_test import ReadNonBlocking_TC
from tests.frontend.slicing_test import HlsSlicingTC
from tests.frontend.stmFor_test import StmFor_TC
from tests.frontend.stmIf_test import StmIf_TC
from tests.frontend.stmWhile_test import StmWhile_ll_TC, StmWhile_sim_TC
from tests.frontend.trivial_test import HlsAstTrivial_TC
from tests.frontend.tupleAssign_test import HlsPythonTupleAssign_TC
from tests.frontend.twoTimesA_test import TwoTimesA_TC
from tests.frontend.varReference_test import VarReference_TC
from tests.frontend.variableChain_test import VariableChain_TC
from tests.frontend.whileIf_test import HlsAstWhileIf_TC
from tests.frontend.whileTrue_test import HlsAstWhileTrue_TC
from tests.testCaseUtils import testSuiteFromTCs
from tests.frontend.opcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST import TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST_TC

frontend_TCs = [
    TestOpcode_LOAD_FAST_LOAD_FAST__STORE_FAST_STORE_FAST_TC ,
    FnCall_TC,
    HlsSlicingTC,
    HlsPythonTupleAssign_TC,
    VarReference_TC,
    HlsPythonHwrange_TC,
    HlsPythonHwenumerate_TC,
    HlsAstReadIfTc,
    ReadHwIOArray_TC,
    *PreprocLoopMultiExit_TCs,
    *BitonicSorterHLS_TCs,
    HlsMAC_example_TC,
    HlsAstExprTree3_example_TC,
    HlsSimpleIfStatement_TC,
    TwoTimesA_TC,
    HlsAstTrivial_TC,
    HlsAstWhileIf_TC,
    HlsAstWhileTrue_TC,
    BinToBcd_TC,
    LoopAfterLoop_TC,
    LoopFollowedByIf_TC,
    FromPythonBasics_TC,
    PyBytecodeErrors_TC,
    PyBytecodePyException_TC,
    PyBytecodeInline_TC,
    PyArrShift_TC,
    FnClosure_TC,
    StmIf_TC,
    StmFor_TC,
    StmWhile_ll_TC,
    StmWhile_sim_TC,
    PyArrHwIndex_TC,
    HStructAssign_TC,
    VariableChain_TC,
    ReadNonBlocking_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*frontend_TCs))

