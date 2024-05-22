#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.frontend.ast.whileTrue import WhileTrueWriteCntr0
from tests.frontend.pyBytecode.stmWhile import TRUE
from tests.io.ioFsm import WriteFsm1WhileTrue123hs


class WriteFsmFor(WriteFsm1WhileTrue123hs):
    """
    IO write FSM inside of pipeline
    """

    @override
    def hwImpl(self) -> None:
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

    @override
    def hwImpl(self) -> None:
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

    @override
    def hwImpl(self) -> None:
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

    @override
    def hwImpl(self) -> None:
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

    @override
    def hwDeclr(self):
        WriteFsm1WhileTrue123hs.hwDeclr(self)
        self.i = HwIOStructRdVld()
        self.i.T = self.o.T

    @override
    def hwImpl(self) -> None:
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


class ReadFsmWriteFsmSumAndCondWrite(WriteFsm1WhileTrue123hs):

    @override
    def hwConfig(self) -> None:
        WriteFsm1WhileTrue123hs.hwConfig(self)
        self.USE_PY_FRONTEND = HwParam(False)

    @override
    def hwDeclr(self):
        WriteFsm1WhileTrue123hs.hwDeclr(self)
        self.i = HwIOStructRdVld()
        self.i.T = self.o.T

    def _implPy(self, hls: HlsScope) -> None:
        while TRUE:
            v0 = hls.read(self.i)
            if v0._eq(0):
                continue
            v1 = hls.read(self.i)
            if v1._eq(1):
                hls.write(1, self.o)
                hls.write(2, self.o)
                hls.write(3, self.o)

            v2 = hls.read(self.i)
            hls.write(4, self.o)
            hls.write(5, self.o)

    @override
    def hwImpl(self) -> None:
        WhileTrueWriteCntr0.hwImpl(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    dut = ReadFsmWriteFsmSumAndCondWrite()
    dut.USE_PY_FRONTEND = True
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(dut, target_platform=p))
