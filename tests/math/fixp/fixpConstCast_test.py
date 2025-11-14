#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from tests.math.fixp.fixpTypes import HFixedPointQ
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from tests.math.fixp.fixpResize import fixp_resize_py


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

        for n in (0.0, 0.1, 0.25, 0.3, 0.5, 1.0):
            _n = floatToBits(n)
            self.assertAlmostEqual(bitsToFloat(_n), n, delta=0.01)

            _n = floatToBits(-n)
            # print(-n, _n, bitsToFloat(_n))
            self.assertAlmostEqual(bitsToFloat(_n), -n, delta=0.01)

    def test_q4_8(self):
        self.test_q2_6(fpT=HFixedPointQ(4, 8))

    def _test_q8_0(self, rounding, refValues):
        fpT0 = HFixedPointQ(8, 1, rounding=rounding)
        fpT1 = HFixedPointQ(8, 0, rounding=rounding)
        # bitsT = HBits(9)

        def cast(v: float):
            return float(fpT0.from_py(v)._auto_cast(fpT1))

        testIn = [11.5, 12.5, -11.5, -12.5]
        for n, ref in zip(testIn, refValues):
            _n = cast(n)
            self.assertAlmostEqual(float(_n), ref, delta=0.01)
            _n = fixp_resize_py(n, signed=True, inIntWidth=8, inFracWidth=1, outIntWidth=8, outFracWidth=0,
                                roundingMode=rounding, saturationMode=HFloatTmpSaturation.SATURATE_NONE)
            self.assertAlmostEqual(_n, ref, delta=0.01)
            
    def test_q8_0_ROUND_HALF_EVEN(self):
        self._test_q8_0(HFloatTmpRounding.ROUND_HALF_EVEN, [12.0, 12.0, -12.0, -12.0, ])

    def test_q8_0_ROUND_HALF_UP(self):
        self._test_q8_0(HFloatTmpRounding.ROUND_HALF_UP  , [12.0, 13.0, -12.0, -13.0, ])

    def test_q8_0_ROUND_DOWN(self):
        self._test_q8_0(HFloatTmpRounding.ROUND_DOWN     , [11.0, 12.0, -11.0, -12.0, ])

    def test_q8_0_ROUND_CEILING(self):
        self._test_q8_0(HFloatTmpRounding.ROUND_CEILING  , [12.0, 13.0, -11.0, -12.0, ])

    def test_q8_0_ROUND_FLOOR(self):
        self._test_q8_0(HFloatTmpRounding.ROUND_FLOOR    , [11.0, 12.0, -12.0, -13.0, ])


if __name__ == '__main__':
    import sys
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HFixedPointQ_HConst_TC('test_q8_0_ROUND_CEILING')])
    suite = testLoader.loadTestsFromTestCase(HFixedPointQ_HConst_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())
