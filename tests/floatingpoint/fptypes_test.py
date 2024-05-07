from math import inf, nan, isnan
import struct
import unittest

from tests.floatingpoint.cmp_test import IEEE754FpCmp_TC
from tests.floatingpoint.fptypes import IEEE754Fp32, IEEE754Fp64


def fp64reinterpretToInt(a: float):
    return int.from_bytes(struct.pack("d", a), byteorder='little')


def int64reinterpretToFloat(n: float):
    return struct.unpack("d", n.to_bytes(8, byteorder='little'))[0]


class IEEE754Fp_TC(unittest.TestCase):

    def testFromPyAndBackInt(self):
        for intNumbers in IEEE754FpCmp_TC.TEST_DATA:
            for nInt in intNumbers:
                nFloatRef = struct.unpack("f", nInt.to_bytes(4, byteorder='little'))[0]

                nHdl = IEEE754Fp32.fromPyInt(nInt)
                nFloat = IEEE754Fp32.to_py(nHdl)
                self.assertEqual(nFloat, nFloatRef)

    def testFromPyAndBackFloat(self):
        for nFloatRef in [1.0, 2.0, 1.5, 1.125, 0.00001, 1e6, nan, inf, -inf, -10.0]:
            nHdl = IEEE754Fp64.from_py(nFloatRef)
            nFloat = IEEE754Fp64.to_py(nHdl)
            if isnan(nFloatRef):
                self.assertTrue(isnan(nFloat))
            else:
                self.assertEqual(nFloat, nFloatRef)


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754Fp_TC('testFromPyAndBackInt')])
    suite = testLoader.loadTestsFromTestCase(IEEE754Fp_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
