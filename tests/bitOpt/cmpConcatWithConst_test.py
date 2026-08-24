#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from operator import lt
import os
from typing import Callable

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b1
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIOs.std import HwIODataRdVld, HwIODataVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.testUtils import TestMatrix
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.rtlLevel.netlist import RtlNetlist
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.constants import CLK_PERIOD
from tests.frontend.trivial import WriteOnce


class TestHwModuleCmpConcatWithConst(HwModule):

    @override
    def hwConfig(self) -> None:
        self.P = HwParam(lt)
        self.PREFIX_LENS = HwParam((0, 1, 2))
        self.SUFFIX_LENS = HwParam((0, 1, 2))

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.dataIn = HwIODataRdVld()
        self.dataIn.DATA_WIDTH = 2
        # :note: separated channels so it is more easy to read in LLVM IR
        outputCnt = len(self.applyPredicate(HBits(2).from_py(0)))
        self.dataOut = HwIODataVld()._m()
        self.dataOut.DATA_WIDTH = outputCnt
        # self.dataOut = HwIOArray(
        #    HwIODataVld()._m() for _ in range(outputCnt)
        # )
        # for i in self.dataOut:
        #    i.DATA_WIDTH = 1

    @hwt_expr_producer
    def applyPredicate(self, v: HBitsConst):
        results = []
        p = self.P

        # r = Concat(v, b1) < 5
        # results.append(r)
        # r = HBits(3).from_py(2) < Concat(v, b0)
        # results.append(r)
        # return results
        # t = HBits(3)
        # results = [
        # #Concat(v, b0) < 0           ,
        # #t.from_py(0) < Concat(v, b0),
        # #Concat(v, b0) < 1           ,
        # #t.from_py(1) < Concat(v, b0),
        # #Concat(v, b0) < 2           ,
        # #t.from_py(2) < Concat(v, b0),
        # Concat(v, b0) < 3           ,
        # #t.from_py(3) < Concat(v, b0),
        # #Concat(v, b0) < 4           ,
        # #t.from_py(4) < Concat(v, b0),
        # #Concat(v, b0) < 5           ,
        # #t.from_py(5) < Concat(v, b0),
        # #Concat(v, b0) < 6           ,
        # #t.from_py(6) < Concat(v, b0),
        # #Concat(v, b0) < 7           ,
        # #t.from_py(7) < Concat(v, b0),
        # #Concat(v, b1) < 0           ,
        # #t.from_py(0) < Concat(v, b1),
        # #Concat(v, b1) < 1           ,
        # #t.from_py(1) < Concat(v, b1),
        # #Concat(v, b1) < 2           ,
        # #t.from_py(2) < Concat(v, b1),
        # #Concat(v, b1) < 3           ,
        # #t.from_py(3) < Concat(v, b1),
        # #Concat(v, b1) < 4           ,
        # #t.from_py(4) < Concat(v, b1),
        # #Concat(v, b1) < 5           ,
        # #t.from_py(5) < Concat(v, b1),
        # #Concat(v, b1) < 6           ,
        # #t.from_py(6) < Concat(v, b1),
        # #Concat(v, b1) < 7           ,
        # #t.from_py(7) < Concat(v, b1),
        # ]
        # return results

        # try all combinations of prefix and suffix lengths
        for prefixLen in self.PREFIX_LENS:
            if prefixLen > 0:
                prefixTy = HBits(prefixLen)
            else:
                prefixTy = None
            for suffixLen in self.SUFFIX_LENS:
                if suffixLen > 0:
                    suffixTy = HBits(suffixLen)
                else:
                    suffixTy = None

                operandWidth = v._dtype.bit_length() + prefixLen + suffixLen
                opTy = HBits(operandWidth)

                # try all combinations of prefix and suffix values for given lenghts
                # :note: max(1, ...) because the lenght may be 0 but we still want to test it
                #   so at least 1 iteration is required
                for prefixVal in range(max(1, int(2 ** prefixLen))):
                    if prefixTy is not None:
                        pVal = prefixTy.from_py(prefixVal)
                    for suffixVal in range(max(1, int(2 ** suffixLen))):
                        if suffixTy is not None:
                            sVal = suffixTy.from_py(suffixVal)
                        for otherOpVal in range(int(2 ** operandWidth)):
                            if prefixLen > 0 and suffixLen > 0:
                                op0 = Concat(pVal, v, sVal)
                            elif prefixLen > 0:
                                op0 = Concat(pVal, v)
                            elif suffixLen > 0:
                                op0 = Concat(v, sVal)
                            else:
                                op0 = v

                            op1 = opTy.from_py(otherOpVal)
                            results.append(p(op0, op1))
                            results.append(p(op1, op0))

        return tuple(results)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            v = hls.read(self.dataIn).data
            results = self.applyPredicate(v)
            hls.write(Concat(*reversed(results)), self.dataOut, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


testMatrix = TestMatrix([(0,), (1,), (2,)],
                        [(0,), (1,), (2,)])


class CmpConcatWithConst_TC(SimTestCase):
    """
    :note: this testcase tests all possible combinations of constant and non constant bits
        there are many combinations and thus this test takes long
    """

    def _test(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...], predicate: Callable[[int, int], bool]):
        dut = TestHwModuleCmpConcatWithConst()
        dut.P = predicate
        dut.PREFIX_LENS = prefixLens
        dut.SUFFIX_LENS = suffixLens

        if self.DEFAULT_BUILD_DIR is not None:
            # because otherwise files gets mixed in parallel test execution
            test_name = self.getTestName()
            u_name = dut._getDefaultName()
            unique_name = f"{test_name:s}_{u_name:s}_p{'_'.join(str(d) for d in prefixLens):d}_s{'_'.join(str(d) for d in suffixLens):d}"
            build_dir = os.path.join(self.DEFAULT_BUILD_DIR,
                                     self.getTestName() + unique_name)
        else:
            unique_name = None
            build_dir = None

        self.compileSimAndStart(dut, build_dir=build_dir, unique_name=unique_name, target_platform=VirtualHlsPlatform())
        dut.dataIn._ag.data.extend(i for i in range(int(2 ** 2)))
        self.runSim((len(dut.dataIn._ag.data) + 2) * CLK_PERIOD)
        inTy = HBits(2)
        ref = [dut.applyPredicate(inTy.from_py(v)) for v in range(int(2 ** 2))]
        dout = dut.dataOut._ag.data
        self.assertEqual(len(dout), len(ref))

        for inp, (o, oRef) in enumerate(zip(dout, ref)):
            _o = tuple(int(obit) for obit in o)
            _oRef = tuple(int(_or) for _or in oRef)
            if _o != _oRef:
                ctx = RtlNetlist(None)
                v = ctx.sig("v", inTy)
                oWithOriginalExprs = dut.applyPredicate(v)
                for oBit, oRefBit, expr in zip(_o, _oRef, reversed(oWithOriginalExprs)):
                    self.assertEqual(oBit, oRefBit, msg=(expr, "v=", inp))  # "prefixLens:", prefixLens, "suffixLens:", suffixLens,
            self.assertSequenceEqual(_o, _oRef)

    @testMatrix
    def test_eq(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.EQ._evalFn)

    @testMatrix
    def test_ne(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.NE._evalFn)

    @testMatrix
    def test_ult(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.ULT._evalFn)

    @testMatrix
    def test_ule(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.ULE._evalFn)

    @testMatrix
    def test_ugt(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.UGT._evalFn)

    @testMatrix
    def test_uge(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.UGE._evalFn)

    @testMatrix
    def test_slt(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.SLT._evalFn)

    @testMatrix
    def test_sle(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.SLE._evalFn)

    @testMatrix
    def test_sgt(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.SGT._evalFn)

    @testMatrix
    def test_sge(self, prefixLens: tuple[int, ...], suffixLens: tuple[int, ...]):
        self._test(prefixLens, suffixLens, HwtOps.SGE._evalFn)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    import sys
    sys.setrecursionlimit(int(1e6)) # :note: this does not affect Py_C_RECURSION_LIMIT used in exec()
    #m = TestHwModuleCmpConcatWithConst()
    #m.P = HwtOps.SGE._evalFn
    #print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE),
    #                 serializer_cls=SimModelSerializer))

    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(CmpConcatWithConst_TC)
    # suite = unittest.TestSuite([CmpConcatWithConst_TC('test_sle_2_2')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
