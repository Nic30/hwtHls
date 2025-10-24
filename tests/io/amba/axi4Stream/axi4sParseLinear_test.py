#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
from typing import Type
import unittest

from hwt.hdl.types.bits import HBits
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtSimApi.constants import CLK_PERIOD
from pyMathBitPrecise.bit_utils import int_to_int_list, mask
from tests.io.amba.axi4Stream.axi4sParseLinear import Axi4SParseStructManyInts0, \
    Axi4SParseStructManyInts1, Axi4SParse2fields, struct_i16_i32
# from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS


class Axi4SParseLinearTC(SimTestCase):

    def _test_parse(self, DATA_WIDTH:int, cls=Axi4SParseStructManyInts0, N=3, T=structManyInts):
        dut = cls()
        dut.DATA_WIDTH = DATA_WIDTH
        self._run_test_parse(dut, Axi4StreamSimFrameUtils, N, T)

    def _run_test_parse(self, dut: Axi4SParseStructManyInts0, frameUtilsCls: Type[Axi4StreamSimFrameUtils], N=3, T=structManyInts):
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED]
            ))

        ref = []
        first = True
        fu: Axi4StreamSimFrameUtils = frameUtilsCls.from_HwIO(dut.i)
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
            v = v._reinterpret_cast(HBits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            fu.send_bytes(data, dut.i._ag.data)
            first = False

        t = CLK_PERIOD * (len(dut.i._ag.data) + 5)
        self.runSim(t)

        self.assertEqual(len(dut.o), len(ref))
        for _ref, o in zip(ref, dut.o):
            self.assertValSequenceEqual(o._ag.data, _ref, "%r [%s] != [%s]" % (
                o,
                ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in o._ag.data),
                ", ".join("0x%x" % i for i in _ref)
            ))
    
    
    # dissabled because the exmple is too large for circleci
    # def test_Axi4SParseStructManyInts0_8b(self):
    #     self._test_parse(8)

    def test_Axi4SParseStructManyInts0_16b(self):
        self._test_parse(16)

    def test_Axi4SParseStructManyInts0_24b(self):
        self._test_parse(24)

    def test_Axi4SParseStructManyInts0_48b(self):
        self._test_parse(48)

    def test_Axi4SParseStructManyInts0_512b(self):
        self._test_parse(512)

    # dissabled because the exmple is too large
    # def test_Axi4SParseStructManyInts1_8b(self):
    #    self._test_parse(8, cls=Axi4SParseStructManyInts1)

    def test_Axi4SParseStructManyInts1_16b(self):
        self._test_parse(16, cls=Axi4SParseStructManyInts1)

    def test_Axi4SParseStructManyInts1_24b(self):
        self._test_parse(24, cls=Axi4SParseStructManyInts1)

    def test_Axi4SParseStructManyInts1_48b(self):
        self._test_parse(48, cls=Axi4SParseStructManyInts1)

    def test_Axi4SParseStructManyInts1_512b(self):
        self._test_parse(512, cls=Axi4SParseStructManyInts1)

    def test_Axi4SParse2fields_8b(self):
        self._test_parse(8, cls=Axi4SParse2fields, T=struct_i16_i32)

    def test_Axi4SParse2fields_16b(self):
        self._test_parse(16, cls=Axi4SParse2fields, T=struct_i16_i32)

    def test_Axi4SParse2fields_24b(self):
        self._test_parse(24, cls=Axi4SParse2fields, T=struct_i16_i32)

    def test_Axi4SParse2fields_48b(self):
        self._test_parse(48, cls=Axi4SParse2fields, T=struct_i16_i32)

    def test_Axi4SParse2fields_64b(self):
        self._test_parse(64, cls=Axi4SParse2fields, T=struct_i16_i32)

    def test_Axi4SParse2fields_512b(self):
        self._test_parse(512, cls=Axi4SParse2fields, T=struct_i16_i32)


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SParseLinearTC("test_Axi4SParseStructManyInts1_512b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SParseLinearTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
