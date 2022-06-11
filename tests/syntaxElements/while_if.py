#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwtHls.hlsStreamProc.streamProc  import HlsStreamProc
from tests.syntaxElements.trivial import WhileTrueWrite, WhileTrueReadWrite


class WhileAndIf0(WhileTrueWrite):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(x,
                    hls.If(x < 3,
                       x(x - 1),
                    ).Else(
                       x(x - 3),
                    ),
                    # the branches does not contains dynamically scheduled code,
                    # no need to manage control tokens
                    # use just regular pipeline with MUXes
                    hls.write(x, self.dataOut)
                ),
            )
        )
        hls.compile()



class WhileAndIf0b(WhileAndIf0):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                hls.While(x,
                    hls.If(x < 3,
                       x(x - 1),
                       hls.write(x, self.dataOut),
                    ).Else(
                       x(x - 3),
                       hls.write(x, self.dataOut),
                    ),
                ),
            )
        )
        hls.compile()



class WhileAndIf1(WhileTrueWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(x,
                    hls.If(x < 3,
                       x(x - 1),
                    ).Else(
                       x(x - 3),
                    ),
                    # the branches does not contains dynamically scheduled code,
                    # no need to manage control tokens
                    # use just regular pipeline with MUXes
                    hls.write(x, dout)
                ),
                hls.write(x, dout)
            )
        )
        hls.compile()



class WhileAndIf2(WhileTrueReadWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(x,
                    x(x - hls.read(self.dataIn)),
                    # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                    hls.write(x, dout),
                ),
            )
        )
        hls.compile()



class WhileAndIf3(WhileTrueReadWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(True,
                    x(x - hls.read(self.dataIn)),
                    # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                    hls.write(x, dout),
                    hls.If(x._eq(0),
                        hls.Break()
                    )
                ),
            )
        )
        hls.compile()


class WhileAndIf4(WhileTrueReadWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsStreamProc(self)
        x = hls.var("x", Bits(self.DATA_WIDTH, signed=False))
        hls.thread(
            hls.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                hls.While(True,
                    x(x - hls.read(self.dataIn)),
                    # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                    hls.If(x < 5,
                        hls.write(x, dout),
                    )
                ),
            )
        )
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = WhileAndIf4()
    u.DATA_WIDTH = 4
    u.FREQ = int(130e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
