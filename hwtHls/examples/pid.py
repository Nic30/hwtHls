#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Add
from hwt.synthesizer.param import Param
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.logic.pid import PidController


class PidControllerHalfHls(PidController):
    """
    A variant of PID regulator where only expression betwen the registers is in HLS context.
    """

    def _config(self):
        super(PidControllerHalfHls, self)._config()
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        PidController._declr(self)
        self.clk.FREQ = self.CLK_FREQ

    def _impl(self):
        # register of current output value
        u = self._reg("u", dtype=self.output._dtype, def_val=0)

        # create y-pipeline registers (y -> y_reg[0]-> y_reg[1])
        y = [self.input, ]
        for i in range(2):
            _y = self._reg("y_reg%d" % i, dtype=self.input._dtype, def_val=0)
            # feed data from last register
            _y(y[-1])
            y.append(_y)

        # trim signal to width of output
        def trim(signal):
            return signal._reinterpret_cast(self.output._dtype)

        # create arith. expressions between inputs and regs
        hls = HlsStreamProc(self)
        y = [hls.read(_y) for _y in y]
        err = y[0] - hls.read(self.target)
        a = [hls.read(c) for c in self.coefs]

        _u = Add(hls.read(u), a[0] * err, a[1] * y[0],
                 a[2] * y[1], a[3] * y[2], key=trim)

        hls.thread(
            hls.While(True,
                hls.write(_u, u.next)
            )
        )

        # propagate output value register to output
        self.output(u)


class PidControllerHls(PidControllerHalfHls):
    """
    A variant of PID regulator where whole computation is in HLS context.
    (Including main loop and reset.)
    """

    def _impl(self):
        # register of current output value
        hls = HlsStreamProc(self)

        # create y-pipeline registers (y -> y_reg[0]-> y_reg[1])
        y = [hls.read(self.input), ]
        for i in range(2):
            _y = hls.var("y_reg%d" % i, dtype=self.input._dtype)
            # feed data from last register
            _y(y[-1])
            y.append(_y)

        # trim signal to width of output
        def trim(signal):
            return signal._reinterpret_cast(self.output._dtype)

        err = y[0] - hls.read(self.target)
        a = [hls.read(c) for c in self.coefs]
        u = hls.var("u", self.output._dtype)
        _u = Add(hls.read(u), a[0] * err, a[1] * y[0],
                 a[2] * y[1], a[3] * y[2], key=trim)

        hls.thread(
            u(0),
            *(_y(0) for _y in y[1:]),
            hls.While(True,
                # next value computation
                u(_u),
                # propagate output value register to output
                hls.write(u, self.output)
            )
        )


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    u = PidController()
    print(to_rtl_str(u))
    u = PidControllerHls()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))
