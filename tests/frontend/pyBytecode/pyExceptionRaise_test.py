#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type
import unittest

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope


class TestException0(Exception):
    pass


class PyExceptionJustRaise(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        raise TestException0()

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        thread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(thread)
        hls.compile()


class PyExceptionRaisePyConditionaly(PyExceptionJustRaise):

    @override
    def hwConfig(self) -> None:
        self.RAISE = HwParam(True)

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        if self.RAISE:
            raise TestException0()

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssert(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        assert not self.RAISE

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertFromInlined0(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    def mainThreadMainPart(self, hls: HlsScope):
        assert not self.RAISE

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(self.mainThreadMainPart)(hls)


class PyExceptionRaiseRaiseUsingAssertFromInlined1(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    def mainThreadMainPart(self, hls: HlsScope):
        assert not self.RAISE
        x = 0

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(self.mainThreadMainPart)(hls)
        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertFromInlinedWithLognerCond(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    def mainThreadMainPart(self, hls: HlsScope):
        assert not (self.RAISE != False and self.RAISE != 0)
        x = 0

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(self.mainThreadMainPart)(hls)
        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertFromInlined2(PyExceptionRaisePyConditionaly):

    @override
    def hwDeclr(self):
        PyExceptionRaisePyConditionaly.hwDeclr(self)
        addClkRstn(self)

    @hlsBytecode
    def mainThreadMainPart(self, hls: HlsScope):
        assert not self.RAISE
        i = hls.var("i", HBits(8))
        i = 0
        while i < 4:
            hls.write(i, self.o)
            i += 1

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(self.mainThreadMainPart)(hls)
        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertWithMsg(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        assert not self.RAISE, "Err msg"

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertWithLongerCond(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        assert self.RAISE != True or self.RAISE != 1

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseCatch(PyExceptionJustRaise):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        try:
            raise TestException0()
        except TestException0:
            pass

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyBytecodePyException_TC(SimTestCase):

    def _testIfCompiles(self, module: HwModule):
        t_name = self.getTestName()
        u_name = module._getDefaultName()
        unique_name = f"{t_name:s}__{u_name:s}"
        self.compileSim(module, unique_name=unique_name, target_platform=VirtualHlsPlatform())

    def test_PyExceptionJustRaise(self):
        with self.assertRaises(TestException0):
            self._testIfCompiles(PyExceptionJustRaise())

    def test_PyExceptionRaisePyConditionaly(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaisePyConditionaly, errCls=TestException0)

    def test_PyExceptionRaiseRaiseUsingAssert(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaiseRaiseUsingAssert, errCls=AssertionError)

    def test_PyExceptionRaiseRaiseUsingAssertFromInlined0(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaiseRaiseUsingAssertFromInlined0, errCls=AssertionError)

    def test_PyExceptionRaiseRaiseUsingAssertFromInlined1(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaiseRaiseUsingAssertFromInlined1, errCls=AssertionError)

    def test_PyExceptionRaiseRaiseUsingAssertFromInlined2(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaiseRaiseUsingAssertFromInlined2, errCls=AssertionError)

    def test_PyExceptionRaiseRaiseUsingAssertWithMsg(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaiseRaiseUsingAssertWithMsg, errCls=AssertionError)

    def test_PyExceptionRaiseRaiseUsingAssertWithLongerCond(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaiseRaiseUsingAssertWithLongerCond, errCls=AssertionError)

    def test_PyExceptionRaiseRaiseUsingAssertFromInlinedWithLognerCond(self):
        self._test_PyExceptionRaisePyConditionaly(PyExceptionRaiseRaiseUsingAssertFromInlinedWithLognerCond, errCls=AssertionError)

    def _test_PyExceptionRaisePyConditionaly(self, cls: Type[PyExceptionRaisePyConditionaly], errCls: Type[Exception]):
        dut = cls()
        dut.RAISE = True
        with self.assertRaises(errCls):
            self._testIfCompiles(dut)

        dut = cls()
        dut.RAISE = False
        self._testIfCompiles(dut)

    @unittest.expectedFailure
    def test_PyExceptionRaiseRaiseCatch(self):
        dut = PyExceptionRaiseRaiseCatch()
        self._testIfCompiles(dut)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # m = PyExceptionJustRaise()
    # #m.RAISE = False
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyBytecodePyException_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(PyBytecodePyException_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

