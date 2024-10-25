#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.frontend.pyBytecode.pragmaInline import PragmaInline_writeCntr1
from hwt.simulator.simTestCase import SimTestCase
from tests.frontend.pyBytecode.hwrange_test import HlsPythonHwrange_TC


class CntrHolder():

    def __init__(self, hls: HlsScope):
        self.val = hls.var("cntr", uint8_t)


class VarReference_writeCntr0(PragmaInline_writeCntr1):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        cntr = CntrHolder(hls)
        cntr.val = 0
        limit = 4

        while b1:
            hls.write(cntr.val, self.o)
            if limit > 0:
                cntr.val += 1


class VarReference_writeCntr1(PragmaInline_writeCntr1):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        cntr = CntrHolder(hls)
        cntr.val = 0xff
        limit = 4

        while b1:
            if limit > 0:
                cntr.val += 1
            hls.write(cntr.val, self.o)


class VarReference_TC(SimTestCase):

    def test_VarReference_writeCntr0(self):
        HlsPythonHwrange_TC.test_HlsPythonHwrange_fromInt0(self, VarReference_writeCntr0, list(range(10)))

    def test_VarReference_writeCntr1(self):
        HlsPythonHwrange_TC.test_HlsPythonHwrange_fromInt0(self, VarReference_writeCntr1, list(range(0, 10)))


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = VarReference_writeCntr1()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([
    #    VarReference_TC('test_VarReference_writeCntr0'),
    # ])
    suite = testLoader.loadTestsFromTestCase(VarReference_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

