#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.baseSsaTest import BaseSsaTC
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.bitWidthReductionPass_Cmp import BitWidthReductionCmp2Values, \
    BitWidthReductionCmpReducibleEq, BitWidthReductionCmpReducibleNe, \
    BitWidthReductionCmpReducibleLt, BitWidthReductionCmpReducibleLe, \
    BitWidthReductionCmpReducibleGt, BitWidthReductionCmpReducibleGe
from tests.llvmIr.bitWidthReduction_test import BitwidthReductionPass_TC


class BitWidthReductionPass_Cmp_example_TC(BaseSsaTC):
    __FILE__ = __file__
    TEST_FRONTEND = True
    TEST_MIR = True
    TEST_BLOCK_SYNC = False

    def test_BitWidthReductionCmpReducibleEq_ll(self):
        self._test_ll(BitWidthReductionCmpReducibleEq)

    def test_BitWidthReductionCmpReducibleNe_ll(self):
        self._test_ll(BitWidthReductionCmpReducibleNe)

    def test_BitWidthReductionCmpReducibleLt_ll(self):
        self._test_ll(BitWidthReductionCmpReducibleLt)

    def test_BitWidthReductionCmpReducibleLe_ll(self):
        self._test_ll(BitWidthReductionCmpReducibleLe)

    def test_BitWidthReductionCmpReducibleGt_ll(self):
        self._test_ll(BitWidthReductionCmpReducibleGt)

    def test_BitWidthReductionCmpReducibleGe_ll(self):
        self._test_ll(BitWidthReductionCmpReducibleGe)

    def test_BitWidthReductionCmp2Values_ll(self):
        self._test_ll(BitWidthReductionCmp2Values)


class BitWidthReductionPass_Cmp_IR_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return BitwidthReductionPass_TC._runTestOpt(self, llvm)

    def test_cmpUltLowerBits0(self):
        llvmIr = """\
        define void @test_cmpUltLowerBits0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          br label %bb1
        
        bb1:
          %a = load volatile i5, ptr addrspace(1) %dataIn, align 32
          %b = call i7 @hwtHls.bitConcat.i2.i5(i2 0, i5 %a) #2
          %c0 = icmp ult i7 %b, 2 ; should convert to %a == 0 
          store volatile i1 %c0, ptr addrspace(2) %dataOut, align 32
          br label %bb1
        }
        """
        self._test_ll(llvmIr)

    def test_cmpUleLowerBits0(self):
        llvmIr = """\
        define void @test_cmpUleLowerBits0(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb0:
          br label %bb1
        
        bb1:
          %a = load volatile i5, ptr addrspace(1) %dataIn, align 32
          %b = call i7 @hwtHls.bitConcat.i2.i5(i2 0, i5 %a) #2
          %c = icmp ule i7 %b, 2 ; should convert to true
          store volatile i1 %c, ptr addrspace(2) %dataOut, align 32
          br label %bb1
        }
        """
        self._test_ll(llvmIr)


BitWidthReductionPass_Cmp_TCs = [
    BitWidthReductionPass_Cmp_example_TC,
    BitWidthReductionPass_Cmp_IR_TC,
]

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite(testLoader.loadTestsFromTestCase(tc)
                          for tc in BitWidthReductionPass_Cmp_TCs)
    # suite = unittest.TestSuite([BitWidthReductionPass_Cmp_example_TC('test_BitWidthReductionCmp2Values_ll')])
    # suite = testLoader.loadTestsFromTestCase(BitWidthReductionPass_Cmp_IR_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
