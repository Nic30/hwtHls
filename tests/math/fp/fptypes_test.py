from math import inf, nan, isnan
import struct
import unittest

from hwt.code import Concat
from hwt.hdl.types.structValBase import HStructConstBase
from pyMathBitPrecise.bits3t import Bits3val
from hwtHls.llvm.llvmIr import HFloatTmpConfig, APFloat, APInt
from tests.math.fp.fpcmp_test import IEEE754FpCmp_TC
from tests.math.fp.fptypes import IEEE754Fp32, IEEE754Fp64, IEEE754Fp, \
    IEEE754Fp16
from pyMathBitPrecise.bit_utils import to_unsigned


def fpTupleToFpConst(d: tuple[Bits3val, Bits3val, Bits3val], fpType: IEEE754Fp):
    """
    :param d: input data in format (mantissa, exponent, sign)
    """
    dAsInt = Concat(*reversed(d))
    return fpType.fromPyInt(dAsInt.val, dAsInt.vld_mask)


def fpConstToFpTuple(d: HStructConstBase):
    return (int(d.sign), int(d.exponent), int(d.mantissa))


def fpPyDictToFpTuple(d: dict[str, Bits3val]):
    return (d['sign'], d['exponent'], d['mantissa'])


class IEEE754Fp_TC(unittest.TestCase):

    def testFromPyAndBackInt(self):
        for intNumbers in IEEE754FpCmp_TC.TEST_DATA:
            for nInt in intNumbers:
                nFloatRef = struct.unpack("f", nInt.to_bytes(4, byteorder='little'))[0]

                nHdl = IEEE754Fp32.fromPyInt(nInt)
                nFloat = nHdl.to_py()
                self.assertEqual(nFloat, nFloatRef)

    def testFromPyAndBackFloat_fp64(self, t=IEEE754Fp64, DATA=[0.0, 1.0, 2.0, 1.5, 1.125, 0.00001, 1e6, nan, inf, -inf, -10.0]):
        cfg: HFloatTmpConfig = t._cfg
        w = t.bit_length()
        for nFloatRef in DATA:
            nHdl = t.from_py(nFloatRef)
            nFloat = nHdl.to_py()
            if isnan(nFloatRef):
                self.assertTrue(isnan(nFloat))
            else:
                self.assertEqual(nFloat, nFloatRef)

            vApInt: APInt = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(nFloatRef))
            self.assertEqual(vApInt.getBitWidth(), w)
            vApFloat = cfg.bitCastHFloatTmpAPIntToAPFloat(vApInt)
            vAsFloat = float(vApFloat)
            if isnan(nFloatRef):
                self.assertTrue(isnan(vAsFloat))
            else:
                self.assertEqual(vAsFloat, nFloatRef)

    def testFromPyAndBackFloat_fp16(self):
        self.testFromPyAndBackFloat_fp64(IEEE754Fp16, [0.0, 1.0, 2.0, 1.5, 1.125, nan, inf, -inf, -10.0])


if __name__ == "__main__":
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754Fp_TC('testFromPyAndBackInt')])
    suite = testLoader.loadTestsFromTestCase(IEEE754Fp_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
