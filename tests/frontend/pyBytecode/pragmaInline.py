#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal, HwIOSignal, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline, \
    PyBytecodePreprocHwCopy, PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


class PragmaInline_singleBlock(HwModule):

    @override
    def hwDeclr(self):
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):

        @hlsBytecode
        def fn():
            hls.write(1, self.o)

        while BIT.from_py(1):
            PyBytecodeInline(fn)()

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class PragmaInline_NestedLoop(PragmaInline_singleBlock):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        b1 = BIT.from_py(1)

        @hlsBytecode
        def fn():
            while b1:
                hls.write(1, self.o)

        while b1:
            PyBytecodeInline(fn)()


class PragmaInline_return1_0(PragmaInline_singleBlock):

    @override
    def mainThread(self, hls: HlsScope):

        def fn():
            return 1

        while BIT.from_py(1):
            hls.write(PyBytecodeInline(fn)(), self.o)


class PragmaInline_return1_1(PragmaInline_return1_0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):

        @PyBytecodeInline
        def fn():
            return 1

        while BIT.from_py(1):
            hls.write(fn(), self.o)


class PragmaInline_return1_1hw(PragmaInline_return1_0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):

        @PyBytecodeInline
        def fn():
            return uint8_t.from_py(1)

        while BIT.from_py(1):
            hls.write(fn(), self.o)


class PragmaInline_writeCntr0(PragmaInline_return1_0):

    @override
    def hwDeclr(self):
        PragmaInline_return1_0.hwDeclr(self)
        addClkRstn(self)

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        @PyBytecodeInline
        def fn(cntrArg):
            hls.write(cntrArg, self.o)

        while BIT.from_py(1):
            fn(cntr)
            cntr += 1


class PragmaInline_writeCntr1(PragmaInline_return1_0):

    @override
    def hwDeclr(self):
        PragmaInline_return1_0.hwDeclr(self)
        addClkRstn(self)

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        @PyBytecodeInline
        def fn(cntrArg):
            hls.write(cntrArg, self.o)
            cntrArg += 1

        while BIT.from_py(1):
            fn(cntr)


class PragmaInline_writeCntr2(PragmaInline_writeCntr1):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        @PyBytecodeInline
        def fn():
            nonlocal cntr
            hls.write(cntr, self.o)
            cntr += 1

        while BIT.from_py(1):
            fn()


class PragmaInline_writeCntr3(PragmaInline_writeCntr1):

    @hlsBytecode
    def writeAndIncrement(self, hls, cntr):
        hls.write(cntr, self.o)
        cntr += 1
        return cntr

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        while BIT.from_py(1):
            cntr = PyBytecodeInline(self.writeAndIncrement)(hls, cntr)


class PragmaInline_writeSaturatedCntr4(PragmaInline_writeCntr1):

    @hlsBytecode
    def writeAndIncrement(self, hls, cntr, limit=4):
        cntrTmp = PyBytecodePreprocHwCopy(cntr)
        if limit > 0:
            limitBit = cntr[limit]
            if ~limitBit:
                cntr += 1
        # else:
        #    hls.write(cntr, self.o)

        return cntrTmp

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        while BIT.from_py(1):
            cntrTmp = PyBytecodeInline(self.writeAndIncrement)(hls, cntr)
            hls.write(cntrTmp, self.o)


class PragmaInline_SequenceCounter(PragmaInline_singleBlock):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.o = HwIODataRdVld()._m()
        self.o.DATA_WIDTH = 8
        self.i = HwIOSignal()

    @hlsBytecode
    @PyBytecodeInline
    def oneSeqLen(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)
        PyBytecodeBlockLabel("oneSeqLen")
        while hls.read(self.i).data:
            PyBytecodeBlockLabel("whileRead")
            cntr += 1
        PyBytecodeBlockLabel("oneSeqLenRet")
        return cntr

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("entry")
        while BIT.from_py(1):
            PyBytecodeBlockLabel("mainLoop")
            oneLen = self.oneSeqLen(self, hls)
            hls.write(oneLen, self.o)

    @override
    def hwImpl(self):
        PragmaInline_singleBlock.hwImpl(self)


class PragmaInline_FilterZeros(PragmaInline_SequenceCounter):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.o = HwIODataRdVld()._m()
        self.o.DATA_WIDTH = 8
        self.i = HwIODataRdVld()
        self.i.DATA_WIDTH = 8

    @hlsBytecode
    @PyBytecodeInline
    @override
    def oneSeqLen(self, hls: HlsScope):
        PyBytecodeBlockLabel("oneSeqLen")
        v = hls.read(self.i).data
        while v._eq(0):
            PyBytecodeBlockLabel("whileRead")
            v = hls.read(self.i).data
        PyBytecodeBlockLabel("oneSeqLenRet")
        return v


class PragmaInline_TwoInLoopLiveVars(PragmaInline_FilterZeros):

    @hlsBytecode
    @PyBytecodeInline
    @override
    def oneSeqLen(self, hls: HlsScope):
        PyBytecodeBlockLabel("oneSeqLen")
        cntr = uint8_t.from_py(0)
        v = hls.read(self.i).data
        while v < 128:
            PyBytecodeBlockLabel("whileRead")
            cntr += v
            v = hls.read(self.i).data
        if v < 4:
            cntr += 1
        PyBytecodeBlockLabel("oneSeqLenRet")
        return cntr


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = PragmaInline_SequenceCounter()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
