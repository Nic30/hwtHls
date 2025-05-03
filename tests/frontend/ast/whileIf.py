#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from tests.frontend.ast.trivial import WhileTrueWrite, WhileTrueReadWrite


class WhileAndIf0(WhileTrueWrite):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            x = HBits(self.DATA_WIDTH, signed=False).from_py(10)
            # add counter of pending transactions on enter to while
            # if there is not pending transaction we do not require the control token
            # from while body end to push data in while body, otherwise we need to wait for one
            while x:
                if x < 3:
                    x -= 1
                else:
                    x -= 3
                # the branches does not contains dynamically scheduled code,
                # no need to manage control tokens
                # use just regular pipeline with MUXes
                hls.write(x, self.dataOut)


class WhileAndIf0b(WhileAndIf0):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            x = HBits(self.DATA_WIDTH, signed=False).from_py(10)
            while x:
                if x < 3:
                    x -= 1
                    hls.write(x, self.dataOut)
                else:
                    x -= 3
                    hls.write(x, self.dataOut)


class WhileAndIf1(WhileTrueWrite):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            x = HBits(self.DATA_WIDTH, signed=False).from_py(10)
            while x:
                if x < 3:
                    x -= 1
                else:
                    x -= 3
                hls.write(x, self.dataOut)

            hls.write(x, self.dataOut)


class WhileAndIf2(WhileTrueReadWrite):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            x = HBits(self.DATA_WIDTH, signed=False).from_py(10)
            while x:
                x -= hls.read(self.dataIn).data
                # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                hls.write(x, self.dataOut)


class WhileAndIf3(WhileTrueReadWrite):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            x = HBits(self.DATA_WIDTH, signed=False).from_py(10)
            while b1:
                x -= hls.read(self.dataIn).data
                hls.write(x, self.dataOut)
                if x._eq(0):
                    break


class WhileAndIf4(WhileTrueReadWrite):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            x = HBits(self.DATA_WIDTH, signed=False).from_py(10)
            while b1:
                    x -= hls.read(self.dataIn).data
                    if x < 5:
                        hls.write(x, self.dataOut)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = WhileAndIf0()
    m.DATA_WIDTH = 4
    m.FREQ = int(50e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
