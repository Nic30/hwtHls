from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmMir.baseLlvmMirTC import BaseLlvmMirTC


class HwtFpgaPreToNetlistGICombiner_TC(BaseLlvmMirTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        llvm._testHwtFpgaPreToNetlistCombiner()

    def test_mux_merge0(self):
        self._test_mir_file()

    def test_mux_merge_twoWritingSameReg(self):
        self._test_mir_file()

if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HwtFpgaPreToNetlistGICombiner_TC('test_mux_merge0')])
    suite = testLoader.loadTestsFromTestCase(HwtFpgaPreToNetlistGICombiner_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
