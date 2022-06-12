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


class WriteOnce(Unit):

    def _config(self):
        self.FREQ = Param(int(100e6))
        self.DATA_WIDTH = Param(8)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        o = self.dataOut = HsStructIntf()._m()
        o.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromAst(hls,
            hls.write(1, self.dataOut),
            self._name)
        )
        hls.compile()


class ReadWriteOnce0(WriteOnce):

    def _declr(self):
        super(ReadWriteOnce0, self)._declr()
        i = self.dataIn = HsStructIntf()
        i.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromAst(hls,
            hls.write(hls.read(self.dataIn), self.dataOut),
            self._name)
        )
        hls.compile()


class ReadWriteOnce1(ReadWriteOnce0):

    def _impl(self) -> None:
        hls = HlsScope(self)
        tmp = hls.var("tmp", self.dataIn.T)
        hls.addThread(HlsThreadFromAst(hls, [
                tmp(hls.read(self.dataIn)),
                hls.write(tmp, self.dataOut),
            ],
            self._name)
        )
        hls.compile()


class ReadWriteOnce2(ReadWriteOnce0):

    def _impl(self) -> None:
        hls = HlsScope(self)
        tmp = hls.var("tmp", self.dataIn.T)
        hls.addThread(HlsThreadFromAst(hls, [
                tmp(hls.read(self.dataIn)),
                hls.write(tmp + 1, self.dataOut),
            ],
            self._name)
        )
        hls.compile()


class WhileTrueWrite(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.FREQ = Param(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataOut: HsStructIntf = HsStructIntf()._m()
        self.dataOut.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        dout = self.dataOut
        hls = HlsScope(self)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(10, dout)
            ),
            self._name)
        )
        hls.compile()


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


class WhileTrueReadWrite(WhileTrueWrite):

    def _declr(self) -> None:
        super(WhileTrueReadWrite, self)._declr()
        i = self.dataIn = HsStructIntf()
        i.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(hls.read(self.dataIn, self.dataIn.T), self.dataOut)
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = WhileTrueWriteCntr0()
    u.FREQ = int(150e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
