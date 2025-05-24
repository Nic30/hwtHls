#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tests.math.fp.fpadd_test import IEEE754FpAdder_TC, _Test_IEEE754FpAlu
from tests.math.fp.fpmul import IEEE754FpMul


class IEEE754FpMultipier_TC(IEEE754FpAdder_TC):
    FP_FUNCTION = staticmethod(IEEE754FpMul)
    FP_OPERATOR_FN = staticmethod(lambda a, b: a * b)
    FP_FUNCTION_ADD_IS_SIM_ARG = False

    @staticmethod
    def model(a: float, b: float):
        return a * b


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from tests.math.fp.fptypes import IEEE754Fp16
    # from hwtHls.platform.xilinx.artix7 import Artix7Fast

    m = _Test_IEEE754FpAlu()
    m.FP_FUNCTION = IEEE754FpMul
    m.CLK_FREQ = int(100e3)
    m.T = IEEE754Fp16

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpMultipier_TC('test_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpMultipier_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
