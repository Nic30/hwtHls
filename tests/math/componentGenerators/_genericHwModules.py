from types import MethodType
from typing import Union, Callable

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hdl.types.structValBase import HStructConstBase
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from tests.math.fixp.fixpTypes import HFixedPointQ


class _FpAlu1HwModule(_BaseALU1HwModule):
    """
    Universal HwModule wrapper around floating point unary operator function.
    :attention: do not forget to override _getMaxIterationCount if necessary
    """
    CHECK_UNROLL_FACTOR = True

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        t = self.T
        if isinstance(t, HFixedPointQ):
            # HFixedPointQ not currently supported for io
            t = HBits(t.bit_length())

        self._addDataInDataOut(t, t)

    def _doesSupport_loopPragmaGetter(self, fn: Union[MethodType, Callable]):
        # handle cases of static methods and alike
        fn = getattr(fn, "__func__", fn)
        return "loopPragmaGetter" in fn.__code__.co_varnames[:fn.__code__.co_argcount]
        return fn.__code__.co_kwonlyargcount != 0

    def FN(self, a, loopPragmaGetter=None):
        raise NotImplementedError("Implement this method in child class", self)

    @override
    @hlsBytecode
    def aluFn(self, inp: HStructConstBase):
        outT = self._getTypeOfIo(self.data_out)
        inpAsT = inp._reinterpret_cast(self.T)
        if self._doesSupport_loopPragmaGetter(self.FN):
            return PyBytecodeInline(self.FN)(
                inpAsT,
                loopPragmaGetter=self._getLoopMeta)\
                ._reinterpret_cast(outT)
        else:
            assert not self.CHECK_UNROLL_FACTOR or self.UNROLL_FACTOR == 1, ("does not support unrolling because function does not have loopPragmaGetter kwarg", self, self.FN)
            return PyBytecodeInline(self.FN)(inpAsT)\
                    ._reinterpret_cast(outT)


class _FpAlu2HwModule(_BaseALU1HwModule):
    """
    Universal HwModule wrapper around floating point binary operator function.
    :attention: do not forget to override _getMaxIterationCount if necessary
    """
    CHECK_UNROLL_FACTOR = True

    @override
    def hwDeclr(self) -> None:
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

    def _doesSupport_loopPragmaGetter(self, fn: Union[MethodType, Callable]):
        return _FpAlu1HwModule._doesSupport_loopPragmaGetter(self, fn)

    def FN(self, a, b, loopPragmaGetter=None):
        raise NotImplementedError("Implement this method in child class", self)

    @override
    @hlsBytecode
    def aluFn(self, inp: HStructConstBase):
        a = inp.a._reinterpret_cast(self.T)
        b = inp.b._reinterpret_cast(self.T)
        if self._doesSupport_loopPragmaGetter(self.FN):
            return PyBytecodeInline(self.FN)(a, b, loopPragmaGetter=self._getLoopMeta)
        else:
            assert not self.CHECK_UNROLL_FACTOR or self.UNROLL_FACTOR == 1, ("does not support unrolling because function does not have loopPragmaGetter kwarg", self, self.FN)
            return PyBytecodeInline(self.FN)(a, b)

