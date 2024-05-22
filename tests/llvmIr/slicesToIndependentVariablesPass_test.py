#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from io import StringIO
import os

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal, HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm
from tests.baseSsaTest import TestFinishedSuccessfuly
from tests.bitOpt.countBits import CountLeadingZeros
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC


class SliceBreakSlicedVar0(HwModule):

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = int(1e6)
        self.o = HwIOVectSignal(32)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = HBits(32).from_py(0)
        x[0] = 1
        x[1] = 1
        hls.write(x, self.o)

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class SliceBreakSlicedVar1(SliceBreakSlicedVar0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = HBits(32).from_py(0)
        x[1] = 1
        x[0] = 1
        hls.write(x, self.o)


class SliceBreakSlicedVar2(SliceBreakSlicedVar0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = HBits(32).from_py(0)
        x[5] = 1
        hls.write(x, self.o)


class SliceBreak0(SliceBreakSlicedVar0):

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = int(1e6)
        self.i = HwIOVectSignal(32)
        self.o = HwIOVectSignal(32)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = hls.read(self.i).data
        x = Concat(i[:16], i[16:])
        hls.write(x, self.o)


class SliceBreak1(SliceBreak0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = hls.read(self.i).data
        x = Concat(i[:16], i[16:])

        hls.write(x + 1, self.o)


class SliceBreak2(SliceBreak0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = hls.read(self.i).data
        x = Concat(i[:16], i[16:])

        hls.write(~(x + 1), self.o)


class SliceBreak3(SliceBreak0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = hls.read(self.i).data
        x0 = Concat(i[:16], i[16:])
        x1 = ~(x0 + 1)
        x2 = Concat(x1[:16], x1[16:])
        hls.write(x2, self.o)


class Slice0(HwModule):

    def _declr(self) -> None:
        addClkRstn(self)
        self.i = HwIOVectSignal(16)
        self.clk.FREQ = int(1e6)
        self.o = HwIOVectSignal(32)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = hls.read(self.i).data
        hls.write(Concat(HBits(16).from_py(0), x), self.o)

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class Slice1(Slice0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = Concat(HBits(32).from_py(0), hls.read(self.i).data)
        hls.write(x[32:], self.o)


class Slice2(Slice0):

    def _declr(self) -> None:
        addClkRstn(self)
        self.i0 = HwIOSignal()
        self.i1 = HwIOVectSignal(5)
        self.clk.FREQ = int(1e6)
        self.o = HwIOVectSignal(2)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Extracted from:

        .. code-block:: Python
            m = CrcCombHls()
            m.setConfig(CRC_5_USB)
            m.REFOUT = False
            m.CLK_FREQ = int(200e6)
            m.DATA_WIDTH = 1

        """
        v3 = hls.read(self.i0).data
        v2 = hls.read(self.i1).data
        v4 = v2[4 + 1:1]
        v7 = Concat(v4, v3)
        v9 = v7[2 + 3:2]
        v13 = BIT.from_py(0)
        v12 = Concat(v9, v13)
        v15 = v7[0]
        v18 = Concat(v12, v15)
        v27 = v18[2:]
        hls.write(v27, self.o)


class BaseSliceBreakTestPlatform(VirtualHlsPlatform):

    def __init__(self):
        VirtualHlsPlatform.__init__(self)
        self.postSliceBreak = StringIO()

    def runSsaPasses(self, hls:"HlsScope", toSsa:HlsAstToSsa):
        SsaPassConsystencyCheck().runOnSsaModule(toSsa)
        SsaPassToLlvm(hls, self._llvmCliArgs).runOnSsaModule(toSsa)
        f = toSsa.start.llvm._testSlicesToIndependentVariablesPass()
        fStr = repr(f)
        # print(fStr)
        self.postSliceBreak.write(fStr)
        raise TestFinishedSuccessfuly()


class SlicesToIndependentVariablesPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._testSlicesToIndependentVariablesPass()

    def _test_ll_direct(self, irStr: str):
        return BaseLlvmIrTC._test_ll(self, irStr)

    def _test_ll(self, hwModuleConstructor: HwModule, name=None):
        p = BaseSliceBreakTestPlatform()
        if isinstance(hwModuleConstructor, HwModule):
            unit = hwModuleConstructor
        else:
            unit = hwModuleConstructor()
        self._runTranslation(unit, p)
        if name is None:
            name = unit.__class__.__name__
        self.assert_same_as_file(p.postSliceBreak.getvalue(), os.path.join("data", self.__class__.__name__ + "." + name + ".ll"))

    def test_SliceBreakSlicedVar0_ll(self):
        self._test_ll(SliceBreakSlicedVar0)

    def test_SliceBreakSlicedVar1_ll(self):
        self._test_ll(SliceBreakSlicedVar1)

    def test_SliceBreakSlicedVar2_ll(self):
        self._test_ll(SliceBreakSlicedVar2)

    def test_SliceBreak0_ll(self):
        self._test_ll(SliceBreak0)

    def test_SliceBreak1_ll(self):
        self._test_ll(SliceBreak1)

    def test_SliceBreak2_ll(self):
        self._test_ll(SliceBreak2)

    def test_SliceBreak3_ll(self):
        self._test_ll(SliceBreak3)

    def test_Slice0_ll(self):
        self._test_ll(Slice0)

    def test_Slice1_ll(self):
        self._test_ll(Slice1)

    def test_Slice2_ll(self):
        self._test_ll(Slice2)

    def test_CountLeadingZeros(self):
        m = CountLeadingZeros()
        m.DATA_WIDTH = 4
        self._test_ll(m)

    def test_sliceZext(self):
        llvmIr = """\
        define void @test_sliceZext(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r = load volatile i25, ptr addrspace(1) %i, align 4
            %rSlice = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %r, i6 0) #2
            %0 = zext i24 %rSlice to i32
            store volatile i32 %0, ptr addrspace(2) %o, align 4
            ret void
        }
        """
        self._test_ll_direct(llvmIr)

    def test_phiLoop0(self):
        llvmIr = """\
        define void @test_phiLoop0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r = load volatile i8, ptr addrspace(1) %i, align 1
            br label %BB1
        BB1:
            %phi = phi i8 [ %r, %BB0 ], [ %xor, %BB1 ]
            %and = and i8 %phi, -2
            %xor = xor i8 %and, -1
            store volatile i8 %xor, ptr addrspace(2) %o, align 4
            br label %BB1
        }
        """
        self._test_ll_direct(llvmIr)

    def test_phiLoopCutUpBit0(self):
        llvmIr = """\
        define void @test_phiLoopCutUpBit0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r = load volatile i8, ptr addrspace(1) %i, align 1
            br label %BB1
        BB1:
            %phi = phi i8 [ %r, %BB0 ], [ %phiWithoutUpBitZext, %BB1 ]
            store volatile i8 %phi, ptr addrspace(2) %o, align 4
            %phiWithoutUpBit = call i7 @hwtHls.bitRangeGet.i8.i3.i7.0(i8 %phi, i3 0) #2
            %phiWithoutUpBitZext = zext i7 %phiWithoutUpBit to i8
            br label %BB1
        }
        """
        self._test_ll_direct(llvmIr)

    def test_phiLoopCutUpBit1(self):
        llvmIr = """\
        define void @test_phiLoopCutUpBit1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r = load volatile i8, ptr addrspace(1) %i, align 1
            br label %BB1
        BB1:
            %phi = phi i8 [ %r, %BB0 ], [ %phiWithoutUpBitZext, %BB1 ]
            %phiWithoutUpBit = call i7 @hwtHls.bitRangeGet.i8.i3.i7.0(i8 %phi, i3 0) #2
            %phiWithoutUpBitZext = zext i7 %phiWithoutUpBit to i8
            store volatile i8 %phiWithoutUpBitZext, ptr addrspace(2) %o, align 4
            br label %BB1
        }
        """
        self._test_ll_direct(llvmIr)

    def test_shiftInLoop0(self):
        # store, >> 1
        llvmIr = """\
        define void @test_shiftInLoop0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r = load volatile i4, ptr addrspace(1) %i, align 1
            br label %BB1
        BB1:
            %phi = phi i4 [ %r, %BB0 ], [ %phiSh, %BB1 ]
            store volatile i4 %phi, ptr addrspace(2) %o, align 1
            %phiShLow = call i3 @hwtHls.bitRangeGet.i4.i2.i3.0(i4 %phi, i2 1) #2
            %phiSh = zext i3 %phiShLow to i4
            br label %BB1
        }
        """
        self._test_ll_direct(llvmIr)

    def test_shiftInLoop1(self):
        # >> 1, store
        llvmIr = """\
        define void @test_shiftInLoop1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r = load volatile i4, ptr addrspace(1) %i, align 1
            br label %BB1
        BB1:
            %phi = phi i4 [ %r, %BB0 ], [ %phiSh, %BB1 ]
            %phiShLow = call i3 @hwtHls.bitRangeGet.i4.i2.i3.0(i4 %phi, i2 1) #2
            %phiSh = zext i3 %phiShLow to i4
            store volatile i4 %phiSh, ptr addrspace(2) %o, align 1
            br label %BB1
        }
        """
        self._test_ll_direct(llvmIr)

    def test_zextUle0(self):
        llvmIr = """\
        define void @test_zextUle0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r0 = load volatile i3, ptr addrspace(1) %i, align 1
            %r1 = load volatile i5, ptr addrspace(1) %i, align 1
            %zext = zext i3 %r0 to i5
            %ule = icmp ule i5 %zext, %r1
            store volatile i1 %ule, ptr addrspace(2) %o, align 1
            ret void
        }
        """
        self._test_ll_direct(llvmIr)

    def test_zextUle1(self):
        llvmIr = """\
        define void @test_zextUle1(ptr addrspace(1) %i, ptr addrspace(2) %o) {
        BB0:
            %r0 = load volatile i3, ptr addrspace(1) %i, align 1
            %r1 = load volatile i3, ptr addrspace(1) %i, align 1
            %r1zext = call i5 @hwtHls.bitConcat.i2.i3(i2 0, i3 %r1) #2
            %r0zext = zext i3 %r0 to i5
            %ule = icmp ule i5 %r1zext, %r0zext
            store volatile i1 %ule, ptr addrspace(2) %o, align 1
            ret void
        }
        """
        self._test_ll_direct(llvmIr)

    def test_ShifterLeftBarrelUsingLoop2(self):
        llvmIr = """\
            define void @ShifterLeftBarrelUsingLoop2(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %sh) {
            BB0:
              br label %BB1
            
            BB1:
              %vIn = load volatile i2, ptr addrspace(1) %i, align 1
              %vIn_b0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %vIn, i2 0) #2
              %shVal = load volatile i1, ptr addrspace(3) %sh, align 1
              %vIn_sh1 = call i2 @hwtHls.bitConcat.i1.i1(i1 false, i1 %vIn_b0) #2
              %vOut = select i1 %shVal, i2 %vIn_sh1, i2 %vIn
              store volatile i2 %vOut, ptr addrspace(2) %o, align 1
              br label %BB1
            }
        """
        self._test_ll_direct(llvmIr)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # m = SliceBreak3()
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SlicesToIndependentVariablesPass_TC('test_ShifterLeftBarrelUsingLoop2')])
    suite = testLoader.loadTestsFromTestCase(SlicesToIndependentVariablesPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
