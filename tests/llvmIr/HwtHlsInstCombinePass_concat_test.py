#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsInstCombinePass_test import HwtHlsInstCombinePass_TC


class HwtHlsInstCombinePass_concat_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return HwtHlsInstCombinePass_TC._runTestOpt(self, llvm)

    def test_tryReduceSelectInst_concatWithConst0(self):
        llvmIr = """\
        define void @test_tryReduceSelectInst_concatWithConst0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
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
    
    def test_tryReduceBitRangeGetOnConcat_sliceOnConcat0(self):
        # if the select on concatenation does select exactly some members, we should rewrite it as a cocat of those members
        llvmIr = """\
        define void @test_tryReduceBitRangeGetOnConcat_sliceOnConcat0(ptr addrspace(1) %dataIn, ptr addrspace(2) %condIn, ptr addrspace(3) %dataOut) {
        bb.0:
          %v0 = load volatile i8, ptr addrspace(2) %condIn, align 1
          %v1 = load volatile i8, ptr addrspace(2) %condIn, align 1
          %v2 = load volatile i1, ptr addrspace(2) %condIn, align 1
          %v3 = call i17 @hwtHls.bitConcat.i8.i8.i1(i8 %v0, i8 %v1, i1 %v2) #2
          %v4 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %v3, i6 0) #2
          store volatile i16 %v4, ptr addrspace(3) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)
    
if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsInstCombinePass_concat_TC)
    # suite = unittest.TestSuite([HwtHlsInstCombinePass_concat_TC('test_tryReduceBitRangeGetOnConcat_sliceOnConcat0')])
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
