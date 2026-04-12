#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from hwtHls.llvm.llvmIr import FunctionPassManager, ExtractBitConcatAndSliceOpsPass


class ExtractBitConcatAndSliceOpsPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:

        def _addHwtHlsInstCombinePass(FPM:FunctionPassManager):
            FPM.addPass(ExtractBitConcatAndSliceOpsPass())

        return llvm._runCustomFunctionPass(_addHwtHlsInstCombinePass)

    def test_tryOrToBitConcat_0(self):
        llvmIr = """\
        define void @test_tryOrToBitConcat_0(ptr addrspace(1) %o) {
        bb0:
          br label %bb1
        
        bb1:
          %i.0 = phi i3 [ %i.2, %bb1 ], [ 0, %bb0 ]
          %i.1 = zext i3 %i.0 to i64
          %v = or disjoint i64 %i.1, 8
          store volatile i64 %v, ptr addrspace(1) %o, align 8
          %i.2 = add i3 %i.0, 1
          br label %bb1
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HwtHlsInstCombinePass_select_TC('test_tryReduceSelectInst_concatWithConst0')])
    suite = testLoader.loadTestsFromTestCase(ExtractBitConcatAndSliceOpsPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
