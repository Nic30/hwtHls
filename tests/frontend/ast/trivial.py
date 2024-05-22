#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope


class WriteOnce(HwModule):

    def _config(self):
        self.FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        o = self.dataOut = HwIOStructRdVld()._m()
        o.T = HBits(self.DATA_WIDTH, signed=False)

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
        i = self.dataIn = HwIOStructRdVld()
        i.T = HBits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromAst(hls,
            hls.write(hls.read(self.dataIn).data, self.dataOut),
            self._name)
        )
        hls.compile()


class ReadWriteOnce1(ReadWriteOnce0):

    def _impl(self) -> None:
        hls = HlsScope(self)
        tmp = hls.var("tmp", self.dataIn.T)
        hls.addThread(HlsThreadFromAst(hls, [
                tmp(hls.read(self.dataIn).data),
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
                tmp(hls.read(self.dataIn).data),
                hls.write(tmp + 1, self.dataOut),
            ],
            self._name)
        )
        hls.compile()


class WhileTrueWrite(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataOut: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut.T = HBits(self.DATA_WIDTH, signed=False)

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


class WhileTrueReadWrite(WhileTrueWrite):

    def _declr(self) -> None:
        super(WhileTrueReadWrite, self)._declr()
        i = self.dataIn = HwIOStructRdVld()
        i.T = HBits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsScope(self)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(hls.read(self.dataIn).data, self.dataOut)
            ),
            self._name)
        )
        hls.compile()


class WhileTrueReadWriteExpr(WhileTrueReadWrite):

    def _impl(self) -> None:
        hls = HlsScope(self)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write((hls.read(self.dataIn).data * 8 + 2) * 3, self.dataOut)
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = WhileTrueReadWriteExpr()
    m.FREQ = int(150e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
