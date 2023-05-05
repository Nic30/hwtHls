from tests.baseSsaTest import BaseSsaTC
from tests.bitOpt.bitWidthReductionCmp import BitWidthReductionCmp2Values, \
    BitWidthReductionCmpReducibleEq, BitWidthReductionCmpReducibleNe, \
    BitWidthReductionCmpReducibleLt, BitWidthReductionCmpReducibleLe, \
    BitWidthReductionCmpReducibleGt, BitWidthReductionCmpReducibleGe


class BitWidthReductionCmp_example_TC(BaseSsaTC):
    __FILE__ = __file__

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


if __name__ == "__main__":
    import unittest
    
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([BitWidthReductionCmp_example_TC('test_BitWidthReductionCmpReducibleEq_ll')])
    suite = testLoader.loadTestsFromTestCase(BitWidthReductionCmp_example_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
