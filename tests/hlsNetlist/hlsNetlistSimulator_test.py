#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwt.hdl.commonConstants import b0, b1
from hwtHls.platform.debugBundle import HlsDebugBundle
from pyMathBitPrecise.bit_utils import get_bit
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC, \
    ListRaisingStopSimumulationWhenFilled
from tests.frontend.ifstm_test import HlsSimpleIfStatement
from tests.frontend.whileTrue import WhileTrueWriteCntr0
from tests.io.ioFsm import WriteFsm0WhileTrue123


class HlsNetlistSimulator_TC(BaseIrMirRtl_TC):

    def test_HlsSimpleIfStatement(self):
        # :note: simple combinational 1 clk circuit with 3 inputs, 1 output and 1 mux
        dut = HlsSimpleIfStatement()
        # test all combinations
        a = []
        b = []
        c = []
        d = []
        for i in range(1 << 3):
            _a = get_bit(i, 0)
            _b = get_bit(i, 1)
            _c = get_bit(i, 2)
            a.append(b1 if _a else b0)
            b.append(b1 if _b else b0)
            c.append(b1 if _c else b0)
            _d = dut.model(_a, _b, _c)
            d.append(_d)

        def prepareIrAndMirArgs():
            return (iter(a), iter(b), iter(c), [])

        def checkIrAndMirArgs(args):
            _, _, _, _d = args
            self.assertValSequenceEqual(_d, d)

        prepareHlsNetlistSimArgs = prepareIrAndMirArgs
        checkHlsNetlistSimResults = checkIrAndMirArgs

        def prepareRtlSimArgs(dut):
            dut.a._ag.data.extend(a)
            dut.b._ag.data.extend(b)
            dut.c._ag.data.extend(c)
            return d

        def checkRtlSimResults(dut, ref):
            self.assertValSequenceEqual(dut.d._ag.data, ref)

        self._test(dut,
            prepareIrAndMirArgs,
            checkIrAndMirArgs,
            prepareHlsNetlistSimArgs,
            checkHlsNetlistSimResults,
            prepareRtlSimArgs,
            checkRtlSimResults,
            # wallTimeIr,
            # wallTimeOptIr,
            # wallTimeOptMir,
            wallTimeRtlClks=(1 << 3) + 1,
            # runTestAfterPassFilter={"HlsNetlistPassSimplifySync", },
            runTestAfterEachHlsNetlistPass=True,
            debugFilter=HlsDebugBundle.ALL_RELIABLE,
        )

    def test_WhileTrueWriteCntr0(self):
        # :note: simple circuit with adder and backedge
        dut = WhileTrueWriteCntr0()
        N = 10
        ref = list(range(N))

        def prepareIrAndMirArgs():
            return (ListRaisingStopSimumulationWhenFilled([], N),)

        def checkIrAndMirArgs(args):
            res, = args
            self.assertValSequenceEqual(res, ref)

        prepareHlsNetlistSimArgs = prepareIrAndMirArgs
        checkHlsNetlistSimResults = checkIrAndMirArgs

        def prepareRtlSimArgs(dut):
            return ref

        def checkRtlSimResults(dut, ref):
            self.assertValSequenceEqual(dut.dataOut._ag.data, ref)

        self._test(dut,
            prepareIrAndMirArgs,
            checkIrAndMirArgs,
            prepareHlsNetlistSimArgs,
            checkHlsNetlistSimResults,
            prepareRtlSimArgs,
            checkRtlSimResults,
            wallTimeRtlClks=N + 1,
            # runTestAfterPassFilter={"HlsArchPassSyncLowering", },
            runTestAfterEachHlsNetlistPass=True,
            debugFilter=HlsDebugBundle.ALL_RELIABLE,
        )

    def test_WriteFsm0WhileTrue123(self):
        dut = WriteFsm0WhileTrue123()
        N = 10
        ref = list([(i % 3) + 1 for i in range(N)])

        def prepareIrAndMirArgs():
            return (ListRaisingStopSimumulationWhenFilled([], N),)

        def checkIrAndMirArgs(args):
            res, = args
            self.assertValSequenceEqual(res, ref)

        prepareHlsNetlistSimArgs = prepareIrAndMirArgs
        checkHlsNetlistSimResults = checkIrAndMirArgs

        def prepareRtlSimArgs(dut):
            return ref

        def checkRtlSimResults(dut, ref):
            self.assertValSequenceEqual(dut.o._ag.data, ref)

        self._test(dut,
            prepareIrAndMirArgs,
            checkIrAndMirArgs,
            prepareHlsNetlistSimArgs,
            checkHlsNetlistSimResults,
            prepareRtlSimArgs,
            checkRtlSimResults,
            wallTimeRtlClks=N + 1,
            # runTestAfterPassFilter={"HlsArchPassSyncLowering", },
            runTestAfterEachHlsNetlistPass=True,
            debugFilter=HlsDebugBundle.ALL_RELIABLE,
        )


if __name__ == '__main__':
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HlsNetlistSimulator_TC)
    # suite = unittest.TestSuite([HlsNetlistSimulator_TC("test_HlsSimpleIfStatement")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
