#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Iterator, Union

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOVectSignal, HwIOSignal, HwIODataRdVld, HwIOClk
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.synthesizer.vectorUtils import fitTo_t
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline, \
    PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


TRUE = BIT.from_py(1)


class HlsPythonHwWhile0a(HwModule):

    def _config(self) -> None:
        self.CLK_FREQ = HwParam(HwIOClk.DEFAULT_FREQ)

    def _declr(self):
        addClkRstn(self)
        self.i = HwIOSignal()  # rst
        self.o = HwIOVectSignal(8, signed=False)._m()

    @staticmethod
    def model(dataIn: Iterator[HBitsConst], dataOut: List[int]):
        i = uint8_t.from_py(0)
        while True:  # recognized as HW loop because of type
            i += 1
            dataOut.append(int(i))
            rst = next(dataIn)
            if rst:
                i = 0

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while TRUE:  # recognized as HW loop because of type
            i += 1
            hls.write(i, self.o)
            if hls.read(self.i).data:
                i = 0

    def _impl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class HlsPythonHwWhile0b(HlsPythonHwWhile0a):
    """
    Test of directly nested HW while true loop
    """

    def _declr(self):
        addClkRstn(self)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @staticmethod
    def model(dataOut: List[int]):
        while True:
            dataOut.append(10)
            yield

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:  # recognized as HW loop because of type
            while TRUE:  # recognized as HW loop because of type
                i = uint8_t.from_py(10)
                hls.write(i, self.o)


class HlsPythonHwWhile0c(HlsPythonHwWhile0a):

    @staticmethod
    def model(dataIn: Iterator[HBitsConst], dataOut: List[HBitsConst]):
        while True:
            i = uint8_t.from_py(10)
            while True:
                i = i + 1
                dataOut.append(i)
                if next(dataIn):
                    break

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:  # recognized as HW loop because of type
            i = uint8_t.from_py(10)
            while TRUE:  # recognized as HW loop because of type
                i += 1
                hls.write(i, self.o)
                if hls.read(self.i).data:
                    break


class HlsPythonHwWhile1(HlsPythonHwWhile0a):

    @staticmethod
    def model(dataIn: Iterator[HBitsConst], dataOut: List[int]):
        i = uint8_t.from_py(10)
        while True:
            while True:
                dataOut.append(int(i))
                i = i + 1
                rst = next(dataIn)
                if rst:
                    break

            i = 0

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(10)
        while TRUE:  # recognized as HW loop because of type
            while True:  # recognized as HW loop because of break condition
                hls.write(i, self.o)
                i += 1
                if hls.read(self.i).data:
                    break

            i = 0


class HlsPythonHwWhile2(HlsPythonHwWhile0a):

    def _config(self) -> None:
        HlsPythonHwWhile0a._config(self)
        self.CLK_FREQ = int(1e6)

    def _declr(self):
        addClkRstn(self)
        self.o = HwIOStructRdVld()._m()
        self.o.T = uint8_t
        # self.o = HwIOVectSignal(8, signed=False)._m()

    @staticmethod
    def model(dataOut: List[Union[HBitsConst, int]]):
        i = uint8_t.from_py(0)
        while True:  # recognized as HW loop because of type
            if i <= 4:
                dataOut.append(i)
                yield
            elif i._eq(10):
                break
            i += 1

        while True:
            dataOut.append(0)
            yield

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while TRUE:  # recognized as HW loop because of type
            PyBytecodeBlockLabel("wh0")
            if i <= 4:
                hls.write(i, self.o)
            elif i._eq(10):
                break
            i += 1

        while TRUE:
            PyBytecodeBlockLabel("wh1")
            hls.write(0, self.o)


