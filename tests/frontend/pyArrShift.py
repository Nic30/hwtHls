#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from hwt.code import Concat
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, \
    PyBytecodeInPreproc
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope


class PyArrShift(HwModule):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        arr = [hls.var(f"arr{i:d}", self.o._dtype) for i in range(3)]
        # :note: using () instead of just = because we want to set value not just rewrite reference in preprocessor
        for item in arr:
            item(0)

        while b1:
            for i in range(len(arr) - 1, 0, -1):
                arr[i](arr[i - 1])

            arr[0](hls.read(self.i).data)
            hls.write(arr[-1], self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        t = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(t)
        hls.compile()


class PyArrShiftFn(PyArrShift):

    @staticmethod
    def shiftArray(arr: list):
        for i in range(len(arr) - 1, 0, -1):
            arr[i](arr[i - 1])

    @override
    def mainThread(self, hls: HlsScope):
        arr = [hls.var(f"arr{i:d}", self.o._dtype) for i in range(3)]
        # :note: using () instead of just = because we want to set value not just rewrite reference in preprocessor
        for item in arr:
            item(0)

        while b1:
            PyBytecodeInline(self.shiftArray)(arr)
            arr[0](hls.read(self.i).data)
            hls.write(arr[-1], self.o)


class PyArrShiftFnStruct(PyArrShift):

    @staticmethod
    @override
    def shiftArray(arr: list):
        for i in range(len(arr) - 1, 0, -1):
            arr[i](arr[i - 1])

    @override
    def mainThread(self, hls: HlsScope):
        HALF_WIDTH = self.o._dtype.bit_length() // 2
        halfT = HBits(HALF_WIDTH)
        Ty = HStruct((halfT, "low"),
                     (halfT, "high"))
        arr = [hls.var(f"arr{i:d}", Ty) for i in range(3)]
        # :note: using () instead of just = because we want to set value not just rewrite reference in preprocessor
        for item in arr:
            item(Ty.from_py({"high": 0, "low": 0}))

        while b1:
            PyBytecodeInline(self.shiftArray)(arr)

            d = hls.read(self.i).data
            arr[0].low(d[HALF_WIDTH:])
            arr[0].high(d[:HALF_WIDTH])

            last = PyBytecodeInPreproc(arr[-1])
            hls.write(Concat(last.high, last.low), self.o)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = PyArrShiftFnStruct()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
