#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class HlsPythonPreprocFor(HwModule):

    def hwDeclr(self):
        addClkRstn(self)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        for i in range(5):
            hls.write(i, self.o)

    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class HlsPythonPreprocForInIf0(HlsPythonPreprocFor):

    def hwConfig(self) -> None:
        HlsPythonPreprocFor.hwConfig(self)
        self.IF_COND = HwParam(True)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        if self.IF_COND:
            for i in range(5):
                hls.write(i, self.o)
        else:
            for i in range(3):
                hls.write(i, self.o)


class HlsPythonPreprocForInIf1(HlsPythonPreprocForInIf0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("begin")
        cntr = self.o._dtype.from_py(0)
        # while TRUE:
        if self.IF_COND:
            PyBytecodeBlockLabel("if.true")
            for _ in range(1, 3):
                PyBytecodeBlockLabel("for.head")
                hls.write(cntr, self.o)
                if cntr._eq(2):
                    PyBytecodeBlockLabel("for.break")
                    break

        PyBytecodeBlockLabel("exit")
        hls.write(cntr, self.o)
        # cntr += 1


class HlsPythonPreprocForInIf2(HlsPythonPreprocForInIf0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("begin")
        cntr = self.o._dtype.from_py(0)
        while b1:
            if self.IF_COND:
                PyBytecodeBlockLabel("if.true")
                for _ in range(1, 3):
                    PyBytecodeBlockLabel("for.head")
                    hls.write(cntr, self.o)
                    if cntr._eq(2):
                        PyBytecodeBlockLabel("for.break")
                        break

            PyBytecodeBlockLabel("exit")
            hls.write(cntr, self.o)
            cntr += 1


class HlsPythonPreprocForPreprocWhile(HlsPythonPreprocFor):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        for i in range(5):
            while i < 2:
                hls.write(i, self.o)
                i += 1


class HlsPythonPreprocFor2x_0(HlsPythonPreprocFor):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        for y in range(2):
            for x in range(2):
                hls.write((y << 1) | x, self.o)


class HlsPythonPreprocFor2x_1(HlsPythonPreprocFor):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        for y in range(2):
            for _ in range(2):
                hls.write(y << 1, self.o)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = HlsPythonPreprocForInIf2()
    m.IF_COND = False
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
