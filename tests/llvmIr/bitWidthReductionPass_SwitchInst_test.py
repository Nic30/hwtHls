#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class BitWidthReductionPass_SwitchInst_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testBitwidthReductionPass()

    def test_uselessSuffix(self):
        llvmIr = """\
            define void @test_uselessSuffix(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
            entry:
              br label %bb0
            bb0:
              %v = load volatile i2, ptr addrspace(1) %dataIn, align 4
              %cond = call i5 @hwtHls.bitConcat.i3.i2(i3 0, i2 %v) #2
              switch i5 %cond, label %bb.default [
                i5 0, label %bb.case0
                i5 8, label %bb.case8
                i5 -16, label %bb.case16
              ]
            
            bb.default:
              store volatile i8 15, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case0:
              store volatile i8 0, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case8:
              store volatile i8 8, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case16:
              store volatile i8 16, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            }
        """
        self._test_ll(llvmIr)

    def test_uselessSuffixCaseRm(self):
        llvmIr = """\
            define void @test_uselessSuffixCaseRm(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
            entry:
              br label %bb0
            bb0:
              %v = load volatile i2, ptr addrspace(1) %dataIn, align 4
              %cond = call i5 @hwtHls.bitConcat.i3.i2(i3 0, i2 %v) #2
              switch i5 %cond, label %bb.default [
                i5 0, label %bb.case0
                i5 9, label %bb.case8
                i5 -16, label %bb.case16
              ]
            
            bb.default:
              store volatile i8 15, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case0:
              store volatile i8 0, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case8:
              store volatile i8 8, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case16:
              store volatile i8 16, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            }
        """
        self._test_ll(llvmIr)

    def test_uselessInMiddle(self):
        llvmIr = """\
            define void @test_uselessInMiddle(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
            entry:
              br label %bb0
            bb0:
              %v = load volatile i2, ptr addrspace(1) %dataIn, align 4
              %cond = call i5 @hwtHls.bitConcat.i2.i2.i1(i2 0, i2 %v, i1 0) #2
              switch i5 %cond, label %bb.default [
                i5 0, label %bb.case0
                i5 8, label %bb.case8
                i5 -16, label %bb.case16
              ]
            
            bb.default:
              store volatile i8 15, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case0:
              store volatile i8 0, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case8:
              store volatile i8 8, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            bb.case16:
              store volatile i8 16, ptr addrspace(2) %dataOut, align 4
              br label %bb0
            }
        """
        self._test_ll(llvmIr)

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BitWidthReductionPass_SwitchInst_TC('test_uselessBitsInMiddle')])
    suite = testLoader.loadTestsFromTestCase(BitWidthReductionPass_SwitchInst_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
