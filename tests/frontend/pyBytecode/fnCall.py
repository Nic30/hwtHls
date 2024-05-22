#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


@hlsBytecode
def checkedFn0():
    return 1


@hlsBytecode
def checkedFn1():
    for _ in range(3):
        return


@hlsBytecode
def checkedFn2(a, b, c):
    assert a == 0, a
    assert b == 1, b
    assert c == 2, c
    return 10


@hlsBytecode
def checkedFn3(a=None, b=None, c=None):
    assert a == 0, a
    assert b == 1, b
    assert c == 2, c
    return 10


@hlsBytecode
def checkedFn4(a, b, c, d=None, e=None, f=None):
    assert a == 0, a
    assert b == 1, b
    assert c == 2, c
    assert d == 3, d
    assert e == 4, e
    assert f == 5, f
    return 10


@hlsBytecode
def checkedFn5(a, b, c, d=None, e=4, f=None):
    assert a == 0, a
    assert b == 1, b
    assert c == 2, c
    assert d == 3, d
    assert e == 4, e
    assert f == 5, f
    return 10


@hlsBytecode
def checkedFn6(*args):
    a, b, c = args
    assert a == 0, a
    assert b == 1, b
    assert c == 2, c
    return 10


@hlsBytecode
def checkedFn7(*args, d=None, e=4, f=None):
    a, b, c = args
    assert a == 0, a
    assert b == 1, b
    assert c == 2, c
    assert d == 3, d
    assert e == 4, e
    assert f == 5, f
    return 10


class FnCallFn(HwModule):

    def _declr(self):
        self.o = HwIOVectSignal(8, signed=False)._m()
    
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        checkedFn1()
        while BIT.from_py(1):
            hls.write(1, self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class FnCallFnRet(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(checkedFn0(), self.o)


class FnCallFnArgs(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(checkedFn2(0, 1, 2), self.o)


class FnCallFnArgsExpand(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            args = (0, 1, 2)
            hls.write(checkedFn2(*args), self.o)


class FnCallFnKwArgs(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(checkedFn3(a=0, b=1, c=2), self.o)


class FnCallFnArgsKwArgs(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(checkedFn4(0, 1, 2, d=3, e=4, f=5), self.o)


class FnCallFnArgsKwArgsSomeDefault(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(checkedFn5(0, 1, 2, d=3, f=5), self.o)


class FnCallFnVariadic(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(checkedFn6(0, 1, 2), self.o)


class FnCallFnVariadicExpand(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            ags = (0, 1, 2)
            hls.write(checkedFn6(*ags), self.o)


class FnCallFnVariadicExpandKwArgs(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            ags = (0, 1, 2)
            hls.write(checkedFn6(*ags, d=3, f=5), self.o)


class FnCallFnVariadicExpandKwArgsExpand(FnCallFn):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            ags = (0, 1, 2)
            kwargs = {"d": 3, "f":5}
            hls.write(checkedFn6(*ags, **kwargs), self.o)


class FnCallMethod(FnCallFn):

    def checkedMethod1(self):
        assert isinstance(self, FnCallFn), self
        
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        self.checkedMethod1()
        while BIT.from_py(1):
            hls.write(1, self.o)


class FnCallMethodArgsKwArgsSomeDefault(FnCallFn):

    @hlsBytecode
    def checkedMeth5(self, a, b, c, d=None, e=4, f=None):
        assert isinstance(self, FnCallFn), self
        assert a == 0, a
        assert b == 1, b
        assert c == 2, c
        assert d == 3, d
        assert e == 4, e
        assert f == 5, f
        return 10

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(self.checkedMeth5(0, 1, 2, d=3, f=5), self.o)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = FnCallFnVariadicExpandKwArgsExpand()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
