#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Due to break on HW evaluated condition the preprocessor loop can have multiple exit points with a different state of stack and locals.
This is a problem and requires that all variants of successor code are translate for each variant of stack/locals.
However the duplication has a limiter. Once we are sure that the preproc value are not used in successor block we may stop duplication and converge
all duplicate on this successor block. Because we can not easily analyze the bytecode if it modifies some value we must depend on definition scopes.
The terminators for duplications are:
* The end of function body
* The end of HW evaluated loop body
"""

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline, \
    PyBytecodePreprocDivergence
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


class PreprocLoopMultiExit_singleExit0(HwModule):

    def _config(self):
        self.FREQ = HwParam(int(10e6))
        self.DATA_WIDTH = HwParam(8)

    def _declr(self):
        with self._hwParamsShared():
            self.i = HwIODataRdVld()
            self.o = HwIODataRdVld()._m()
            addClkRstn(self)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Will expand to:

        .. code-block:: Python

            if hls.read(self.i).data != 0:
                hls.write(0, self.o)
            if hls.read(self.i).data != 1:
                hls.write(1, self.o)
            if hls.read(self.i).data != 2:
                hls.write(2, self.o)
        """
        for i in range(3):  # this for is unrolled in preprocessor
            if hls.read(self.i).data != i:
                hls.write(i, self.o)
                # [todo] add variant with the break because this one does not actually generate error
            # in each iteration this block will exist only once because divergence is not marked

    def _impl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class PreprocLoopMultiExit_singleExit1(PreprocLoopMultiExit_singleExit0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Will expand to:

        .. code-block:: Python

            if hls.read(self.i).data != 0:
                hls.write(0, self.o)
                if hls.read(self.i).data != 1:
                    hls.write(1, self.o)
                else:
                    if hls.read(self.i).data != 2:
                        hls.write(2, self.o)

            else:
                if hls.read(self.i).data != 1:
                    hls.write(1, self.o)
                else:
                    if hls.read(self.i).data != 2:
                        hls.write(2, self.o)

        """

        for i in range(3):  # this for is unrolled in preprocessor
            if PyBytecodePreprocDivergence(hls.read(self.i).data != i):
                hls.write(i, self.o)
            # this block is duplicated for every possibility of condition in previous if statement


class PreprocLoopMultiExit_hwBreak0(PreprocLoopMultiExit_singleExit0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Will expand to (unintended the value of 'i' is not propagated as expected):

        .. code-block:: Python

            if hls.read(self.i).data == 0 or hls.read(self.i).data == 0 or hls.read(self.i).data == 0:
                hls.write(0, self.o)

        """
        for i in range(3):  # this for statement is unrolled in preprocessor
            if hls.read(self.i).data._eq(0):
                # This block is actually outside of the lopp and there will be only one instance of it and it will have i=0
                hls.write(i, self.o)
                break


class PreprocLoopMultiExit_hwBreak1(PreprocLoopMultiExit_singleExit0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        Will expand to (unintended the value of 'i' is not propagated as expected):

        .. code-block:: Python

            if hls.read(self.i).data == 0:
                hls.write(0, self.o)
            elif hls.read(self.i).data == 0:
                hls.write(1, self.o)
            elif hls.read(self.i).data == 0:
                hls.write(2, self.o)
        """
        for i in range(3):  # this for statement is unrolled in preprocessor
            if PyBytecodePreprocDivergence(hls.read(self.i).data._eq(0)):
                # this block is duplicated for every possibility of break from previous for statement
                hls.write(i, self.o)
                break


class PreprocLoopMultiExit_hwBreak2(PreprocLoopMultiExit_singleExit0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        :meth:`~.PreprocLoopMultiExit_hwBreak1.mainThread` in infinite hardware loop
        """
        while BIT.from_py(1):
            for i in range(4):
                if PyBytecodePreprocDivergence(hls.read(self.i).data._eq(0)):
                    hls.write(i, self.o)
                    break


class PreprocLoopMultiExit_hwBreak3(PreprocLoopMultiExit_singleExit0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        """
        :note: same as :class:`~.PreprocLoopMultiExit_hwBreak2` just with :class:`PyBytecodeInline`
        """
        while BIT.from_py(1):
            PyBytecodeInline(PreprocLoopMultiExit_hwBreak1.mainThread)(self, hls)


class PreprocLoopMultiExit_countLeadingZeros_0(PreprocLoopMultiExit_singleExit0):

    def _config(self):
        self.FREQ = HwParam(int(10e6))
        self.DATA_WIDTH = HwParam(3)

    def _declr(self):
        with self._hwParamsShared():
            self.i = HwIODataRdVld()
            addClkRstn(self)
        self.o = HwIODataRdVld()._m()
        self.o.DATA_WIDTH = 8

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            d = hls.read(self.i).data
            zeroCnt = uint8_t.from_py(self.DATA_WIDTH)
            for i in range(self.DATA_WIDTH):
                zeroCnt = i  # there the value of i does not reach out of parent loop
                if d[i]:
                    break
            hls.write(zeroCnt, self.o)


class PreprocLoopMultiExit_countLeadingZeros_1_error(PreprocLoopMultiExit_singleExit0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            d = hls.read(self.i).data
            zeroCnt = uint8_t.from_py(self.DATA_WIDTH)
            for i in range(self.DATA_WIDTH):
                if d[i]:
                    # error: there the value of i reaches out of parent loop
                    # and it is not marked so preprocessor does not know about it
                    # because of this zeroCnt will work only for min and max value
                    zeroCnt = i
                    break

            hls.write(zeroCnt, self.o)


class PreprocLoopMultiExit_countLeadingZeros_2(PreprocLoopMultiExit_singleExit0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            d = hls.read(self.i).data
            zeroCnt = uint8_t.from_py(self.DATA_WIDTH)
            for i in range(self.DATA_WIDTH):
                if PyBytecodePreprocDivergence(d[i]):
                    # the value of i reaches out of parent loop
                    # and it is marked so preprocessor knows about it
                    zeroCnt = i
                    break

            hls.write(zeroCnt, self.o)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = PreprocLoopMultiExit_countLeadingZeros_0()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
