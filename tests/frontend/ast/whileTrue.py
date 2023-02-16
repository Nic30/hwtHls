#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import propagateClkRstn
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.handshaked.reg import HandshakedReg
from tests.frontend.ast.trivial import WhileTrueReadWrite, WhileTrueWrite


class WhileTrueWriteCntr0(WhileTrueWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsScope(self)
        cntr = hls.var("cntr", dout.data._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
            cntr(0),
            ast.While(True,
                hls.write(cntr, dout),
                cntr(cntr + 1),
            )
            ], self._name)
        )
        hls.compile()


class WhileTrueWriteCntr1(WhileTrueWrite):

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsScope(self)
        cntr = hls.var("cntr", dout.data._dtype)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
            cntr(0),
            ast.While(True,
                cntr(cntr + 1),
                hls.write(cntr, dout),
            )
            ], self._name)
        )
        hls.compile()


class WhileSendSequence0(WhileTrueReadWrite):
    """
    WhileSendSequence described as a simple feed forward pipeline.
    """

    def _impl(self) -> None:
        hls = HlsScope(self)
        sizeBuff = HandshakedReg(Handshaked)
        sizeBuff.DATA_WIDTH = self.dataIn.T.bit_length()
        sizeBuff.LATENCY = (1, 2)
        sizeBuff.INIT_DATA = ((0,),)
        self.sizeBuff = sizeBuff

        size = hls.var("size", self.dataIn.T)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                size(hls.read(self.sizeBuff.dataOut).data),
                ast.If(size._eq(0),
                    size(hls.read(self.dataIn).data)
                ),
                ast.If(size > 0,
                    hls.write(size, self.dataOut),
                    hls.write(size - 1, sizeBuff.dataIn)
                ).Else(
                    hls.write(size, sizeBuff.dataIn)
                
                )
            ),
            self._name)
        )
        hls.compile()
        propagateClkRstn(self)


class WhileSendSequence1(WhileSendSequence0):
    """
    dataIn is always read if size==0, Control of loops are entirely dependent on value of size
    which makes it more simple.
    :note: this is significantly more simple than :class:`~.WhileSendSequence2`
           however there is 1 cycle delay after reset
    """

    def _impl(self) -> None:
        hls = HlsScope(self)

        size = hls.var("size", self.dataIn.T)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                ast.While(size != 0,
                    hls.write(size, self.dataOut),
                    size(size - 1),
                ),
                # [todo] last iteration requires dataIn to be present
                # as a consequence the last dataOut stuck in the component and is currently
                # not flushed by default. However based on the original code user probably
                # expect the dataOut to be flushed. 
                size(hls.read(self.dataIn).data),
            ),
            self._name)
        )
        hls.compile()


class WhileSendSequence2(WhileTrueReadWrite):
    """
    May skip nested while loop and renter top loop
    or jump to nested  while loop, exit nested  loop and reenter top loop
    or jump to nested  while loop and reenter nested while loop.
    
    In addition write to dataOut needs flushing.

    :note: This is actually a complex example.
    """

    def _impl(self) -> None:
        hls = HlsScope(self)

        size = hls.var("size", self.dataIn.T)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            # sync 26 = loop on bb1 (while read size == 0)
            # sync 57 = enter to loop48
            # loop48 is expected to be exited but it is not because it was just entered
            # however if this was the case the dataIn should be read and the cfg should jump directly to bb3
            ast.While(True,
                size(hls.read(self.dataIn).data),
                ast.While(size != 0,
                    hls.write(size, self.dataOut),
                    size(size - 1),
                ),
            ),
            self._name)
        )
        hls.compile()


class WhileSendSequence3(WhileSendSequence0):
    """
    same as :class:`~.WhileSendSequence2` but more explicit
    """

    def _impl(self) -> None:
        hls = HlsScope(self)

        size = hls.var("size", self.dataIn.T)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                ast.While(size._eq(0),
                    size(hls.read(self.dataIn).data),
                ),
                ast.While(size != 0,
                    hls.write(size, self.dataOut),
                    size(size - 1),
                ),
            ),
            self._name)
        )
        hls.compile()


class WhileSendSequence4(WhileSendSequence0):
    """
    same as :class:`~.WhileSendSequence3` but more explicit
    """

    def _impl(self) -> None:
        hls = HlsScope(self)

        size = hls.var("size", self.dataIn.T)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                ast.While(size._eq(0),
                    size(hls.read(self.dataIn).data),
                ),
                ast.While(True,
                    hls.write(size, self.dataOut),
                    size(size - 1),
                    ast.If(size._eq(0),
                        ast.Break(),
                    )
                ),
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = WhileSendSequence0()
    # u.DATA_WIDTH = 32
    u.FREQ = int(20e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
