#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from operator import lt
from typing import Callable

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIOs.std import HwIODataVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.trivial import WriteOnce
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hdl.types.struct import HStruct


class TestHwModuleCmpConcatWithConstInMiddle(HwModule):

    @override
    def hwConfig(self) -> None:
        self.P = HwParam(lt)

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.dataIn = HwIOStructRdVld()
        t = HBits(2)
        self.dataIn.T = HStruct(
            (t, "op0h"),
            (t, "op0l"),
            (t, "op1h"),
            (t, "op1l"),
        )
        # :note: separated channels so it is more easy to read in LLVM IR
        outputCnt = (2 ** 2) * (2 ** 2)
        self.dataOut = HwIODataVld()._m()
        self.dataOut.DATA_WIDTH = outputCnt

    @hwt_expr_producer
    def applyPredicate(self, op0h: HBitsConst, op0l: HBitsConst, op1h: HBitsConst, op1l: HBitsConst,):
        results = []
        p = self.P

        middleTy = HBits(2)

        # try all combinations of prefix and suffix values for given lenghts
        # :note: max(1, ...) because the lenght may be 0 but we still want to test it
        #   so at least 1 iteration is required
        for op0CVal in range(int(2 ** 2)):
            c0 = middleTy.from_py(op0CVal)
            for op1CVal in range(int(2 ** 2)):
                c1 = middleTy.from_py(op1CVal)
                op0 = Concat(op0h, c0, op0l)
                op1 = Concat(op1h, c1, op1l)
                results.append(p(op0, op1))

        return tuple(results)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            v = hls.read(self.dataIn).data
            results = self.applyPredicate(v.op0h, v.op0l, v.op1h, v.op1l)
            hls.write(Concat(*reversed(results)), self.dataOut, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class CmpConcatWithConstInMiddle_TC(SimTestCase):

    def _test(self, predicate: Callable[[int, int], bool]):
        dut = TestHwModuleCmpConcatWithConstInMiddle()
        dut.P = predicate

        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        dataIn: list[tuple[int, int, int, int]] = []
        for op0l in range(int(2 ** 2)):
            for op0h in range(int(2 ** 2)):
                for op1l in range(int(2 ** 2)):
                    for op1h in range(int(2 ** 2)):
                        d = (op0h, op0l, op1h, op1l)
                        dataIn.append(d)

        dut.dataIn._ag.data.extend(dataIn)
        self.runSim((len(dut.dataIn._ag.data) + 2) * CLK_PERIOD)
        inTy = HBits(2)
        ref = [dut.applyPredicate(inTy.from_py(op0h),
                                  inTy.from_py(op0l),
                                  inTy.from_py(op1h),
                                  inTy.from_py(op1l))
               for op0h, op0l, op1h, op1l in dataIn]
        dout = dut.dataOut._ag.data
        self.assertEqual(len(dout), len(ref))

        for inp, o, oRef in zip(dataIn, dout, ref):
            _o = tuple(int(obit) for obit in o)
            _oRef = tuple(int(_or) for _or in oRef)
            if _o != _oRef:
                ctx = RtlNetlist(None)
                op0h = ctx.sig("op0h", inTy)
                op0l = ctx.sig("op0l", inTy)
                op1h = ctx.sig("op1h", inTy)
                op1l = ctx.sig("op1l", inTy)
                oWithOriginalExprs = dut.applyPredicate(op0h, op0l, op1h, op1l)
                for oBit, oRefBit, expr in zip(_o, _oRef, reversed(oWithOriginalExprs)):
                    self.assertEqual(oBit, oRefBit, msg=(expr, "inp=", inp))  # "prefixLens:", prefixLens, "suffixLens:", suffixLens,
            self.assertSequenceEqual(_o, _oRef)

    def test_eq(self):
        self._test(HwtOps.EQ._evalFn)

    def test_ne(self):
        self._test(HwtOps.NE._evalFn)

    def test_ult(self):
        self._test(HwtOps.ULT._evalFn)

    def test_ule(self):
        self._test(HwtOps.ULE._evalFn)

    def test_ugt(self):
        self._test(HwtOps.UGT._evalFn)

    def test_uge(self):
        self._test(HwtOps.UGE._evalFn)

    def test_slt(self):
        self._test(HwtOps.SLT._evalFn)

    def test_sle(self):
        self._test(HwtOps.SLE._evalFn)

    def test_sgt(self):
        self._test(HwtOps.SGT._evalFn)

    def test_sge(self):
        self._test(HwtOps.SGE._evalFn)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = TestHwModuleCmpConcatWithConstInMiddle()
    m.P = HwtOps.ULT._evalFn
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([CmpConcatWithConstInMiddle_TC('test_ult')])
    suite = testLoader.loadTestsFromTestCase(CmpConcatWithConstInMiddle_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
