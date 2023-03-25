import os

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, parseIR
from tests.baseSsaTest import BaseSsaTC


class SlicesMergePass_TC(BaseSsaTC):
    __FILE__ = __file__

    def _test_ll(self, irStr: str):
        llvm = LlvmCompilationBundle("test")
        Err = SMDiagnostic()
        M = parseIR(irStr, "test", Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            fns = tuple(M)
            llvm.main = fns[0]
            name = llvm.main.getName().str()

        optF = llvm._testSlicesMergePass()
        self.assert_same_as_file(repr(optF), os.path.join("data", 'SlicesMergePass_TC.' + name + ".ll"))

    def test_notingToReduce(self):
        llvmIr0 = """
        define void @notingToReduce() {
          ret void
        }
        """
        self._test_ll(llvmIr0)

    def test_mergeConst(self):
        ir = """
        define void @mergeConst(i8 addrspace(2)* %o) {
          %1 = call i8 @hwtHls.bitConcat.i4.i4(i4 1, i4 2)
          store volatile i8 %1, i8 addrspace(2)* %o, align 1
          ret void
        }
        ; Function Attrs: nofree nounwind readnone willreturn
        declare i8 @hwtHls.bitConcat.i4.i4(i4 %0, i4 %1) #0

        attributes #0 = { nofree nounwind readnone willreturn }
        """
        self._test_ll(ir)


    def test_mergeBecauseOfConcat(self):
        ir = """
        define void @mergeBecauseOfConcat(i8 addrspace(1)* %i, i8 addrspace(2)* %o) {
          BB0:
            %i0 = load volatile i8, i8 addrspace(1)* %i, align 1
            %0 = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i0, i64 0)
            %1 = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i0, i64 4)
            br label %BB1

          BB1:
            %2 = call i8 @hwtHls.bitConcat.i4.i4(i4 %0, i4 %1)
            store volatile i8 %2, i8 addrspace(2)* %o, align 1
            br label %BB1
        }
        ; Function Attrs: nofree nounwind readnone willreturn
        declare i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %0, i64 %1) #0

        ; Function Attrs: nofree nounwind readnone willreturn
        declare i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %0, i64 %1) #0

        ; Function Attrs: nofree nounwind readnone willreturn
        declare i8 @hwtHls.bitConcat.i4.i4(i4 %0, i4 %1) #0

        attributes #0 = { nofree nounwind readnone willreturn }
        """
        self._test_ll(ir)


    def test_phiShift(self):
        ir = """
        define void @phiShift(i4 addrspace(1)* %i, i4 addrspace(2)* %o) {
          BB0:
            br label %BB1

          BB1:
            %i0 = load volatile i4, i4 addrspace(1)* %i, align 1
            %0 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %i0, i64 0)
            %1 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.1(i4 %i0, i64 1)
            %2 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.2(i4 %i0, i64 2)
            %3 = call i1 @hwtHls.bitRangeGet.i4.i64.i1.3(i4 %i0, i64 3)
            br label %BB2
          BB2: ; i0 >>= 1
            %4 = phi i1 [ %0, %BB1 ], [ %5, %BB2 ]
            %5 = phi i1 [ %1, %BB1 ], [ %6, %BB2 ]
            %6 = phi i1 [ %2, %BB1 ], [ %7, %BB2 ]
            %7 = phi i1 [ %3, %BB1 ], [ 0, %BB2 ]
            store volatile i4 11, i4 addrspace(2)* %o, align 1
            br i1 %4, label %BB2, label %BB1 ; while (i0 & 1)

        }
        ; Function Attrs: nofree nounwind readnone willreturn
        declare i1 @hwtHls.bitRangeGet.i4.i64.i1.0(i4 %0, i64 %1) #0

        ; Function Attrs: nofree nounwind readnone willreturn
        declare i1 @hwtHls.bitRangeGet.i4.i64.i1.1(i4 %0, i64 %1) #0

        ; Function Attrs: nofree nounwind readnone willreturn
        declare i1 @hwtHls.bitRangeGet.i4.i64.i1.2(i4 %0, i64 %1) #0

        ; Function Attrs: nofree nounwind readnone willreturn
        declare i1 @hwtHls.bitRangeGet.i4.i64.i1.3(i4 %0, i64 %1) #0

        attributes #0 = { nofree nounwind readnone willreturn }
        """
        self._test_ll(ir)

    def test_parallelAnd(self):
        ir = """
        define void @parallelAnd(i8 addrspace(1)* %i0, i8 addrspace(1)* %i1, i4 addrspace(2)* %o0, i4 addrspace(2)* %o1) {
            %i00 = load volatile i8, i8 addrspace(1)* %i0, align 1
            %i10 = load volatile i8, i8 addrspace(1)* %i1, align 1
            %"0" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i00, i64 0)
            %"1" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i00, i64 4)
            %"2" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %i10, i64 0)
            %"3" = call i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %i10, i64 4)
            %"4" = and i4 %"0", %"2"
            %"5" = and i4 %"1", %"3"
            store volatile i4 %"4", i4 addrspace(2)* %o0, align 1
            store volatile i4 %"5", i4 addrspace(2)* %o1, align 1
            ret void
        }
        ; Function Attrs: nofree nounwind readnone willreturn
        declare i4 @hwtHls.bitRangeGet.i8.i64.i4.0(i8 %0, i64 %1) #0

        ; Function Attrs: nofree nounwind readnone willreturn
        declare i4 @hwtHls.bitRangeGet.i8.i64.i4.4(i8 %0, i64 %1) #0

        attributes #0 = { nofree nounwind readnone willreturn }
        """
        self._test_ll(ir)


if __name__ == "__main__":
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = SliceBreak3()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(SlicesMergePass_TC('test_phiShift'))
    suite.addTest(unittest.makeSuite(SlicesMergePass_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
