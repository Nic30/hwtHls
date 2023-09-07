import os

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, parseIR
from tests.baseSsaTest import BaseSsaTC
from tests.bitOpt.slicesMergePass_test import generateAndAppendHwtHlsFunctionDeclarations
from tests.bitOpt.rewriteExtractOnMergeValues_test import RewriteExtractOnMergeValuesPass_TC


class BitwidthReductionPass_TC(BaseSsaTC):
    __FILE__ = __file__

    def _test_ll(self, irStr: str):
        irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
        llvm = LlvmCompilationBundle("test")
        Err = SMDiagnostic()
        M = parseIR(irStr, "test", Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            fns = tuple(M)
            llvm.main = fns[0]
            name = llvm.main.getName().str()

        optF = llvm._testBitwidthReductionPass()
        self.assert_same_as_file(repr(optF), os.path.join("data", self.__class__.__name__ + '.' + name + ".ll"))

    def test_constInConcat0(self):
        llvmIr = """\
            define void @constInConcat0(ptr addrspace(1) %dataOut) {
            AxiSWriteByte.mainThread:
              %0 = call i16 @hwtHls.bitConcat.i8.i8(i8 1, i8 0) #2
              %1 = call i19 @hwtHls.bitConcat.i16.i2.i1(i16 %0, i2 1, i1 true) #2
              br label %blockL42i0_42
            
            blockL42i0_42:                                    ; preds = %blockL42i0_42, %AxiSWriteByte.mainThread
              store volatile i19 %1, ptr addrspace(1) %dataOut, align 4
              br label %blockL42i0_42
            }
        """
        self._test_ll(llvmIr)

    def test_constInConcat1(self):
        llvmIr = """\
        define void @constInConcat1(ptr addrspace(1) %rx, ptr addrspace(2) %txBody) {
            bb0:
              br label %bb1
            
            bb1:
              %rxRaw0 = load volatile i19, ptr addrspace(1) %rx, align 4
              %rxStrb1 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19 %rxRaw0, i6 17) #2
              %rxStrb0 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19 %rxRaw0, i6 16) #2
              %rxData0to8 = call i8 @hwtHls.bitRangeGet.i19.i6.i8.0(i19 %rxRaw0, i6 0) #2
              %rxData0to16 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %rxRaw0, i6 0) #2
              ; %rxStrb = call i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19 %rxRaw0, i6 16) #2
              %rxLast = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %rxRaw0, i6 18) #2
              %0 = xor i1 %rxStrb1, true
              %1 = and i1 %rxLast, %0
              %rxRaw1 = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %rxData0to8, i1 %rxStrb0, i1 %1) #2
              %2 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rxRaw1, i5 0) #2
              %3 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rxRaw1, i5 9) #2
              %4 = call i16 @hwtHls.bitConcat.i8.i8(i8 %2, i8 0) #2
  
              %5 = call i19 @hwtHls.bitConcat.i16.i2.i1(i16 %rxData0to16, i2 1, i1 %rxLast) #2
              store volatile i19 %5, ptr addrspace(2) %txBody, align 4
              ret void
        }
        """
        self._test_ll(llvmIr)

    def test_sliceBr(self):
        RewriteExtractOnMergeValuesPass_TC.test_sliceBr(self)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BitwidthReductionPass_TC('test_sliceBr')])
    suite = testLoader.loadTestsFromTestCase(BitwidthReductionPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
