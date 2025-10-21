from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmMir.baseLlvmMirTC import BaseLlvmMirTC


class HwtFpgaPreRegAllocGICombiner_TC(BaseLlvmMirTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        llvm._testHwtFpgaPreRegAllocGICombiner()

    def test_extract_on_merge_values0(self):
        self._test_mir(f"""\
  bb.0.{self.getTestName()}:
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.bb1:
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
    %3:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
    %4:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
    %5:anyregcls(s48) = HWTFPGA_MERGE_VALUES %2(s16), %3(s16), %4(s16), 16, 16, 16
    %6:anyregcls(s16) = HWTFPGA_EXTRACT %5(s48), 48, 0, 16
    HWTFPGA_CSTORE %6(s16), %1, 0, 16, 1:: (volatile store (s16) into %ir.o, addrspace 2)
    %7:anyregcls(s16) = HWTFPGA_EXTRACT %5(s48), 48, 8, 16
    HWTFPGA_CSTORE %7(s16), %1, 0, 16, 1:: (volatile store (s16) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1

""")

    def test_merge_value_merge_continuous_slices0(self):
        self._test_mir(f"""\
  bb.0.{self.getTestName()}:
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.bb1:
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
    %3:anyregcls(s1) = HWTFPGA_EXTRACT %2(s16), 16, 1, 1
    %4:anyregcls(s2) = HWTFPGA_EXTRACT %2(s16), 16, 2, 2
    %5:anyregcls(s1) = HWTFPGA_EXTRACT %2(s16), 16, 4, 1
    %6:anyregcls(s4) = HWTFPGA_MERGE_VALUES %3(s1), %4(s2), %5(s1), 1, 2, 1

    HWTFPGA_CSTORE %6(s4), %1, 0, 4, 1:: (volatile store (s4) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1

""")
    def test_merge_value_merge_continuous_slices1(self):
        self._test_mir(f"""\
  bb.0.{self.getTestName()}:
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.bb1:
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
    %3:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1, 16 :: (volatile load (s16) from %ir.i, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_EXTRACT %2(s16), 16, 1, 1
    %5:anyregcls(s2) = HWTFPGA_EXTRACT %2(s16), 16, 2, 2
    %6:anyregcls(s1) = HWTFPGA_EXTRACT %2(s16), 16, 4, 1
    %7:anyregcls(s20) = HWTFPGA_MERGE_VALUES %3(s16), %4(s1), %5(s2), %6(s1), 16, 1, 2, 1
    HWTFPGA_CSTORE %7(s20), %1, 0, 20, 1:: (volatile store (s20) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1

""")
if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([HwtFpgaPreRegAllocGICombiner_TC('test_merge_value_merge_continuous_slices1')])
    # suite = testLoader.loadTestsFromTestCase(HwtFpgaPreToNetlistGICombiner_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)