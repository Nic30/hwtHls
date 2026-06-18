
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.scope import HlsScope
from tests.math.fixp.fixpResize import fixp_resize, fixp_resize_py
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpCast import castToHFloatTmp
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


class _FixpUnOpTestModule(HwModule):

    @override
    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))

    @staticmethod
    def HLS_OP_FN(a):
        raise NotImplementedError("Implement this in your test")

    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(self, data_in: float) -> bool:
        return self.HLS_OP_FN(data_in)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.data_in = HwIOStructRdVld()
        t = HBits(self.T.bit_length())  # can not currently use HFixedPointQ for IO of the module
        self.data_in.T = t

        self.data_out = HwIOStructRdVld()._m()
        self.data_out.T = t

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        T = self.T
        while b1:
            inp = hls.read(self.data_in).data
            # a = inp.data._reinterpret_cast(HFloatTmp)
            a = castToHFloatTmp(inp._reinterpret_cast(T))

            res = self.HLS_OP_FN(a)
            assert res._dtype is HFloatTmp
            resOut = res._explicit_cast(self.T)
            hls.write(resOut, self.data_out, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        _FixpBinOpTestModule.hwImpl(self)


# https://medium.com/incredible-coder/converting-fixed-point-to-floating-point-format-and-vice-versa-6cbc0e32544e
class _FixpBinOpTestModule(HwModule):

    @override
    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))

    @staticmethod
    def HLS_OP_FN(a, b):
        raise NotImplementedError("Implement this in your test")
    
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(self, a: float, b: float) -> float:
        return self.HLS_OP_FN(a, b)

    @override
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
            # a = inp.data.a._explicit_cast(HFloatTmp)
            # b = inp.data.b._explicit_cast(HFloatTmp)
            a = castToHFloatTmp(inp.a._reinterpret_cast(T))
            b = castToHFloatTmp(inp.b._reinterpret_cast(T))

            res = self.HLS_OP_FN(a, b)
            assert res._dtype is HFloatTmp
            resOut = res._explicit_cast(self.T)
            hls.write(resOut, self.data_out, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class _FixpCmpOpTestModule(HwModule):

    @override
    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))

    @staticmethod
    def HLS_OP_FN(a, b):
        raise NotImplementedError("Implement this in your test")

    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(self, a: float, b: float) -> bool:
        return int(self.HLS_OP_FN(a, b))  # int to have visually shorter output

    @override
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

            res = self.HLS_OP_FN(a, b)
            assert res._dtype is BIT, (res._dtype, res)
            hls.write(res, self.data_out, mayBecomeFlushable=False)

    def hwImpl(self) -> None:
        _FixpBinOpTestModule.hwImpl(self)


class _FixpCastOpTestModule(HwModule):

    @override
    def hwConfig(self) -> None:
        self.T = HwParam(HFixedPointQ(2, 6))
        self.CLK_FREQ = HwParam(int(20e6))
        self.T_OUT = HwParam(HFixedPointQ(2, 3))

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        self.data_in = HwIOStructRdVld()
        t = HBits(self.T.bit_length())  # can not currently use HFixedPointQ for IO of the module
        self.data_in.T = t

        self.data_out = HwIOStructRdVld()._m()
        self.data_out.T = HBits(self.T_OUT.bit_length())

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        T = self.T
        T_OUT = self.T_OUT
        T_OUT_RAW = self.data_out.T
        while b1:
            inp = hls.read(self.data_in).data
            a = inp._reinterpret_cast(T)
            aCasted = a._explicit_cast(T_OUT)
            aOutRaw = aCasted._reinterpret_cast(T_OUT_RAW)
            hls.write(aOutRaw, self.data_out, mayBecomeFlushable=False)

    def HLS_OP_FN(self, a: AnyHBitsValue) -> AnyHBitsValue:
        return fixp_resize(a, self.T, self.T_OUT)

    @hlsModelProps(returnsPyValue=True, returnsOutValue=True)
    def model(self, data_in: float) -> float:
        FP_TY = self.T
        FP_TY_OUT = self.T_OUT
        res = fixp_resize_py(data_in, FP_TY_OUT.signed, FP_TY.int_bit_length, FP_TY.frac_bit_length,
                             FP_TY_OUT.int_bit_length, FP_TY_OUT.frac_bit_length,
                             FP_TY_OUT.rounding, FP_TY_OUT.saturation)
        return res

    @override
    def hwImpl(self) -> None:
        _FixpUnOpTestModule.hwImpl(self)
