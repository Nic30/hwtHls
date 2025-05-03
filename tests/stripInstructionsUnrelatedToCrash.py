# -*- coding: utf-8 -*-
from typing import Callable

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, \
    parseIR, verifyModule
from tests.llvmIr.baseLlvmIrTC import generateAndAppendHwtHlsFunctionDeclarations


def llmIrStripInstrucionsUnrelatedToCrash(irStr: str, testFunction: Callable[[LlvmCompilationBundle], None]):
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
        raise AssertionError()
        llvm = LlvmCompilationBundle(scopeName, [])
    llvm._testStripInstrucionUnrelatedToCrash(6, testFunction)
    return llvm
    #print(str(llvm.main))
