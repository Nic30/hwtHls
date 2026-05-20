# -*- coding: utf-8 -*-
import multiprocessing
from typing import Callable, Optional

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, \
    parseIR, verifyModule
from tests.llvmIr.baseLlvmIrTC import generateAndAppendHwtHlsFunctionDeclarations


def llmIrStripInstrucionsUnrelatedToCrash(irStr: str, testFunction: Callable[[LlvmCompilationBundle], None], nprocs=None,
                                          logAfterChange=False, timeout:Optional[float]=None):
    """
    Attempt to remove as much instruction as possible while preserving crashing of the compiler.
    :note: Use this to obtain minimal example to trigger the bug.
    """
    irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
    scopeName = "llmIrStripInstrucionsUnrelatedToCrash"
    llvm = LlvmCompilationBundle(scopeName, [])
    Err = SMDiagnostic()
    M = parseIR(irStr, scopeName, Err, llvm.ctx)
    if M is None:
        raise AssertionError(Err.str(scopeName, True, True))
    else:
        fns = tuple(M)
        llvm.module = M
        llvm.main = fns[0]
        # name = llvm.main.getName().str()
    if verifyModule(M):
        raise AssertionError("The input module itself is already broken (this test that the function breaks on working code)")
        llvm = LlvmCompilationBundle(scopeName, [])

    if nprocs is None:
        nprocs = multiprocessing.cpu_count()
    llvm._testStripInstrucionUnrelatedToCrash(nprocs, testFunction, logAfterChange=logAfterChange, timeout=timeout)
    return llvm
    # print(str(llvm.main))
