import unittest

from hwtHls.llvm.llvmIr import HFloatTmpConfig, APFloat
from pyMathBitPrecise.bit_utils import to_signed


class HFloatTmpConstToLlvm_TC(unittest.TestCase):

    def _makeHFloatTmpConfig(self,
            exponentWidth, mantissaWidth,
            isInQFromat, supportSubnormal=None, hasSign=True, hasIsNaN=False, hasIsInf=False, hasIs1=False, hasIs0=False
            ):
        if supportSubnormal is None:
            supportSubnormal = isInQFromat
        return HFloatTmpConfig(
            exponentWidth, mantissaWidth,
            isInQFromat, supportSubnormal, hasSign, hasIsNaN, hasIsInf, hasIs1, hasIs0)

    def testQ2_6(self):
        fpCfg: HFloatTmpConfig = self._makeHFloatTmpConfig(2, 6, True)

        def f(v):
            return int(fpCfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v)))

        self.assertEqual(int(fpCfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(1.0))), 1 << 6)
        self.assertEqual(int(fpCfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(-1.0))), to_signed(0b11 << 6, 8))
        self.assertEqual(int(fpCfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(0.5))), 1 << 5)
        self.assertEqual(int(fpCfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(0.25))), 1 << 4)
        self.assertEqual(int(fpCfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(0.75))), 0b11 << 4)


if __name__ == '__main__':
    unittest.main()

if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HFloatTmpConstToLlvm_TC('test_cmp_py')])
    suite = testLoader.loadTestsFromTestCase(HFloatTmpConstToLlvm_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
