#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope


class WriteFsm0(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: VectSignal = VectSignal(self.DATA_WIDTH, signed=False)._m()

    def _impl(self) -> None:
        hls = HlsScope(self)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(1, self.o),
                hls.write(2, self.o),
                hls.write(3, self.o),
            ),
            self._name)
            
        )
        hls.compile()



class WriteFsm0Once(WriteFsm0):

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(
            HlsThreadFromAst(hls, [
                hls.write(1, self.o),
                hls.write(2, self.o),
                hls.write(3, self.o),
            ],
            self._name)
        )
        hls.compile()


class WriteFsm1(WriteFsm0):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: HsStructIntf = HsStructIntf()._m()
        self.o.T = Bits(self.DATA_WIDTH)


class WriteFsm1Once(WriteFsm1):

    def _impl(self) -> None:
        WriteFsm0Once._impl(self)


class ReadFsm0(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i = VectSignal(self.DATA_WIDTH)
        self.o = VectSignal(3 * self.DATA_WIDTH)._m()

    def _impl(self) -> None:
        hls = HlsScope(self)
        r = [hls.read(self.i) for _ in range(3)]
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls, 
            ast.While(True,
                *r,
                hls.write(Concat(*reversed([_r.data for _r in r])), self.o),
            ),
            self._name)
        )
        hls.compile()



class ReadFsm0Once(ReadFsm0):

    def _impl(self) -> None:
        hls = HlsScope(self)
        r = [hls.read(self.i) for _ in range(3)]
        hls.addThread(HlsThreadFromAst(hls, [
                *r,
                hls.write(Concat(*reversed([_r.data for _r in r])), self.o),
            ],
            self._name)
        )
        hls.compile()



class ReadFsm1(ReadFsm0):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i: HsStructIntf = HsStructIntf()
        self.i.T = Bits(self.DATA_WIDTH)       
        self.o: HsStructIntf = HsStructIntf()._m()
        self.o.T = Bits(3 * self.DATA_WIDTH)


class ReadFsm1Once(ReadFsm1):

    def _impl(self) -> None:
        ReadFsm0Once._impl(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = WriteFsm0()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
