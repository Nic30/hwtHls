#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class HFloatTmpLoweringPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testHFloatTmpLoweringPass()

    def test_addSub(self):
        llvmIr = """\
        define void @test_addSub(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i5, ptr addrspace(1) %dataIn, align 1
          %v0 = call double @hwtHls.fp.castToHFloatTmp.i5(i5 %r0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %res0.0 = fsub double 5.000000e-01, %v0
          %res1.0 = fadd double %v0, -5.000000e-01
          %res0.1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %res0.0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %res1.1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %res1.0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          store volatile i5 %res0.1, ptr addrspace(2) %dataOut, align 2
          store volatile i5 %res1.1, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)
    
    def test_addSubUnsigned(self):
        llvmIr = """\
        define void @test_addSubUnsigned(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i5, ptr addrspace(1) %dataIn, align 1
          %v0 = call double @hwtHls.fp.castToHFloatTmp.i5(i5 %r0, i1 true, i8 2, i8 3, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %res0.0 = fsub double 5.000000e-01, %v0
          %res1.0 = fadd double %v0, -5.000000e-01
          %res0.1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %res0.0, i1 true, i8 2, i8 3, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %res1.1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %res1.0, i1 true, i8 2, i8 3, i1 false, i1 false, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          store volatile i5 %res0.1, ptr addrspace(2) %dataOut, align 2
          store volatile i5 %res1.1, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        with self.assertRaises(Exception):
            self._test_ll(llvmIr)

    def test_nopCast(self):
        llvmIr = """\
        define void @test_nopCast(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i5, ptr addrspace(1) %dataIn, align 1
          %v0 = call double @hwtHls.fp.castToHFloatTmp.i5(i5 %r0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %v0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          store volatile i5 %v1, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_nopCast2x(self):
        llvmIr = """\
        define void @test_nopCast2x(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i5, ptr addrspace(1) %dataIn, align 1
          %v0 = call double @hwtHls.fp.castToHFloatTmp.i5(i5 %r0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %v0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v0.1 = call double @hwtHls.fp.castToHFloatTmp.i5(i5 %v1, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v1.1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %v0.1, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          store volatile i5 %v1.1, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)

    def test_nopCast2xDifferent(self):
        llvmIr = """\
        define void @test_nopCast2xDifferent(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) {
        bb.0:
          %r0 = load volatile i6, ptr addrspace(1) %dataIn, align 1
          %v0 = call double @hwtHls.fp.castToHFloatTmp.i6(i6 %r0, i1 true, i8 3, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v1 = call i6 @hwtHls.fp.castFromHFloatTmp.i6(double %v0, i1 true, i8 3, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v1.casted = call i5 @hwtHls.fp.castHFloatTmpToHFloatTmpRaw.i6.i5(i6 %v1, i1 true, i8 3, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v0.1 = call double @hwtHls.fp.castToHFloatTmp.i5(i5 %v1.casted, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          %v1.1 = call i5 @hwtHls.fp.castFromHFloatTmp.i5(double %v0.1, i1 true, i8 2, i8 3, i1 false, i1 true, i1 false, i1 false, i1 false, i1 false, i8 4, i8 0) #5
          store volatile i5 %v1.1, ptr addrspace(2) %dataOut, align 2
          ret void
        }
        """
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HFloatTmpLoweringPass_TC('test_nopCast2xDifferent')])
    suite = testLoader.loadTestsFromTestCase(HFloatTmpLoweringPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