class HlsPythonHwWhile3(HlsPythonHwWhile2):

    def _declr(self):
        addClkRstn(self)
        self.i = HwIODataRdVld()
        self.o = HwIODataRdVld()._m()
        for i in (self.i, self.o):
            i.DATA_WIDTH = 8

    @staticmethod
    def model(dataIn: Iterator[HBitsConst], dataOut: List[Union[HBitsConst, int]]):
        while True:
            while True:
                r1 = next(dataIn)
                if r1 != 1:
                    r2 = next(dataIn)
                    dataOut.append(r2)
                    if r2 != 2:
                        break
                else:
                    break

            dataOut.append(99)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:
            while TRUE:
                r1 = hls.read(self.i)
                # dCroped = [d.data._reinterpret_cast(HBits(i * 8)) for i in range(1, self.DATA_WIDTH // 8)]
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
        self.i = HwIOStructRdVld()
        self.i.T = BIT
        self.o = HwIODataRdVld()._m()
        self.o.DATA_WIDTH = 8

    @staticmethod
    def model(dataIn: Iterator[HBitsConst], dataOut: List[HBitsConst]):
        while True:
            data = HBits(8).from_py(None)
            cntr = 8 - 1
            while cntr >= 0:
                d = next(dataIn)
                data = Concat(d, data[8:1])  # shift-in data from left
                cntr = cntr - 1
            dataOut.append(data)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        # serial to parallel
        PyBytecodeBlockLabel("mainThread")
        while TRUE:
            PyBytecodeBlockLabel("LCntrParent")
            data = HBits(8).from_py(None)
            cntr = HBits(4, signed=True).from_py(8 - 1)
            while cntr >= 0:
                PyBytecodeBlockLabel("LCntr")
                data = Concat(hls.read(self.i).data, data[8:1])  # shift-in data from left
                cntr -= 1

            PyBytecodeBlockLabel("LFinalWrite")
            hls.write(data, self.o)


class HlsPythonHwWhile5(HlsPythonHwWhile4):
    """
    Same as :class:`~.HlsPythonHwWhile4` just with extra while (because this is test of this syntax)
    """

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("mainThread")
        # serial to parallel
        while TRUE:
            PyBytecodeBlockLabel("LCntrParentParent")
            while TRUE:
                PyBytecodeBlockLabel("LCntrParent")
                data = HBits(8).from_py(None)
                cntr = HBits(4, signed=True).from_py(8 - 1)
                while cntr >= 0:
                    PyBytecodeBlockLabel("LCntr")
                    data = Concat(hls.read(self.i).data, data[8:1])  # shift-in data from left
                    cntr -= 1

                PyBytecodeBlockLabel("LFinalWrite")
                hls.write(data, self.o)


class HlsPythonHwWhile5b(HlsPythonHwWhile5):
    """
    Same as :class:`~.HlsPythonHwWhile4b` just with extra while (because this is test of this syntax)
    """

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while TRUE:
            PyBytecodeBlockLabel("mainThread")
            # serial to parallel
            while TRUE:
                PyBytecodeBlockLabel("LCntrParentParent")
                while TRUE:
                    PyBytecodeBlockLabel("LCntrParent")
                    data = HBits(8).from_py(None)
                    cntr = HBits(4, signed=True).from_py(8 - 1)
                    while cntr >= 0:
                        PyBytecodeBlockLabel("LCntr")
                        data = Concat(hls.read(self.i).data, data[8:1])  # shift-in data from left
                        cntr -= 1

                    PyBytecodeBlockLabel("LFinalWrite")
                    hls.write(data, self.o)


class HlsPythonHwWhile5c(HlsPythonHwWhile4):
    """
    Same as :class:`~.HlsPythonHwWhile5` Same as :class:`~.HlsPythonHwWhile5` with less arithmetic operations
    """

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("mainThread")
        # serial to parallel
        while TRUE:
            PyBytecodeBlockLabel("LCntrParentParent")
            while TRUE:
                PyBytecodeBlockLabel("LCntrParent")
                cntr = HBits(4, signed=True).from_py(8 - 1)
                while cntr >= 0:
                    PyBytecodeBlockLabel("LCntr")
                    cntr -= 1

                PyBytecodeBlockLabel("LFinalWrite")
                data = fitTo_t(hls.read(self.i).data, self.o.data._dtype)
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
                    data = HBits(8).from_py(None)
                    cntr = HBits(4, signed=True).from_py(8 - 1)
                    while cntr >= 0:
                        data = Concat(hls.read(self.i).data, data[8:1])  # shift-in data from left
                        cntr -= 1
                    hls.write(data, self.o)


