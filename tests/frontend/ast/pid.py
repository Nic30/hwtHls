#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Add
from hwt.hdl.commonConstants import b1
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.logic.pid import PidController
from tests.frontend.ast.exprTree3 import HlsAstExprTree3_example


class PidControllerHalfHls(PidController):
    """
    A variant of PID regulator where only expression between the registers is in HLS context.
    """

    @override
    def hwConfig(self):
        super(PidControllerHalfHls, self).hwConfig()
        self.CLK_FREQ = HwParam(int(50e6))

    @override
    def hwDeclr(self):
        PidController.hwDeclr(self)
        self.clk.FREQ = self.CLK_FREQ

    @override
    def hwImpl(self):
        # register of current output value
        u = self._reg("u", dtype=self.output._dtype, def_val=0)
        # propagate output value register to output
        self.output(u)

        # create y-pipeline registers (y -> y_reg[0]-> y_reg[1])
        y = [self.input, ]
        for i in range(2):
            _y = self._reg(f"y_reg{i:d}", dtype=self.input._dtype, def_val=0)
            # feed data from last register
            _y(y[-1])
            y.append(_y)

        # trim signal to width of output
        def trim(signal):
            return signal._reinterpret_cast(self.output._dtype)

        @hlsBytecode
        def mainThread(hls: HlsScope):
            # in HLS create only arith. expressions between inputs and regs
            while b1:
                _y = [hls.read(_y).data for _y in y]
                err = _y[0] - hls.read(self.target).data
                a = [hls.read(c).data for c in self.coefs]

                _u = Add(hls.read(u).data,
                         a[0] * err,
                         a[1] * _y[0],
                         a[2] * _y[1],
                         a[3] * _y[2],
                         key=trim)

                hls.write(_u, u.next)

        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, mainThread, hls))
        hls.compile()


class PidControllerHls(PidControllerHalfHls):
    """
    A variant of PID regulator where whole computation is in HLS context.
    (Including main loop and reset.)
    """

    @hlsBytecode
    def mainThread(self, hls: HlsScope):

        # trim signal to width of output
        def trim(signal):
            return signal._reinterpret_cast(self.output._dtype)

        # create y-pipeline registers (y -> y_reg[0]-> y_reg[1])
        y = [None, ]
        for i in range(2):
            y.append(hls.var(f"y_reg{i:d}", dtype=self.input._dtype))

        # initial reset
        u = self.output._dtype.from_py(0)
        y[1](0)  # operator() is used because assignment to subscript would replace variable reference with 0
        y[2](0)
        while b1:
            y[0] = hls.read(self.input).data
            err = y[0] - hls.read(self.target).data
            coefs = [hls.read(c).data for c in self.coefs]
            # next value computation
            u = Add(u,
                    coefs[0] * err,
                    coefs[1] * y[0],
                    coefs[2] * y[1],
                    coefs[3] * y[2], key=trim)
            # propagate output value register to output
            hls.write(u, self.output)
            # shift y registers
            y[2](y[1])
            y[1](y[0])

    @override
    def hwImpl(self) -> None:
        HlsAstExprTree3_example.hwImpl(self)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    # m = PidController()
    # print(to_rtl_str(m))
    m = PidControllerHls()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
