from tests.baseSsaTest import BaseSsaTC
from tests.pythonFrontend.fnClosure import FnClosureSingleItem, FnClosureNone0, \
    FnClosureNone1


class FnClosure_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_FnClosureSingleItem_ll(self):
        self._test_ll(FnClosureSingleItem)
        
    def test_FnClosureNone0_ll(self):
        self._test_ll(FnClosureNone0)
        
    def test_FnClosureNone1_ll(self):
        self._test_ll(FnClosureNone1)


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(FnClosure_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(FnClosure_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
