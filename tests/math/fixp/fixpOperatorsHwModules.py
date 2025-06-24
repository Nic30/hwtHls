
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmpCast import castToHFloatTmp


# https://medium.com/incredible-coder/converting-fixed-point-to-floating-point-format-and-vice-versa-6cbc0e32544e
class _FixpBinOpTestModule(HwModule):

    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))
        self.FN = HwParam(lambda a, b: a + b)

    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.data_in = HwIOStructRdVld()
        t = HBits(self.T.bit_length())  # can not currently use HFixedPointQ for IO of the module
        self.data_in.T = HStruct(
            (t, "a"),
            (t, "b")
        )

        self.data_out = HwIOStructRdVld()._m()
        self.data_out.T = t

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        T = self.T
        while b1:
            inp = hls.read(self.data_in).data
            # a = inp.data.a._auto_cast(HFloatTmp)
            # b = inp.data.b._auto_cast(HFloatTmp)
            a = castToHFloatTmp(inp.a._reinterpret_cast(T))
            b = castToHFloatTmp(inp.b._reinterpret_cast(T))

            res = self.FN(a, b)
            hls.write(res._auto_cast(self.T), self.data_out, mayBecomeFlushable=False)

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class _FixpCmpOpTestModule(HwModule):

    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))
        self.FN = HwParam(lambda a, b: a < b)

    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.data_in = HwIOStructRdVld()
        t = HBits(self.T.bit_length())  # can not currently use HFixedPointQ for IO of the module
        self.data_in.T = HStruct(
            (t, "a"),
            (t, "b")
        )

        self.data_out = HwIOStructRdVld()._m()
        self.data_out.T = BIT

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        T = self.T
        while b1:
            inp = hls.read(self.data_in).data
            a = castToHFloatTmp(inp.a._reinterpret_cast(T))
            b = castToHFloatTmp(inp.b._reinterpret_cast(T))

            res = self.FN(a, b)
            hls.write(res, self.data_out, mayBecomeFlushable=False)

    def hwImpl(self) -> None:
        _FixpBinOpTestModule.hwImpl(self)


class _FixpUnOpTestModule(HwModule):

    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))
        self.FN = HwParam(lambda a, b:-a)

    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.data_in = HwIOStructRdVld()
        t = HBits(self.T.bit_length())  # can not currently use HFixedPointQ for IO of the module
        self.data_in.T = HStruct(
            (t, "a"),
        )

        self.data_out = HwIOStructRdVld()._m()
        self.data_out.T = t

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        T = self.T
        while b1:
            inp = hls.read(self.data_in).data
            # a = inp.data.a._reinterpret_cast(HFloatTmp)
            # b = inp.data.b._reinterpret_cast(HFloatTmp)
            a = castToHFloatTmp(inp.a._reinterpret_cast(T))

            res = self.FN(a)
            hls.write(res._auto_cast(self.T), self.data_out, mayBecomeFlushable=False)

    def hwImpl(self) -> None:
        _FixpBinOpTestModule.hwImpl(self)


class _FixpCastOpTestModule(_FixpUnOpTestModule):

    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))
        self.T_OUT = HwParam(HFixedPointQ(2, 3))

    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.data_in = HwIOStructRdVld()
        t = HBits(self.T.bit_length())  # can not currently use HFixedPointQ for IO of the module
        self.data_in.T = HStruct(
            (t, "a"),
        )

        self.data_out = HwIOStructRdVld()._m()
        self.data_out.T = HBits(self.T_OUT.bit_length())

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        T = self.T
        T_OUT = self.T_OUT
        T_OUT_RAW = self.data_out.T
        while b1:
            inp = hls.read(self.data_in).data
            a = inp.a._reinterpret_cast(T)
            aCasted = a._auto_cast(T_OUT)
            hls.write(aCasted._reinterpret_cast(T_OUT_RAW), self.data_out, mayBecomeFlushable=False)
