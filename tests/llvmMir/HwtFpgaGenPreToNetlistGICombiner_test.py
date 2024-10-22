from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmMir.baseLlvmMirTC import BaseLlvmMirTC


class HwtFpgaPreToNetlistGICombiner_TC(BaseLlvmMirTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        llvm._testHwtFpgaPreToNetlistCombiner()

    def test_mux_merge0(self):
        self._test_mir_file()

    def test_mux_merge_twoWritingSameReg1(self):
        self._test_mir(f"""\
  bb.0.{self.getTestName()}:
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.bb1:

    %2:anyregcls(s16) = IMPLICIT_DEF ; %2 is register holding value between loop iterations
  
  bb.2.bb2:
  
    %2:anyregcls(s16) = HWTFPGA_MUX i16 1 ; set default value for %2
    %3:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1 :: (volatile load (s16) from %ir.rx, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_EXTRACT %3(s16), 0, 1 ; condition for mux
    %2:anyregcls(s16) = HWTFPGA_MUX %2(s16), %4(s1), %3(s16) ; conditionally update %2
    HWTFPGA_CSTORE %2(s16), %1, 0, 1:: (volatile store (s16) into %ir.txBody, addrspace 2)

    HWTFPGA_BR %bb.2

""")
    
    def test_mux_merge_twoWritingSameReg2(self):
        self._test_mir(f"""\
  bb.0.{self.getTestName()}:
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.bb1:

    %2:anyregcls(s16) = IMPLICIT_DEF ; %2 is register holding value between loop iterations
  
  bb.2.bb2:
  
    %2:anyregcls(s16) = HWTFPGA_MUX i16 1 ; set default value for %2
    %5:anyregcls(s16) = HWTFPGA_ADD %2(s16), i16 1
    HWTFPGA_CSTORE %5(s16), %1, 0, 1:: (volatile store (s16) into %ir.txBody, addrspace 2)
    %3:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 1 :: (volatile load (s16) from %ir.rx, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_EXTRACT %3(s16), 0, 1 ; condition for mux
    %2:anyregcls(s16) = HWTFPGA_MUX %2(s16), %4(s1), %3(s16) ; conditionally update %2
    HWTFPGA_CSTORE %2(s16), %1, 0, 1:: (volatile store (s16) into %ir.txBody, addrspace 2)

    HWTFPGA_BR %bb.2

""")
    def test_mux_trivial_const_propagation_onlyLocallyUsedReg0(self):
        self._test_mir(f"""\
  bb.0.{self.getTestName()}:
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %3:anyregcls(s8) = HWTFPGA_MUX i8 0
     
  bb.1.bb1:

    %2:anyregcls(s8) = HWTFPGA_MUX %3(s8)
    %4:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s8), i8 0
    HWTFPGA_BRCOND %4(s1), %bb.1

  bb.2.bb2:
  
    %3:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 1 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
    HWTFPGA_BR %bb.1

""")
        
        
        
    def test_mux_trivial_const_propagation_onlyLocallyUsedReg1(self):
        self._test_mir(f"""\
    bb.0.{self.getTestName()}:   
    
      %0:anyregcls = HWTFPGA_ARG_GET 0
      %1:anyregcls = HWTFPGA_ARG_GET 1
      %12:anyregcls = HWTFPGA_MUX i8 0
    
    bb.1.WhileSendSequence1.mainLoop:
    
      %2:anyregcls = HWTFPGA_MUX killed %12:anyregcls
      %4:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2:anyregcls, i8 0
      %13:anyregcls = HWTFPGA_MUX killed %2:anyregcls
      HWTFPGA_BRCOND killed %4:anyregcls(s1), %bb.3
    
    bb.2.WhileSendSequence1.whileSize:
    
      %5:anyregcls = HWTFPGA_MUX %13:anyregcls
      HWTFPGA_CSTORE %5:anyregcls, %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.dataOut, addrspace 2)
      %13:anyregcls = HWTFPGA_ADD killed %5:anyregcls, i8 -1
      %8:anyregcls = HWTFPGA_ICMP intpred(ne), %13:anyregcls, i8 0
      HWTFPGA_BRCOND killed %8:anyregcls, %bb.2
    
    bb.3.WhileSendSequence1.read:
    
      %12:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
      HWTFPGA_BR %bb.1
""")
      
if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HwtFpgaPreToNetlistGICombiner_TC('test_mux_merge0')])
    suite = testLoader.loadTestsFromTestCase(HwtFpgaPreToNetlistGICombiner_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
