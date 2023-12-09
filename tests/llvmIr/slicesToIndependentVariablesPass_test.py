from io import StringIO
import os

from hwt.code import Concat
#from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, parseIR
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal, Signal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm
from tests.baseSsaTest import BaseSsaTC, TestFinishedSuccessfuly
from tests.bitOpt.countBits import CountLeadingZeros
#from tests.bitOpt.slicesMergePass_test import generateAndAppendHwtHlsFunctionDeclarations


class SliceBreakSlicedVar0(Unit):

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = int(1e6)
        self.o = VectSignal(32)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = Bits(32).from_py(0)
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
        x = Bits(32).from_py(0)
        x[1] = 1
        x[0] = 1
        hls.write(x, self.o)


class SliceBreakSlicedVar2(SliceBreakSlicedVar0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = Bits(32).from_py(0)
        x[5] = 1
        hls.write(x, self.o)


class SliceBreak0(SliceBreakSlicedVar0):

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = int(1e6)
        self.i = VectSignal(32)
        self.o = VectSignal(32)._m()

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


class Slice0(Unit):

    def _declr(self) -> None:
        addClkRstn(self)
        self.i = VectSignal(16)
        self.clk.FREQ = int(1e6)
        self.o = VectSignal(32)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = hls.read(self.i).data
        hls.write(Concat(Bits(16).from_py(0), x), self.o)

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class Slice1(Slice0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        x = Concat(Bits(32).from_py(0), hls.read(self.i).data)
        hls.write(x[32:], self.o)


class Slice2(Slice0):

    def _declr(self) -> None:
        addClkRstn(self)
        self.i0 = Signal()
        self.i1 = VectSignal(5)
        self.clk.FREQ = int(1e6)
        self.o = VectSignal(2)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Extracted from:

        .. code-block:: Python
            u = CrcCombHls()
            u.setConfig(CRC_5_USB)
            u.REFOUT = False
            u.CLK_FREQ = int(200e6)
            u.DATA_WIDTH = 1

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
        SsaPassConsystencyCheck().apply(hls, toSsa)
        SsaPassToLlvm().apply(hls, toSsa)
        f = toSsa.start.llvm._testSlicesToIndependentVariablesPass()
        fStr = repr(f)
        # print(fStr)
        self.postSliceBreak.write(fStr)
        raise TestFinishedSuccessfuly()


class SlicesToIndependentVariablesPass_TC(BaseSsaTC):
    __FILE__ = __file__

    #def _test_ll_direct(self, irStr: str):
    #    irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
    #    llvm = LlvmCompilationBundle("test")
    #    Err = SMDiagnostic()
    #    M = parseIR(irStr, "test", Err, llvm.ctx)
    #    if M is None:
    #        raise AssertionError(Err.str("test", True, True))
    #    else:
    #        fns = tuple(M)
    #        llvm.main = fns[0]
    #        name = llvm.main.getName().str()
    #
    #    optF = llvm._testSlicesToIndependentVariablesPass()
    #    print(optF)
    #    self.assert_same_as_file(repr(optF), os.path.join("data", self.__class__.__name__ + '.' + name + ".ll"))

    def _test_ll(self, unitConstructor: Unit, name=None):
        p = BaseSliceBreakTestPlatform()
        if isinstance(unitConstructor, Unit):
            unit = unitConstructor
        else:
            unit = unitConstructor()
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

    def test(self):
        u = CountLeadingZeros()
        u.DATA_WIDTH = 4
        self._test_ll(u)

if __name__ == "__main__":
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = SliceBreak3()
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([SlicesToIndependentVariablesPass_TC('test_SliceBreak3_ll')])
    suite = testLoader.loadTestsFromTestCase(SlicesToIndependentVariablesPass_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
