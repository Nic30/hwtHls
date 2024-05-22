from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hObjList import HObjList
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


class ForLoopWithIoSelectIn(HwModule):

    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataIn: HObjList[HwIOStructRdVld] = HObjList(HwIOStructRdVld() for _ in range(3))
        for i in self.dataIn:
            i.T = HBits(self.DATA_WIDTH, signed=False)
        self.dataOut0: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut0.T = HBits(self.DATA_WIDTH, signed=False)

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        din = self.dataIn
        res = hls.var("res", self.dataOut0.T)
        i = hls.var("i", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                res(0),
                ast.For(i(0), i < 3, i(i + 1),
                    # if this for is not unrolled the execution is sequential,
                    # in each clock only a single input is read
                    ast.If(i._eq(0),
                        res(hls.read(din[0]).data),
                    ).Elif(i._eq(1),
                        res(hls.read(din[1]).data),
                    ).Elif(i._eq(2),
                        res(hls.read(din[2]).data),
                    )
                ),
                hls.write(res, self.dataOut0),
            ),
            self._name)
        )
        hls.compile()


class SumReduce(ForLoopWithIoSelectIn):

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        din = self.dataIn
        res = hls.var("res", self.dataOut0.T)
        i = hls.var("i", uint8_t)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                res(0),
                ast.For(i(0), i < 3, i(i + 1),
                    # if this for is not unrolled the execution is sequential,
                    # in each clock only a single input is read
                    ast.If(i._eq(0),
                        res(res + hls.read(din[0]).data),
                    ).Elif(i._eq(1),
                        res(res + hls.read(din[1]).data),
                    ).Elif(i._eq(2),
                        res(res + hls.read(din[2]).data),
                    )
                ),
                hls.write(res, self.dataOut0),
            ),
            self._name)
        )
        hls.compile()

if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = SumReduce()
    m.FREQ = int(150e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
