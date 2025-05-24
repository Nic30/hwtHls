#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtLib.tests.all import unittestMain
from tests.frontend.bitonicSort import BitonicSorterHLS_TCs
from tests.frontend.exprTree3 import HlsAstExprTree3_example_TC
from tests.frontend.ifstm import HlsSimpleIfStatement_TC
from tests.frontend.loopAfterLoop import LoopAfterLoop_TC
from tests.frontend.loopFollowedByIf import LoopFollowedByIf_TC
from tests.frontend.mac import HlsMAC_example_TC
from tests.frontend.readIf import HlsAstReadIfTc
from tests.frontend.slicing import HlsSlicingTC
from tests.frontend.trivial_test import HlsAstTrivial_TC
from tests.frontend.twoTimesA import TwoTimesA_TC
from tests.frontend.whileIf_test import HlsAstWhileIf_TC
from tests.frontend.whileTrue_test import HlsAstWhileTrue_TC
from tests.frontend.pyBytecode.basics_test import FromPythonBasics_TC
from tests.frontend.pyBytecode.binToBcd_test import BinToBcd_TC
from tests.frontend.pyBytecode.errors_test import PyBytecodeErrors_TC
from tests.frontend.pyBytecode.fnClosue_test import FnClosure_TC
from tests.frontend.pyBytecode.hwenumerate_test import HlsPythonHwenumerate_TC
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
from tests.testCaseUtils import testSuiteFromTCs

frontend_TCs = [
    HlsSlicingTC,
    HlsPythonTupleAssign_TC,
    VarReference_TC,
    HlsPythonHwrange_TC,
    HlsPythonHwenumerate_TC,
    HlsAstReadIfTc,
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
    VariableChain_TC,
    ReadNonBlocking_TC,
]

if __name__ == '__main__':
    unittestMain(testSuiteFromTCs(*frontend_TCs))

