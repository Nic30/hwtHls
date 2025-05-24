#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Iterator

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import propagateClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaLoop import PyBytecodeLoopFlattenUsingIf
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.scope import HlsScope
from hwtLib.handshaked.reg import HandshakedReg
from tests.frontend.trivial import WhileTrueReadWrite, WhileTrueWrite


class WhileTrueWriteCntr0(WhileTrueWrite):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        cntr = self.dataOut.data._dtype.from_py(0)
        while b1:
            hls.write(cntr, self.dataOut)
            cntr = cntr + 1


class WhileTrueWriteCntr1(WhileTrueWriteCntr0):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        cntr = self.dataOut.data._dtype.from_py(0)
        while b1:
            cntr = cntr + 1
            hls.write(cntr, self.dataOut)


class WhileSendSequence0(WhileTrueReadWrite):
    """
    WhileSendSequence described as a simple feed forward pipeline without nested loops.
    """

    @override
    def hwConfig(self) -> None:
        WhileTrueReadWrite.hwConfig(self)

    @override
    def hwImpl(self) -> None:
        WhileTrueWriteCntr0.hwImpl(self)
        propagateClkRstn(self)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        sizeBuff = HandshakedReg(HwIODataRdVld)
        sizeBuff.DATA_WIDTH = self.dataIn.T.bit_length()
        sizeBuff.LATENCY = (1, 2)
        sizeBuff.INIT_DATA = ((0,),)
        self.sizeBuff = sizeBuff

        while b1:
            size = hls.read(self.sizeBuff.dataOut).data
            if size._eq(0):
                size = hls.read(self.dataIn).data
            if size > 0:
                hls.write(size, self.dataOut)
                hls.write(size - 1, sizeBuff.dataIn)
            else:
                hls.write(size, sizeBuff.dataIn)

    def model(self, dataIn: Iterator[HBitsConst]):
        size = self.dataIn.T.from_py(0)
        while True:
            while size != 0:
                yield size
                size = size - 1
            try:
                size = next(dataIn)
            except StopIteration:
                return


class WhileSendSequence1(WhileSendSequence0):
    """
    dataIn is always read if size==0, Control of loops are entirely dependent on value of size
    which makes it more simple.
    :note: this is significantly less complicated than :class:`~.WhileSendSequence2`
           however there is 1 cycle delay after reset
    """

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        size = self.dataIn.T.from_py(0)
        while b1:
            PyBytecodeBlockLabel("WhileSendSequence1.mainLoop")
            while size != 0:
                PyBytecodeBlockLabel("WhileSendSequence1.whileSize")
                hls.write(size, self.dataOut)
                size = size - 1
                PyBytecodeLoopFlattenUsingIf()

            PyBytecodeBlockLabel("WhileSendSequence1.read")
            size = hls.read(self.dataIn).data


class WhileSendSequence2(WhileTrueReadWrite):
    """
    May skip nested while loop and renter top loop
    or jump to nested  while loop, exit nested  loop and reenter top loop
    or jump to nested  while loop and reenter nested while loop.

    In addition write to dataOut needs flushing.

    :note: This is actually a complex example.
    """

    @override
    def hwConfig(self) -> None:
        WhileTrueReadWrite.hwConfig(self)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            size = hls.read(self.dataIn).data
            while size != 0:
                hls.write(size, self.dataOut)
                size = size - 1

    def model(self, dataIn: Iterator[HBitsConst]):
        yield from WhileSendSequence0.model(self, dataIn)


class WhileSendSequence3(WhileSendSequence0):
    """
    same as :class:`~.WhileSendSequence2` but more explicit
    """

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            size = self.dataIn.T.from_py(0)
            while size._eq(0):
                size = hls.read(self.dataIn).data

            while size != 0:
                hls.write(size, self.dataOut)
                size = size - 1


class WhileSendSequence4(WhileSendSequence0):
    """
    same as :class:`~.WhileSendSequence3` but more explicit
    """

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            size = self.dataIn.T.from_py(0)
            while size._eq(0):
                size = hls.read(self.dataIn).data
            while b1:
                hls.write(size, self.dataOut)
                size = size - 1
                if size._eq(0):
                    break


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = WhileTrueWriteCntr1()
    # m.DATA_WIDTH = 32
    m.CLK_FREQ = int(200e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