class MovingOneGen(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(4)
        self.FREQ = HwParam(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ

        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(self.DATA_WIDTH)

    @staticmethod
    def model(dataOut: List[int]):
        t = HBits(4)
        width = t.bit_length()
        while True:
            qMask = t.from_py(1 << (width - 1))
            while qMask != 0:
                dataOut.append(int(qMask))
                yield
                qMask >>= 1

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t = self.o.T
        width = t.bit_length()
        while BIT.from_py(1):
            qMask = t.from_py(1 << (width - 1))
            while qMask != 0:
                hls.write(qMask, self.o)
                qMask >>= 1

    def _impl(self) -> None:
        HlsPythonHwWhile0a._impl(self)


class LoopCondBitSet(MovingOneGen):

    def _declr(self) -> None:
        MovingOneGen._declr(self)
        self.i = HwIOStructRdVld()
        self.i.T = BIT

    @staticmethod
    def model(dataIn: Iterator[HBitsConst], dataOut: List[int]):
        t = HBits(4)
        width = t.bit_length()
        while True:
            qMask = t.from_py(1 << (width - 1))
            res = t.from_py(0)
            while qMask != 0:
                if next(dataIn):
                    res = res | qMask
                dataOut.append(int(res))
                qMask >>= 1

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t = self.o.T
        width = t.bit_length()
        while BIT.from_py(1):
            qMask = t.from_py(1 << (width - 1))
            res = t.from_py(0)
            while qMask != 0:
                if hls.read(self.i).data:
                    res |= qMask
                hls.write(res, self.o)
                qMask >>= 1


class LoopZeroPadCompareShift(MovingOneGen):

    def _declr(self) -> None:
        MovingOneGen._declr(self)
        self.i = HwIOStructRdVld()
        self.i.T = self.o.T

    @staticmethod
    def model(dataIn: Iterator[HBitsConst], dataOut: List[int]):
        t = HBits(4)
        divisor = next(dataIn)
        dividend = next(dataIn)

        width = t.bit_length()
        zeroPad = HBits(width - 1).from_py(0)
        divisorTmp = Concat(divisor, zeroPad)
        i = 0
        while True:
            if divisorTmp <= Concat(zeroPad, dividend):
                dividend -= divisorTmp[width:]

            dataOut.append(int(dividend))
            divisorTmp >>= 1
            if i == width:
                break
            else:
                i += 1

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        divisor = hls.read(self.i).data
        dividend = hls.read(self.i).data

        t = self.o.T
        width = t.bit_length()
        zeroPad = HBits(width - 1).from_py(0)
        divisorTmp = Concat(divisor, zeroPad)

        while BIT.from_py(1):
            if divisorTmp <= Concat(zeroPad, dividend):
                dividend -= divisorTmp[width:]
            hls.write(dividend, self.o)
            divisorTmp >>= 1


class PragmaInline_HlsPythonHwWhile4(HlsPythonHwWhile4):

    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        while TRUE:
            PyBytecodeBlockLabel("LBeforeInline")
            PyBytecodeInline(HlsPythonHwWhile4.mainThread)(self, hls)


class PragmaInline_HlsPythonHwWhile5(HlsPythonHwWhile5):

    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        while TRUE:
            PyBytecodeBlockLabel("LBeforeInline")
            PyBytecodeInline(HlsPythonHwWhile5.mainThread)(self, hls)


class PragmaInline_HlsPythonHwWhile5c(HlsPythonHwWhile5):

    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        PyBytecodeBlockLabel("mainThread")
        while TRUE:
            PyBytecodeBlockLabel("LBeforeInline")
            PyBytecodeInline(HlsPythonHwWhile5c.mainThread)(self, hls)
            PyBytecodeBlockLabel("LAfterInline")


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = PragmaInline_HlsPythonHwWhile5c()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE.union(HlsDebugBundle.DBG_FRONTEND))))

