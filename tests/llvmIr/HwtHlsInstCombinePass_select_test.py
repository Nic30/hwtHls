#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsInstCombinePass_test import HwtHlsInstCombinePass_TC


class HwtHlsInstCombinePass_select_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return HwtHlsInstCombinePass_TC._runTestOpt(self, llvm)

    def test_tryReduceSelectInst_concatWithConst0(self):
        llvmIr = """\
        define void @tryReduceSelectInst_concatWithConst0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:
          %c0 = load volatile i1, ptr addrspace(2) %condIn, align 1
          %c1 = load volatile i1, ptr addrspace(2) %condIn, align 1
          %v0 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %c0) #2
          %v1 = select i1 %c1, i2 0, i2 %v0
          store volatile i2 %v1, ptr addrspace(3) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HwtHlsInstCombinePass_select_TC('test_tryReduceSelectInst_concatWithConst0')])
    suite = testLoader.loadTestsFromTestCase(HwtHlsInstCombinePass_select_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
