#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, verifyFunction, \
    FunctionPassManager, StreamReadLoweringPass
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


def _addStreamReadLoweringPass(FPM: FunctionPassManager):
    FPM.addPass(StreamReadLoweringPass())


class StreamReadLoweringPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        # llvm.addLlvmCliArgOccurence("debug-only", 0, "", "newgvn")
        F = llvm._runCustomFunctionPass(_addStreamReadLoweringPass)
        if verifyFunction(F):
            raise AssertionError()
        return F

    def _test_ir_file(self, use_generateAndAppendHwtHlsFunctionDeclarations=False):
        nameOfMain = self.getTestName()
        inputFileName = Path(self.__FILE__).expanduser().resolve().parent / "dataIn" / (nameOfMain + ".in.ir.ll")
        with open(inputFileName) as f:
            self._test_ll(f.read(), use_generateAndAppendHwtHlsFunctionDeclarations=use_generateAndAppendHwtHlsFunctionDeclarations)

    def test_copy2B(self):
        # based on:
        # m = Axi4SPacketCopyByteByByte()
        # m.UNROLL = None
        # m.DATA_WIDTH = 2 * 8
        # m.OUT_DATA_WIDTH = 2 * 8
        self._test_ir_file()


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle
    # m = SliceBreak3()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SlicesMergePass_select_TC('test_selectSub0')])
    suite = testLoader.loadTestsFromTestCase(StreamReadLoweringPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
