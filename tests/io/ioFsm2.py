#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.hsStructIntf import HsStructIntf
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.io.ioFsm import WriteFsm1WhileTrue123hs


class WriteFsmFor(WriteFsm1WhileTrue123hs):
    """
    IO write FSM inside of pipeline
    """

    def _impl(self) -> None:
        hls = HlsScope(self)
        i = hls.var("i", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.For(i(0), i < 3, i(i + 1),
                hls.write(1, self.o),
                hls.write(2, self.o),
                hls.write(3, self.o),
            ),
            self._name)
        )
        hls.compile()


class WriteFsmPrequel(WriteFsm1WhileTrue123hs):
    """
    IO write FSM before pipeline
    """

    def _impl(self) -> None:
        hls = HlsScope(self)
        i = hls.var("i", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                hls.write(99, self.o),
                hls.write(100, self.o),
                ast.For(i(0), i < 3, i(i + 1),
                    hls.write(i + 1, self.o),
                    hls.write(i + 2, self.o),
                    hls.write(i + 3, self.o),
                )
            ],
            self._name)
        )
        hls.compile()


class WriteFsmIf(WriteFsm1WhileTrue123hs):

    def _impl(self) -> None:
        hls = HlsScope(self)
        i = hls.var("i", uint8_t)
        
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i(0),
                ast.While(True,
                    ast.If(i._eq(0),
                        hls.write(1, self.o),
                        hls.write(2, self.o),
                        i(1),
                    ).Else(
                        hls.write(3, self.o),
                        i(0),
                    ),
                ),
            ],
            self._name)
        )
        hls.compile()

class WriteFsmIfOptionalInMiddle(WriteFsm1WhileTrue123hs):

    def _impl(self) -> None:
        hls = HlsScope(self)
        i = hls.var("i", uint8_t)
        
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i(0),
                ast.While(True,
                    hls.write(1, self.o),
                    ast.If(i._eq(0),
                        hls.write(2, self.o),
                        i(1),
                    ).Else(
                        i(0),
                    ),
                    hls.write(3, self.o),

                ),
            ],
            self._name)
        )
        hls.compile()

class WriteFsmControlledFromIn(WriteFsm1WhileTrue123hs):
    
    def _declr(self):
        WriteFsm1WhileTrue123hs._declr(self)
        self.i = HsStructIntf()
        self.i.T = self.o.T

    def _impl(self) -> None:
        hls = HlsScope(self)
        
        ast = HlsAstBuilder(hls)
        r = hls.read(self.i)
        hls.addThread(HlsThreadFromAst(hls, [
                ast.While(True,
                    hls.write(1, self.o),
                    r,
                    ast.If(r.data._eq(1),
                        hls.write(2, self.o),
                    ).Else(
                        hls.write(4, self.o),
                        hls.write(5, self.o),
                    ),
                    hls.write(3, self.o),

                ),
            ],
            self._name)
        )
        hls.compile()

if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = WriteFsmPrequel()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(u, target_platform=p))
