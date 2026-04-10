#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from operator import eq, ne, lt, gt, le, ge
from typing import Callable, Literal

from hwt.hdl.commonConstants import b1
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import to_signed
from tests.frontend.trivial import WriteOnce


class _TestICMP(HwModule):
    """
    Test Integer compare operator
    """

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.PRED:HOperatorDef = HwParam(HwtOps.EQ)
        self.DATA_WIDTH = HwParam(16)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        t = HBits(self.DATA_WIDTH)
        self.i = HwIOStructRdVld()
        self.i.T = HStruct(
                (t, "a"),
                (t, "b"),
            )
        self.o = HwIOSignal()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            i = hls.read(self.i).data
            hls.write(self.PRED._evalFn(i.a, i.b), self.o)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class Icmp_TC(SimTestCase):
    predicates = [
        (HwtOps.EQ, eq, False),
        (HwtOps.NE, ne, False),
        (HwtOps.ULE, le, False),
        (HwtOps.ULT, lt, False),
        (HwtOps.UGT, gt, False),
        (HwtOps.UGE, ge, False),
        (HwtOps.SLE, le, True),
        (HwtOps.SLT, lt, True),
        (HwtOps.SGT, gt, True),
        (HwtOps.SGE, ge, True),
    ]

    def _test_icmp(self,
                   isSigned: bool,
                    cmpPredicateOp: HOperatorDef,
                    cmpPredicatePy: Callable[[int, int], bool]
                   ):
        dut = _TestICMP()
        dut.PRED = cmpPredicateOp
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))

        DW = 4
        inputs = dut.i._ag.data
        resRef: list[Literal[0, 1]] = []
        for a in range(DW):
            if isSigned:
                _a = to_signed(a, DW)
            else:
                _a = a

            for b in range(DW):
                if isSigned:
                    _b = to_signed(b, DW)
                else:
                    _b = b

                inputs.append((a, b))  # append in unsigned format
                res = cmpPredicatePy(_a, _b)
                resRef.append(int(res))

        dut.i._ag.data.extend(inputs)
        self.runSim((len(resRef) + 1) * CLK_PERIOD)

        self.assertValSequenceEqual(dut.o._ag.data, resRef)

    def test_comb(self):
        for pred, predPy, isSigned in self.predicates:
            with self.subTest(pred.id):
                self._test_icmp(isSigned, pred, predPy)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = _TestICMP()
    m.CLK_FREQ = int(150e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_4_0_hwscheduleTrace}))
    print(to_rtl_str(m, target_platform=p))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AndShiftInLoop('test_AndShiftInLoop')])
    suite = testLoader.loadTestsFromTestCase(Icmp_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
