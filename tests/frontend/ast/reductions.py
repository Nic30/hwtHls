from hwt.hObjList import HObjList
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.frontend.ast.exprTree3 import HlsAstExprTree3_example


class ForLoopWithIoSelectIn(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataIn: HObjList[HwIOStructRdVld] = HObjList(HwIOStructRdVld() for _ in range(3))
        for i in self.dataIn:
            i.T = HBits(self.DATA_WIDTH, signed=False)
        self.dataOut0: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut0.T = HBits(self.DATA_WIDTH, signed=False)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        din = self.dataIn
        res = self.dataOut0.T.from_py(0)
        while b1:
            i = uint8_t.from_py(0)
            while i < 3:
                # if this for is not unrolled the execution is sequential,
                # in each clock only a single input is read
                if i._eq(0):
                    res = hls.read(din[0]).data
                elif i._eq(1):
                    res = hls.read(din[1]).data
                elif i._eq(2):
                    res = hls.read(din[2]).data

                i += 1

            hls.write(res, self.dataOut0)

    @override
    def hwImpl(self) -> None:
        HlsAstExprTree3_example.hwImpl(self)


class ForLoopAccumulateSumInputSelByIndex(ForLoopWithIoSelectIn):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        din = self.dataIn
        res = self.dataOut0.T.from_py(0)
        while b1:
            i = uint8_t.from_py(0)
            while i < 3:
                # if this for is not unrolled the execution is sequential,
                # in each clock only a single input is read
                if i._eq(0):
                    res += hls.read(din[0]).data
                elif i._eq(1):
                    res += hls.read(din[1]).data
                elif i._eq(2):
                    res += hls.read(din[2]).data

                i += 1

            hls.write(res, self.dataOut0)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = ForLoopAccumulateSumInputSelByIndex()
    m.FREQ = int(150e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
