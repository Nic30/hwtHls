#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
import unittest

from hwt.hdl.types.bits import Bits
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axis import axis_send_bytes
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtSimApi.constants import CLK_PERIOD
from pyMathBitPrecise.bit_utils import  int_to_int_list, mask
from tests.io.amba.axiStream.axisParseLinear import AxiSParseStructManyInts0, \
    AxiSParseStructManyInts1, AxiSParse2fields, struct_i16_i32


class AxiSParseLinearTC(SimTestCase):

    def _test_parse(self, DATA_WIDTH:int, cls=AxiSParseStructManyInts0, N=3, T=structManyInts):
        u = cls()
        u.DATA_WIDTH = DATA_WIDTH
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())

        ref = []
        first = True
        for _ in range(N):
            d = {}
            fi = 0
            for f in T.fields:
                if f.name is not None:
                    _d = d[f.name] = self._rand.getrandbits(f.dtype.bit_length())
                    if first:
                        valArr = []
                        ref.append(valArr)
                    else:
                        valArr = ref[fi]
                    valArr.append(_d)
                    fi += 1

            v = T.from_py(d)
            w = v._dtype.bit_length()
            v = v._reinterpret_cast(Bits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            axis_send_bytes(u.i, data)
            first = False

        t = CLK_PERIOD * (len(u.i._ag.data) + 5)
        self.runSim(t)

        self.assertEqual(len(u.o), len(ref))
        for _ref, o in zip(ref, u.o):
            self.assertValSequenceEqual(o._ag.data, _ref, "%r [%s] != [%s]" % (
                o,
                ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in o._ag.data),
                ", ".join("0x%x" % i for i in _ref)
            ))

    def test_AxiSParseStructManyInts0_8b(self):
        self._test_parse(8)

    def test_AxiSParseStructManyInts0_16b(self):
        self._test_parse(16)

    def test_AxiSParseStructManyInts0_24b(self):
        self._test_parse(24)

    def test_AxiSParseStructManyInts0_48b(self):
        self._test_parse(48)

    def test_AxiSParseStructManyInts0_512b(self):
        self._test_parse(512)

    # dissabled because the exmple is too large
    #def test_AxiSParseStructManyInts1_8b(self):
    #    self._test_parse(8, cls=AxiSParseStructManyInts1)

    def test_AxiSParseStructManyInts1_16b(self):
        self._test_parse(16, cls=AxiSParseStructManyInts1)

    def test_AxiSParseStructManyInts1_24b(self):
        self._test_parse(24, cls=AxiSParseStructManyInts1)

    def test_AxiSParseStructManyInts1_48b(self):
        self._test_parse(48, cls=AxiSParseStructManyInts1)

    def test_AxiSParseStructManyInts1_512b(self):
        self._test_parse(512, cls=AxiSParseStructManyInts1)

    def test_AxiSParse2fields_8b(self):
        self._test_parse(8, cls=AxiSParse2fields, T=struct_i16_i32)

    def test_AxiSParse2fields_16b(self):
        self._test_parse(16, cls=AxiSParse2fields, T=struct_i16_i32)

    def test_AxiSParse2fields_24b(self):
        self._test_parse(24, cls=AxiSParse2fields, T=struct_i16_i32)

    def test_AxiSParse2fields_48b(self):
        self._test_parse(48, cls=AxiSParse2fields, T=struct_i16_i32)

    def test_AxiSParse2fields_512b(self):
        self._test_parse(512, cls=AxiSParse2fields, T=struct_i16_i32)


if __name__ == '__main__':

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AxiSParseLinearTC("test_AxiSParse2fields_24b")])
    suite = testLoader.loadTestsFromTestCase(AxiSParseLinearTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
