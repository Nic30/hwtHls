#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline, \
    PyBytecodeInPreproc
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.bits import Bits
from hwt.code import Concat


class PyArrShift(Unit):

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsScope):
        arr = [hls.var(f"arr{i}", self.o._dtype) for i in range(3)]
        # :note: using () instead of just = because we want to set value not just rewrite reference in preprocessor
        for item in arr:
            item(0)

        while BIT.from_py(1):
            for i in range(len(arr) - 1, 0, -1):
                arr[i](arr[i - 1])

            arr[0](hls.read(self.i))
            hls.write(arr[-1], self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        t = HlsThreadFromPy(hls, self.mainThread, hls)
        # t.bytecodeToSsa.debug = True
        hls.addThread(t)
        hls.compile()


class PyArrShiftFn(PyArrShift):

    @staticmethod
    def shiftArray(arr: list):
        for i in range(len(arr) - 1, 0, -1):
            arr[i](arr[i - 1])
    
    def mainThread(self, hls: HlsScope):
        arr = [hls.var(f"arr{i}", self.o._dtype) for i in range(3)]
        # :note: using () instead of just = because we want to set value not just rewrite reference in preprocessor
        for item in arr:
            item(0)

        while BIT.from_py(1):
            PyBytecodeInline(self.shiftArray)(arr)
            arr[0](hls.read(self.i))
            hls.write(arr[-1], self.o)


class PyArrShiftFnStruct(PyArrShift):

    @staticmethod
    def shiftArray(arr: list):
        for i in range(len(arr) - 1, 0, -1):
            arr[i](arr[i - 1])
    
    def mainThread(self, hls: HlsScope):
        HALF_WIDTH = self.o._dtype.bit_length() // 2
        halfT = Bits(HALF_WIDTH)
        arr = [hls.var(f"arr{i}", HStruct((halfT, "low"),
                                          (halfT, "high"))) for i in range(3)]
        # :note: using () instead of just = because we want to set value not just rewrite reference in preprocessor
        for item in arr:
            item(item._dtype.from_py({"high": 0, "low": 0}))

        while BIT.from_py(1):
            PyBytecodeInline(self.shiftArray)(arr)
            d = hls.read(self.i)
            arr[0].low(d[HALF_WIDTH:])
            arr[0].high(d[:HALF_WIDTH])
            last = PyBytecodeInPreproc(arr[-1])
            hls.write(Concat(last.high, last.low), self.o)

    
if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    u = PyArrShiftFnStruct()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
