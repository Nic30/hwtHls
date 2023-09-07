#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Type, List

from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.ast.trivial_test import HlsAstTrivial_TC
from tests.io.ioFsm2 import WriteFsmFor, WriteFsmPrequel, WriteFsmIf, \
    WriteFsmIfOptionalInMiddle, WriteFsmControlledFromIn


class IoFsm2_TC(SimTestCase):

    def _test_no_comb_loops(self):
        HlsAstTrivial_TC._test_no_comb_loops(self)

    def _test_Write(self, cls: Type[Unit], ref: List[Optional[int]], CLK):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)

    def test_WriteFsmFor(self, cls=WriteFsmFor, ref=[1, 2, 3,
                                                     1, 2, 3,
                                                     1, 2, 3, ], CLK=18):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsmPrequel(self, cls=WriteFsmPrequel,
                              ref=[99, 100, 1, 2, 3,
                                   1 + 1, 1 + 2, 1 + 3,
                                   2 + 1, 2 + 2, 2 + 3, ], CLK=26):
        self._test_Write(cls, ref, CLK)

    def test_WriteFsmIf(self, cls=WriteFsmIf, CLK=24):

        def model():
            i = 0
            while True:
                if i == 0:
                    yield 1
                    yield 2
                    i = 1
                else:
                    yield 3
                    i = 0

        m = model()
        ref = [next(m) for _ in range(CLK)]
        self._test_Write(cls, ref, CLK + 9)

    def test_WriteFsmIfOptionalInMiddle(self, cls=WriteFsmIfOptionalInMiddle, CLK=12):

        def model():
            i = 0
            while True:
                yield 1
                if i == 0:
                    yield 2
                    i = 1
                else:
                    i = 0
                yield 3

        m = model()
        ref = [next(m) for _ in range(CLK)]
        self._test_Write(cls, ref, CLK + 3)

    def _test_ReadWrite(self, cls: Type[Unit], dinRef: List[Optional[int]], ref: List[Optional[int]], CLK: int):
        u = cls()
        self.compileSimAndStart(u, target_platform=VirtualHlsPlatform())
        u.i._ag.data.extend(dinRef)
        self.runSim(CLK * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(u.o._ag.data, ref)

    def test_WriteFsmControlledFromIn(self, cls=WriteFsmControlledFromIn, CLK=16):

        def model(din):
            while True:
                yield 1
                r = next(din)
                if r == 1:
                    yield 2
                else:
                    yield 4
                    yield 5
                yield 3

        dinRef = [self._rand.choice((1, 2)) for _ in range(CLK)]
        m = model(iter(dinRef))
        ref = [next(m) for _ in range(CLK)]
        self._test_ReadWrite(cls, dinRef, ref, CLK + 4)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = WriteFsmPrequel()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([IoFsm2_TC("test_WriteFsmPrequel")])
    # suite = testLoader.loadTestsFromTestCase(IoFsm2_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
