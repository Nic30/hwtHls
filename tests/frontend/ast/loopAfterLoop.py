#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


class TwoTimesFiniteWhileInWhileTrue(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.FREQ = Param(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataOut0: HsStructIntf = HsStructIntf()._m()
        self.dataOut0.T = Bits(self.DATA_WIDTH, signed=False)
        self.dataOut1: HsStructIntf = HsStructIntf()._m()
        self.dataOut1.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i0, i1 = (hls.var(f"i{i}", uint8_t) for i in range(2))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                ast.While(True,
                    i0(0),
                    ast.While(i0 != 4,
                        hls.write(4, self.dataOut0),
                        i0(i0 + 1)
                    ),
                    i1(0),
                    ast.While(i1 != 5,
                        hls.write(5, self.dataOut1),
                        i1(i1 + 1)
                    ),
                )
            ],
            self._name)
        )
        hls.compile()



class TwoTimesFiniteWhile(TwoTimesFiniteWhileInWhileTrue):

    def _impl(self) -> None:
        hls = HlsScope(self)
        i0, i1 = (hls.var(f"i{i}", uint8_t) for i in range(2))
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i0(0),
                ast.While(i0 != 4,
                    hls.write(4, self.dataOut0),
                    i0(i0 + 1)
                ),
                i1(0),
                ast.While(i1 != 5,
                    hls.write(5, self.dataOut1),
                    i1(i1 + 1)
                ),
            ],
            self._name)
        )
        hls.compile()



class FiniteWhileIf0(TwoTimesFiniteWhileInWhileTrue):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.FREQ = Param(int(100e6))

    def _declr(self) -> None:
        TwoTimesFiniteWhileInWhileTrue._declr(self)
        self.dataIn0: HsStructIntf = HsStructIntf()
        self.dataIn0.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i0 = hls.var("i0", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i0(0),
                ast.While(i0 != 4,
                    hls.write(4, self.dataOut0),
                    i0(i0 + 1)
                ),
                ast.If(hls.read(self.dataIn0)._eq(8),
                    hls.write(7, self.dataOut1),
                ),
            ],
            self._name)
        )
        hls.compile()



class FiniteWhileIf1(TwoTimesFiniteWhileInWhileTrue):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.FREQ = Param(int(100e6))

    def _declr(self) -> None:
        TwoTimesFiniteWhileInWhileTrue._declr(self)
        self.dataIn0: HsStructIntf = HsStructIntf()
        self.dataIn0.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i0 = hls.var("i0", uint8_t)
        din0 = hls.read(self.dataIn0)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, [
                i0(0),
                ast.While(i0 != 4,
                    hls.write(4, self.dataOut0),
                    i0(i0 + 1)
                ),
                ast.If(din0._eq(8),
                    hls.write(7, self.dataOut1),
                ).Elif(din0._eq(7),
                    hls.write(6, self.dataOut1),
                ),
            ],
            self._name)
        )
        hls.compile()



if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = FiniteWhileIf1()
    u.FREQ = int(150e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
