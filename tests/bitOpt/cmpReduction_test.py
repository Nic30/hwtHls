from tests.baseSsaTest import BaseSsaTC
from tests.bitOpt.cmpReduction import RedundantCmpGT


class CmpReduction_TC(BaseSsaTC):
    __FILE__ = __file__
    TEST_THREADS_AND_SYNC = False

    def test_RedundantCmpGT_ll(self):
        self._test_ll(RedundantCmpGT)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([CmpReduction_TC('test_RedundantCmpGT_ll')])
    suite = testLoader.loadTestsFromTestCase(CmpReduction_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
