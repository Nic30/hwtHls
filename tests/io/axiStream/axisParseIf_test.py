#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
import unittest

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.struct import HStruct
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axis import axis_send_bytes
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import  int_to_int_list, mask
from tests.io.axiStream.axisParseIf import AxiSParse2If


class AxiSParseIfTC(SimTestCase):

    def _test_AxiSParse2If(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        u = AxiSParse2If()
        u.DATA_WIDTH = DATA_WIDTH
        u.CLK_FREQ = freq
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        T1 = HStruct(
            (Bits(16), "v0"),
            (Bits(8), "v1"),
        )
        T2 = HStruct(
            (Bits(16), "v0"),
            (Bits(16), "v1"),
        )
        T4 = HStruct(
            (Bits(16), "v0"),
            (Bits(32), "v1"),
        )
        
        ref = []
        ALL_Ts = [T1, T2, T4]
        for _ in range(N):
            T = self._rand.choice(ALL_Ts)
            v1_t = T.field_by_name["v1"].dtype
            v1 = self._rand.getrandbits(v1_t.bit_length())
            d = {
                "v0": v1_t.bit_length() // 8,
                "v1": v1
            }
            if v1_t.bit_length() in (16, 32):
                ref.append(v1)

            v = T.from_py(d)
            w = v._dtype.bit_length()
            v = v._reinterpret_cast(Bits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            axis_send_bytes(u.i, data)

        t = int(freq_to_period(freq)) * (len(u.i._ag.data) + 10) * 2
        self.runSim(t)

        self.assertValSequenceEqual(u.o._ag.data, ref, "%r [%s] != [%s]" % (
            u.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in u.o._ag.data),
            ", ".join("0x%x" % i for i in ref)
        ))

    def test_AxiSParse2If_8b_1MHz(self):
        self._test_AxiSParse2If(8)

    def test_AxiSParse2If_16b_1MHz(self):
        self._test_AxiSParse2If(16)

    def test_AxiSParse2If_24b_1MHz(self):
        self._test_AxiSParse2If(24)

    def test_AxiSParse2If_48b_1MHz(self):
        self._test_AxiSParse2If(48)

    def test_AxiSParse2If_512b_1MHz(self):
        self._test_AxiSParse2If(512)

    def test_AxiSParse2If_8b_40MHz(self):
        self._test_AxiSParse2If(8, freq=int(40e6))

    def test_AxiSParse2If_16b_40MHz(self):
        self._test_AxiSParse2If(16, freq=int(40e6))

    def test_AxiSParse2If_24b_40MHz(self):
        self._test_AxiSParse2If(24, freq=int(40e6))

    def test_AxiSParse2If_48b_40MHz(self):
        self._test_AxiSParse2If(48, freq=int(40e6))

    def test_AxiSParse2If_512b_40MHz(self):
        self._test_AxiSParse2If(512, freq=int(40e6))

    def test_AxiSParse2If_8b_100MHz(self):
        self._test_AxiSParse2If(8, freq=int(100e6))

    def test_AxiSParse2If_16b_100MHz(self):
        self._test_AxiSParse2If(16, freq=int(100e6))

    def test_AxiSParse2If_24b_100MHz(self):
        self._test_AxiSParse2If(24, freq=int(100e6))

    def test_AxiSParse2If_48b_100MHz(self):
        self._test_AxiSParse2If(48, freq=int(100e6))

    def test_AxiSParse2If_512b_100MHz(self):
        self._test_AxiSParse2If(512, freq=int(100e6))


if __name__ == '__main__':
    # from hwt.synthesizer.utils import to_rtl_str
    # u = AxiSParse2If()
    # u.DATA_WIDTH = 16
    # u.CLK_FREQ = int(40e6)
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
    suite = unittest.TestSuite()
    #suite.addTest(AxiSParseIfTC('test_AxiSParse2If_16b_40MHz'))
    suite.addTest(unittest.makeSuite(AxiSParseIfTC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
