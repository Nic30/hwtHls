from typing import Callable, Union, Optional

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragma import _PyBytecodeLoopPragma
from hwtHls.frontend.pragmaFunction import PyBytecodeSkipPass
from hwtHls.frontend.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from tests.passTestInjectorForDInDOutHwModule import hlsModelProps


@hlsBytecode
def _divCastToUnsigned(dividend: RtlSignal, divisor: RtlSignal, isSigned: Union[RtlSignal, bool]):
    """
    An utility function which cast signed operands to unsigned before division
    before division algorithm is for unsigned only.
    It also computes invertQuotient and invertRemainder which
    should be used to correct result if inputs were signed.
    """
    PyBytecodeBlockLabel("_divCastToUnsigned")
    width = dividend._dtype.bit_length()
    if isinstance(isSigned, bool):
        isSigned = BIT.from_py(isSigned)
    invertQuotient = isSigned & (dividend[width - 1] != divisor[width - 1]) & (divisor != 0)
    invertRemainder = isSigned & dividend[width - 1]

    if isSigned & dividend[width - 1]:
        dividend = -dividend

    if isSigned & divisor[width - 1]:
        divisor = -divisor

    return dividend, divisor, invertQuotient, invertRemainder

# NR https://hardwaredescriptions.com/conquer-the-divide/


@hlsBytecode
def divremRestoring(dividend: HBitsRtlSignal,
                    divisor: HBitsRtlSignal,
                    isSigned: Union[HBitsRtlSignal, bool],
                    loopPragmaGetter: Callable[[], _PyBytecodeLoopPragma]=lambda: None,
                    dbgNoSplitSlices:bool=True):
    """
    Restoring integer division, quotient = dividend // divisor, remainder = dividend%divisor 

    :param dbgSplitSlices: debug option which controls SplitSlices pass
        (which does not improve anything but triggers many other optimizations)

    based on https://github.com/ultraembedded/riscv/blob/master/core/riscv/riscv_divider.v
    https://en.wikipedia.org/wiki/Division_algorithm
    https://projectf.io/posts/division-in-verilog/
    """
    assert dividend._dtype == divisor._dtype
    t = dividend._dtype
    width = t.bit_length()

    dividend, divisor, invertQuotient, invertRemainder = PyBytecodeInline(_divCastToUnsigned)(dividend, divisor, isSigned)

    zeroPad = HBits(width - 1).from_py(0)
    quotient = t.from_py(0)
    divisorTmp = Concat(divisor, zeroPad)
    qMask = t.from_py(1 << (width - 1))
    if dbgNoSplitSlices:
        PyBytecodeNoSplitSlices(divisorTmp)

    while qMask != 0:
        PyBytecodeBlockLabel("divremRestoring.divLoop")
        if divisorTmp <= Concat(zeroPad, dividend):
            dividend -= divisorTmp[width:]
            quotient |= qMask

        if dbgNoSplitSlices:
            PyBytecodeNoSplitSlices(qMask)
            PyBytecodeNoSplitSlices(divisorTmp)
            PyBytecodeNoSplitSlices(quotient)

        divisorTmp >>= 1
        qMask >>= 1
        loopPragmaGetter()

    PyBytecodeBlockLabel("divremRestoring.signFinalize")
    if invertQuotient:
        quotient = -quotient

    remainder = dividend
    if invertRemainder:
        remainder = -remainder

    PyBytecodeBlockLabel("divremRestoring.return")
    return (quotient, remainder)


@serializeParamsUniq
class DivRemHwModule(_BaseALU1HwModule):
    """
    Universal HwModule wrapper around integer division function.
    :note: used also to compute udiv/sdiv/urem/srem (rem/mod)
    """
    FN = staticmethod(divremRestoring)

    @override
    def hwConfig(self) -> None:
        _BaseALU1HwModule.hwConfig(self)
        self.MAIN_FN_META = PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass",
                                                "hwtHls::SelectPruningPass"])
        self._inTy: Optional[HStruct] = None
        self._outTy: Optional[HStruct] = None

    def _getDataInOutTypes(self):
        inT = self._inTy
        if inT:
            return inT, self._outTy
        T = self.T
        assert isinstance(T, HBits), T
        self.HAS_RUNTIME_SIGN = T.signed is None

        inT = HStruct(
            (T, "dividend"),
            (T, "divisor"),
            *(((BIT, "signed"),) if self.HAS_RUNTIME_SIGN else ()),
        )
        outT = HStruct(
            (T, "quotient"),
            (T, "remainder")
        )
        self._inTy = inT
        self._outTy = outT
        return inT, outT

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        inT, outT = self._getDataInOutTypes()
        self._addDataInDataOut(inT, outT)

    def _getMaxIterationCount(self):
        return self.T.bit_length()

    @staticmethod
    @hlsModelProps(returnsPyValue=True, returnsOutValue=True, inputArgsAreStructMembers=True)
    def model(dividend: int, divisor: int, isSigned:bool) -> tuple[int, int]:
        if isSigned or dividend < 0 or divisor < 0:
            raise NotImplementedError()

        quotient = dividend // divisor
        remainder = dividend % divisor
        return quotient, remainder

    @hlsBytecode
    def aluFn(self, inp):
        res = PyBytecodeInline(self.FN)(inp.dividend, inp.divisor,
                                        inp.signed if self.HAS_RUNTIME_SIGN else self.T.signed,
                                        loopPragmaGetter=self._getLoopMeta)
        outT = self._getTypeOfIo(self.data_out)
        resTmp = outT.from_py(None)
        resTmp.quotient = res[0]
        resTmp.remainder = res[1]
        return resTmp
