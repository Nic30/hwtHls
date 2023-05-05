#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Add
from hwt.synthesizer.param import Param
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.logic.pid import PidController


class PidControllerHalfHls(PidController):
    """
    A variant of PID regulator where only expression betwen the registers is in HLS context.
    """

    def _config(self):
        super(PidControllerHalfHls, self)._config()
        self.CLK_FREQ = Param(int(50e6))

    def _declr(self):
        PidController._declr(self)
        self.clk.FREQ = self.CLK_FREQ

    def _impl(self):
        # register of current output value
        u = self._reg("u", dtype=self.output._dtype, def_val=0)

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

        hls = HlsScope(self)
        # in HLS create only arith. expressions between inputs and regs
        y = [hls.read(_y).data for _y in y]
        err = y[0] - hls.read(self.target).data
        a = [hls.read(c).data for c in self.coefs]

        _u = Add(hls.read(u).data, a[0] * err, a[1] * y[0],
                 a[2] * y[1], a[3] * y[2], key=trim)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(_u, u.next)
            ),
            self._name)
        )
        hls.compile()

        # propagate output value register to output
        self.output(u)


class PidControllerHls(PidControllerHalfHls):
    """
    A variant of PID regulator where whole computation is in HLS context.
    (Including main loop and reset.)
    """

    def _impl(self):
        # register of current output value
        hls = HlsScope(self)

        # create y-pipeline registers (y -> y_reg[0]-> y_reg[1])
        y = [hls.read(self.input).data, ]
        for i in range(2):
            y.append(hls.var(f"y_reg{i:d}", dtype=self.input._dtype))

        # trim signal to width of output
        def trim(signal):
            return signal._reinterpret_cast(self.output._dtype)

        err = y[0] - hls.read(self.target).data
        coefs = [hls.read(c).data for c in self.coefs]
        u = hls.var("u", self.output._dtype)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
            # initial reset
            u(0),
            y[1](0),
            y[2](0),
            ast.While(True,
                # next value computation
                u(Add(u,
                      coefs[0] * err,
                      coefs[1] * y[0],
                      coefs[2] * y[1],
                      coefs[3] * y[2], key=trim)),
                # propagate output value register to output
                hls.write(u, self.output),
                # shift y registers
                y[2](y[1]),
                y[1](y[0]),
            )
            ],
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    # u = PidController()
    # print(to_rtl_str(u))
    u = PidControllerHls()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
