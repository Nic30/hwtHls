#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.baseSsaTest import BaseSsaTC
from tests.pythonFrontend.pyArrHwIndex import Rom, CntrArray


class PyArrHwIndex_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_Rom_ll(self):
        self._test_ll(Rom)
        
    def test_CntrArray_ll(self):
        self._test_ll(CntrArray)


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(PyArrHwIndex_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(PyArrHwIndex_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
