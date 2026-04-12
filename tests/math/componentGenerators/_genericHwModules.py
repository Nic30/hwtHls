from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from tests.math.fixp.fixpTypes import HFixedPointQ


class _FpUnOpAluHwModule(_BaseALU1HwModule):
    """
    Universal HwModule wrapper around floating point unary operator function.
    """

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        t = self.T
        if isinstance(t, HFixedPointQ):
            # HFixedPointQ not currently supported for io
            t = HBits(t.bit_length())

        self._addDataInDataOut(t, t)

    @override
    @hlsBytecode
    def aluFn(self, inp):
        return PyBytecodeInline(self.FN)(
            inp._reinterpret_cast(self.T),
            loopPragmaGetter=self._getLoopMeta)._reinterpret_cast(self._getTypeOfIo(self.data_out))


@serializeParamsUniq
class _FpBinOpAluHwModule(_FpUnOpAluHwModule):
    """
    Universal HwModule wrapper around floating point binary operator function.
    """

    @override
    def hwDeclr(self) -> None:
        assert self.FN is not NotImplemented
        addClkRstn(self)

        t = self.T
        assert t is not None, self
        if isinstance(t, HFixedPointQ):
            # HFixedPointQ not currently supported for io
            t = HBits(t.bit_length())

        inT = HStruct(
            (t, "a"),
            (t, "b"),
        )
        self._addDataInDataOut(inT, t)

    @override
    @hlsBytecode
    def aluFn(self, inp):
        if self.FN.__code__.co_kwonlyargcount == 0:
            assert self.UNROLL_FACTOR == 1
            return PyBytecodeInline(self.FN)(inp.a._reinterpret_cast(self.T),
                                             inp.b._reinterpret_cast(self.T))
        else:
            return PyBytecodeInline(self.FN)(inp.a._reinterpret_cast(self.T),
                                             inp.b._reinterpret_cast(self.T),
                                             loopPragmaGetter=self._getLoopMeta)

