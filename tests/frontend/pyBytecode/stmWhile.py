#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal, Signal, Handshaked, Clk
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline,\
    PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


TRUE = BIT.from_py(1)

class HlsPythonHwWhile0(Unit):

    def _config(self) -> None:
        Clk._declr(self)

    def _declr(self):
        addClkRstn(self)
        self.i = Signal()  # rst
        self.o = VectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while TRUE:  # recognized as HW loop because of type
            i += 1
            hls.write(i, self.o)
            if hls.read(self.i).data:
                i = 0

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class HlsPythonHwWhile0b(HlsPythonHwWhile0):
    """
    Test of directly nested HW while true loop
    """

    def _declr(self):
        addClkRstn(self)
        self.o = VectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:  # recognized as HW loop because of type
            while TRUE:  # recognized as HW loop because of type
                i = uint8_t.from_py(10)
                hls.write(i, self.o)


class HlsPythonHwWhile0c(HlsPythonHwWhile0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:  # recognized as HW loop because of type
            i = uint8_t.from_py(10)
            while TRUE:  # recognized as HW loop because of type
                i += 1
                hls.write(i, self.o)
                if hls.read(self.i).data:
                    break


class HlsPythonHwWhile1(HlsPythonHwWhile0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while TRUE:  # recognized as HW loop because of type
            while True:  # recognized as HW loop because of break condition
                hls.write(i, self.o)
                i += 1
                if hls.read(self.i).data:
                    break

            i = 0


class HlsPythonHwWhile2(HlsPythonHwWhile0):

    def _declr(self):
        addClkRstn(self)
        self.o = VectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while TRUE:  # recognized as HW loop because of type
            if i <= 4:
                hls.write(i, self.o)
            elif i._eq(10):
                break
            i += 1

        while TRUE:
            hls.write(0, self.o)


class HlsPythonHwWhile3(HlsPythonHwWhile2):

    def _declr(self):
        addClkRstn(self)
        self.i = Handshaked()
        self.o = Handshaked()._m()
        for i in (self.i, self.o):
            i.DATA_WIDTH = 8

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:
            while TRUE:
                r1 = hls.read(self.i)
                # dCroped = [d.data._reinterpret_cast(Bits(i * 8)) for i in range(1, self.DATA_WIDTH // 8)]
                if r1 != 1:
                    r2 = hls.read(self.i)
                    hls.write(r2, self.o)
                    if r2 != 2:
                        break
                else:
                    break

            hls.write(99, self.o)


class HlsPythonHwWhile4(HlsPythonHwWhile2):

    def _declr(self):
        addClkRstn(self)
        self.i = Handshaked()
        self.o = Handshaked()._m()
        self.i.DATA_WIDTH = 1
        self.o.DATA_WIDTH = 8

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        # serial to parallel
        while TRUE:
            data = Bits(8).from_py(None)
            cntr = Bits(4, signed=True).from_py(8 - 1)
            while cntr >= 0:
                data = Concat(hls.read(self.i).data, data[8:1])  # shift-in data from left
                cntr -= 1
            hls.write(data, self.o)


class HlsPythonHwWhile5(HlsPythonHwWhile4):
    """
    Same as :class:`~.HlsPythonHwWhile4` just with extra while (because this is test of this syntax)
    """

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        # serial to parallel
        while TRUE:
            PyBytecodeBlockLabel("LCntrParentParent")
            while TRUE:
                PyBytecodeBlockLabel("LCntrParent")
                data = Bits(8).from_py(None)
                cntr = Bits(4, signed=True).from_py(8 - 1)
                while cntr >= 0:
                    PyBytecodeBlockLabel("LCntr")
                    data = Concat(hls.read(self.i).data, data[8:1])  # shift-in data from left
                    cntr -= 1
                hls.write(data, self.o)


class HlsPythonHwWhile6(HlsPythonHwWhile4):
    """
    Same as :class:`~.HlsPythonHwWhile5` just with extra while (because this is test of this syntax)
    """

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        # serial to parallel
        while TRUE:
            while TRUE:
                while TRUE:
                    data = Bits(8).from_py(None)
                    cntr = Bits(4, signed=True).from_py(8 - 1)
                    while cntr >= 0:
                        data = Concat(hls.read(self.i).data, data[8:1])  # shift-in data from left
                        cntr -= 1
                    hls.write(data, self.o)


class PragmaInline_HlsPythonHwWhile5(HlsPythonHwWhile5):

    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        while TRUE: # [fixme] afterPrefix does not add prefix correctly and generates new blocks without loop prefix for inlined blocks
            PyBytecodeBlockLabel("LBeforeInline")
            PyBytecodeInline(HlsPythonHwWhile5.mainThread)(self, hls)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = HlsPythonHwWhile2()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE.union(HlsDebugBundle.DBG_FRONTEND))))

