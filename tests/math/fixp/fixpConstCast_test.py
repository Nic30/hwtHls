#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from tests.math.fixp.fixpTypes import HFixedPointQ
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst


class HFixedPointQ_HConst_TC(unittest.TestCase):

    def test_q2_2(self):
        fpT = HFixedPointQ(2, 2)
        bitVecT = HBits(fpT.bit_length())

        def floatToBits(v: float):
            return fpT.from_py(v)._reinterpret_cast(bitVecT)

        def bitsToFloat(v: HBitsConst):
            return float(v._reinterpret_cast(fpT))

        self.assertEqual(bitsToFloat(bitVecT.from_py(0b0111)), 1.75)
        self.assertEqual(bitsToFloat(bitVecT.from_py(0b1001)), -1.75)

    def test_q2_6(self, fpT=HFixedPointQ(2, 6)):
        bitVecT = HBits(fpT.bit_length())

        def floatToBits(v: float):
            return fpT.from_py(v)._reinterpret_cast(bitVecT)

        def bitsToFloat(v: HBitsConst):
            return float(v._reinterpret_cast(fpT))

        for n in (0.0, 0.1, 0.25, 0.3, 0.5, 1.0,):
            _n = floatToBits(n)
            self.assertAlmostEqual(bitsToFloat(_n), n, delta=0.01)

            _n = floatToBits(-n)
            # print(-n, _n, bitsToFloat(_n))
            self.assertAlmostEqual(bitsToFloat(_n), -n, delta=0.01)

    def test_q4_8(self):
        self.test_q2_6(fpT=HFixedPointQ(4, 8))


if __name__ == '__main__':
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HFixedPointQ_HConst_TC('test_q2_6')])
    suite = testLoader.loadTestsFromTestCase(HFixedPointQ_HConst_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
