#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.frontend.pyBytecode.binToBcd import BinToBcd
from hwtHls.platform.xilinx.artix7 import Artix7Medium
from hwtLib.logic.bcdToBin_test import BcdToBinTC as HwtLibBinToBcdTC


class BinToBcd_TC(HwtLibBinToBcdTC):

    @classmethod
    def setUpClass(cls):
        cls.u = BinToBcd()
        cls.u.DATA_WIDTH = 8
        cls.compileSim(cls.u, target_platform=Artix7Medium())


if __name__ == "__main__":
    import unittest
    suite = unittest.TestSuite()
    # suite.addTest(IndexingTC('test_split'))
    suite.addTest(unittest.makeSuite(BinToBcd_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
