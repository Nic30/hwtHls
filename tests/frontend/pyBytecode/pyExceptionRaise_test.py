#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type
import unittest

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwt.hdl.types.bits import Bits
from hwt.interfaces.utils import addClkRstn


class TestException0(Exception):
    pass


class PyExceptionJustRaise(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        raise TestException0()

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        thread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(thread)
        hls.compile()


class PyExceptionRaisePyConditionaly(PyExceptionJustRaise):
    
    def _config(self) -> None:
        self.RAISE = Param(True)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        if self.RAISE:
            raise TestException0()

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssert(PyExceptionRaisePyConditionaly):

    @hlsBytecode
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
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(self.mainThreadMainPart)(hls)


class PyExceptionRaiseRaiseUsingAssertFromInlined1(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    def mainThreadMainPart(self, hls: HlsScope):
        assert not self.RAISE
        x = 0

    @hlsBytecode
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
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(self.mainThreadMainPart)(hls)
        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertFromInlined2(PyExceptionRaisePyConditionaly):

    def _declr(self):
        PyExceptionRaisePyConditionaly._declr(self)
        addClkRstn(self)
    
    @hlsBytecode
    def mainThreadMainPart(self, hls: HlsScope):
        assert not self.RAISE
        i = hls.var("i", Bits(8))
        i = 0
        while i < 4:
            hls.write(i, self.o)
            i += 1

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeInline(self.mainThreadMainPart)(hls)
        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertWithMsg(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        assert not self.RAISE, "Err msg"

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseUsingAssertWithLongerCond(PyExceptionRaisePyConditionaly):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        assert self.RAISE != True or self.RAISE != 1

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyExceptionRaiseRaiseCatch(PyExceptionJustRaise):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        try:
            raise TestException0()
        except TestException0:
            pass

        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)


class PyBytecodePyException_TC(SimTestCase):

    def _testIfCompiles(self, unit: Unit):
        t_name = self.getTestName()
        u_name = unit._getDefaultName()
        unique_name = f"{t_name:s}__{u_name:s}"
        self.compileSim(unit, unique_name=unique_name, target_platform=VirtualHlsPlatform())

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
        u = cls()
        u.RAISE = True
        with self.assertRaises(errCls):
            self._testIfCompiles(u)
        u = cls()
        u.RAISE = False
        self._testIfCompiles(u)

    @unittest.expectedFailure
    def test_PyExceptionRaiseRaiseCatch(self):
        u = PyExceptionRaiseRaiseCatch()
        self._testIfCompiles(u)


if __name__ == "__main__":
    # from hwt.synthesizer.utils import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # u = PyExceptionJustRaise()
    # #u.RAISE = False
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([PyBytecodePyException_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(PyBytecodePyException_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

