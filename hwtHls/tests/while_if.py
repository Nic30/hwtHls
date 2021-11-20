#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import If
from hwt.hdl.types.bits import Bits
from hwtHls.hlsStreamProc.streamProc  import HlsStreamProc
from hwtHls.tests.trivial import WhileTrueWrite, WhileTrueReadWrite


class WhileAndIf0(WhileTrueWrite):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending trasactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(x,
                    If(x < 3,
                       x(x - 1),
                    ).Else(
                       x(x - 3),
                    ),
                    # the branches does not contains dynamicaly scheduled code,
                    # no need to manage control tokens
                    # use just regular pipeline with muxes
                    hls.write(x, self.dataOut)
                ),
            )
        )


class WhileAndIf1(WhileTrueWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending trasactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(x,
                    If(x < 3,
                       x(x - 1),
                    ).Else(
                       x(x - 3),
                    ),
                    # the branches does not contains dynamicaly scheduled code,
                    # no need to manage control tokens
                    # use just regular pipeline with muxes
                    hls.write(x, dout)
                ),
                hls.write(x, dout)
            )
        )


class WhileAndIf2(WhileTrueReadWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending trasactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(x,
                    x(x - hls.read(self.dataIn)),
                    # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                    hls.write(x, dout)
                ),
            )
        )


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = WhileAndIf0()
    u.DATA_WIDTH = 32
    u.FREQ = int(130e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))
