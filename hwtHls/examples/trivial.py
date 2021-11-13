from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc


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
        hls = HlsStreamProc(self)
        hls.thread(
            hls.write(1, self.dataOut)
        )


class ReadWriteOnce0(WriteOnce):

    def _declr(self):
        super(ReadWriteOnce0, self)._declr()
        i = self.dataIn = HsStructIntf()
        i.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        hls.thread(
            hls.write(hls.read(self.dataIn), self.dataOut)
        )


class ReadWriteOnce1(ReadWriteOnce0):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        tmp = hls.var("tmp", self.dataIn.T)
        hls.thread(
            tmp(hls.read(self.dataIn)),
            hls.write(tmp, self.dataOut),
        )


class ReadWriteOnce2(ReadWriteOnce0):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        tmp = hls.var("tmp", self.dataIn.T)
        hls.thread(
            tmp(hls.read(self.dataIn)),
            hls.write(tmp + 1, self.dataOut),
        )


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
        hls = HlsStreamProc(self)
        hls.thread(
            hls.While(True,
                hls.write(10, dout)
            )
        )


class WhileTrueReadWrite(WhileTrueWrite):

    def _declr(self) -> None:
        super(WhileTrueReadWrite, self)._declr()
        i = self.dataIn = HsStructIntf()
        i.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        hls.thread(
            hls.While(True,
                hls.write(hls.read(self.dataIn, self.dataIn.T), self.dataOut)
            )
        )


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = WhileTrueWrite()
    u.FREQ = int(150e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))
