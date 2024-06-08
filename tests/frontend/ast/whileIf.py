#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from tests.frontend.ast.trivial import WhileTrueWrite, WhileTrueReadWrite


class WhileAndIf0(WhileTrueWrite):

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        x = hls.var("x", HBits(self.DATA_WIDTH, signed=False))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                ast.While(x,
                    ast.If(x < 3,
                       x(x - 1),
                    ).Else(
                       x(x - 3),
                    ),
                    # the branches does not contains dynamically scheduled code,
                    # no need to manage control tokens
                    # use just regular pipeline with MUXes
                    hls.write(x, self.dataOut)
                ),
            ),
            self._name)
        )
        hls.compile()


class WhileAndIf0b(WhileAndIf0):

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        x = hls.var("x", HBits(self.DATA_WIDTH, signed=False))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                x(10),
                ast.While(x,
                    ast.If(x < 3,
                       x(x - 1),
                       hls.write(x, self.dataOut),
                    ).Else(
                       x(x - 3),
                       hls.write(x, self.dataOut),
                    ),
                ),
            ),
            self._name)
        )
        hls.compile()


class WhileAndIf1(WhileTrueWrite):

    def hwImpl(self) -> None:
        dout = self.dataOut
        hls = HlsScope(self)
        x = hls.var("x", HBits(self.DATA_WIDTH, signed=False))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                ast.While(x,
                    ast.If(x < 3,
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
            ),
            self._name)
        )
        hls.compile()


class WhileAndIf2(WhileTrueReadWrite):

    def hwImpl(self) -> None:
        dout = self.dataOut
        hls = HlsScope(self, namePrefix="")
        x = hls.var("x", HBits(self.DATA_WIDTH, signed=False))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                ast.While(x,
                    x(x - hls.read(self.dataIn).data),
                    # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                    hls.write(x, dout),
                ),
            ),
            self._name)
        )
        hls.compile()


class WhileAndIf3(WhileTrueReadWrite):

    def hwImpl(self) -> None:
        dout = self.dataOut
        hls = HlsScope(self, namePrefix="")
        x = hls.var("x", HBits(self.DATA_WIDTH, signed=False))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                ast.While(True,
                    x(x - hls.read(self.dataIn).data),
                    # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                    hls.write(x, dout),
                    ast.If(x._eq(0),
                        ast.Break()
                    )
                ),
            ),
            self._name)
        )
        hls.compile()


class WhileAndIf4(WhileTrueReadWrite):

    def hwImpl(self) -> None:
        dout = self.dataOut
        hls = HlsScope(self, namePrefix="")
        x = hls.var("x", HBits(self.DATA_WIDTH, signed=False))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                x(10),
                # add counter of pending transactions on enter to while
                # if there is not pending transaction we do not require the control token
                # from while body end to push data in while body, otherwise we need to wait for one
                ast.While(True,
                    x(x - hls.read(self.dataIn).data),
                    # a single predecessor, control sync managed by pipeline, no dynamic scheduling
                    ast.If(x < 5,
                        hls.write(x, dout),
                    )
                ),
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = WhileAndIf0()
    m.DATA_WIDTH = 4
    m.FREQ = int(50e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
