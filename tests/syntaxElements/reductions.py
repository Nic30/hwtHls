from hwt.synthesizer.hObjList import HObjList
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.synthesizer.param import Param
from hwt.interfaces.utils import addClkRstn
from hwt.hdl.types.bits import Bits
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtLib.types.ctypes import uint8_t


class SumReduce(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.FREQ = Param(int(100e6))

    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataIn: HObjList[HsStructIntf] = HObjList(HsStructIntf() for _ in range(3))
        for i in self.dataIn:
            i.T = Bits(self.DATA_WIDTH, signed=False)
        self.dataOut0: HsStructIntf = HsStructIntf()._m()
        self.dataOut0.T = Bits(self.DATA_WIDTH, signed=False)

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        din = self.dataIn
        res = hls.var("res", self.dataOut0.T)
        i = hls.var("i", uint8_t)
        hls.thread(
            hls.While(True,
                res(0),
                hls.For(i(0), i < 3, i(i + 1),
                    hls.If(i._eq(0),
                        i(hls.read(din[0])),
                    ).Elif(i._eq(1),
                        i(hls.read(din[1])),
                    ).Elif(i._eq(2),
                        i(hls.read(din[2])),
                    )
                ),
                hls.write(res, self.dataOut0),
            )
        )


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform, makeDebugPasses
    u = SumReduce()
    u.FREQ = int(150e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
