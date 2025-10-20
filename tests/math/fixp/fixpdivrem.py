#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Callable, Union

from hwt.hdl.commonConstants import b0, b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.code import zext, shlIn
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.hwrange import hwrange
from hwtHls.frontend.pragma import _PyBytecodeLoopPragma
from hwtHls.frontend.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline, \
    PyBytecodeBlockLabel
from hwtHls.llvm.llvmIr import HFloatTmpConfig, HFloatTmpRounding
from tests.math.componentGenerators._div.divRestoring import _divCastToUnsigned, \
    DivRemHwModule
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.componentGenerators._genericHwModules import _FpBinOpAluHwModule


@hlsBytecode
def fixpDivremRestoring(t:HFixedPointQ,
                     dividend: HBitsRtlSignal,
                     divisor: HBitsRtlSignal,
                     isSigned: Union[bool, HBitsRtlSignal],
                     loopPragmaGetter: Callable[[], _PyBytecodeLoopPragma]=lambda: None,
                     dbgNoSplitSlices:bool=True):
    """
    Fixed point division (longdiv algorithm) with support for signed/unsigned and frac_bit_length=0 types
    
    :attention: division of fixed point numbers can overflow, 
        e.g. 1/0.25 both representable at uQ1.2, but the result 4 has is uQ3.2
    :attention: dividend and divisor are raw HBits holding value for HFixedPointQ,
        HFixedPointQ is not used for inputs as only user of this function in the time
        of writing would need cast args and args are casted immediately to raw HBits 
        on the beginning of this function.
    This practically is just an integer division, but the type must be extended
    :: code-block: c
        // https://en.wikipedia.org/wiki/Q_(number_format)
        int16_t q_div(int16_t a, int16_t b) {
            int32_t temp = (int32_t)a << Q;
            if (a.getMsb() == b.getMsb()) {
                temp += (b >> 1);
            } else {
                temp -= (b >> 1);
            }
            return (int16_t)(temp / b);
        }
    """
    assert dividend._dtype == divisor._dtype
    flatT = dividend._dtype
    assert flatT.bit_length() == t.bit_length()

    width = t.bit_length()
    fracWidth = t.frac_bit_length

    dividend, divisor, invertQuotient, invertRemainder = PyBytecodeInline(_divCastToUnsigned)(dividend, divisor, isSigned)

    ITERATION_CNT = width + fracWidth
    cfg: HFloatTmpConfig = t.getHFloatTmpConfig()
    roundingIsJustTruncat = cfg.rounding == HFloatTmpRounding.ROUND_FLOOR or (
        cfg.rounding == HFloatTmpRounding.ROUND_DOWN and isinstance(isSigned, bool) and not isSigned)
    if not roundingIsJustTruncat:
        ITERATION_CNT += 1

    acc = zext(dividend.getMsb(), width + 1)
    quotient = shlIn(dividend, b0)
    if dbgNoSplitSlices:
        PyBytecodeNoSplitSlices(acc)

    remainder = flatT.from_py(None)
    overflow = b0
    for i in hwrange(ITERATION_CNT):
        # division algorithm iteration
        quoNewLsb = BIT.from_py(None)
        accNext = acc._dtype.from_py(None)
        if acc < zext(divisor, width + 1):
            accNext = acc
            quoNewLsb = b0
        else:
            accNext = acc - zext(divisor, width + 1)
            quoNewLsb = b1
        accNext = shlIn(accNext, quotient.getMsb())

        if i._eq(ITERATION_CNT - 1) & (not roundingIsJustTruncat):
            if cfg.rounding == HFloatTmpRounding.ROUND_HALF_EVEN:
                if quoNewLsb:  # next digit is 1, so consider rounding
                    # round up if quotient is odd or remainder is non-zero
                    if quotient[0] | (accNext[:1] != 0):
                        quotient += 1
            else:
                raise NotImplementedError()
        else:
            quotient = shlIn(quotient, quoNewLsb)
            acc = accNext
            if i._eq(width - 1) & (t.frac_bit_length != 0) & (quotient[width:width - t.frac_bit_length] != 0):
                overflow = 1
                # :note: do not break to have stable latency
        if i._eq(width - 1):
            # capture remainder before we start to by fractions of divider
            remainder = acc[:1]

        loopPragmaGetter()

    PyBytecodeBlockLabel("idivremRestoring.signFinalize")
    if invertQuotient:
        quotient = -quotient

    if invertRemainder:
        remainder = -remainder

    PyBytecodeBlockLabel("idivremRestoring.return")
    return (quotient, remainder, overflow)


@serializeParamsUniq
class FixpDivRemHwModule(DivRemHwModule):
    """
    Universal HwModule wrapper around integer division function.
    :note: used also to compute ufixpdiv/sfixpdiv/ufixprem/sfixprem (rem/mod)
    :see: :class:`tests.math.componentGenerators.divrem.DivRemHwModule`
    """

    @override
    def hwConfig(self) -> None:
        DivRemHwModule.hwConfig(self)
        self.FN = fixpDivremRestoring

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        t = HBits(self.T.bit_length())
        self.HAS_RUNTIME_SIGN = False
        self.IS_SIGNED = self.T.signed
        inT = HStruct(
            (t, "dividend"),
            (t, "divisor"),
        )
        outT = HStruct(
            (t, "quotient"),
            (t, "remainder")
        )
        _FpBinOpAluHwModule._addDataInDataOut(self, inT, outT)

    @hlsBytecode
    def aluFn(self, inp):
        res = PyBytecodeInline(self.FN)(self.T,
                                        inp.dividend, inp.divisor,
                                        inp.signed if self.HAS_RUNTIME_SIGN else self.T.signed,
                                        loopPragmaGetter=self._getLoopMeta,
                                        dbgNoSplitSlices=True)
        outT = self._getTypeOfIo(self.data_out)
        resTmp = outT.from_py(None)
        resTmp.quotient = res[0]
        resTmp.remainder = res[1]
        return resTmp

    @override
    def _getMaxIterationCount(self):
        return self._getMaxIterationCountForTy(self.T)

    @staticmethod
    def _getMaxIterationCountForTy(t: HFixedPointQ) -> int:
        ITERATION_CNT = t.int_bit_length + 2 * t.frac_bit_length
        cfg: HFloatTmpConfig = t.getHFloatTmpConfig()
        roundingIsJustTruncat = cfg.rounding == HFloatTmpRounding.ROUND_FLOOR or (
            cfg.rounding == HFloatTmpRounding.ROUND_DOWN and isinstance(t.signed, bool) and not t.signed)
        if not roundingIsJustTruncat:
            ITERATION_CNT += 1
        return ITERATION_CNT


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
    # from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = FixpDivRemHwModule()
    m.T = HFixedPointQ(2, 4, signed=False)
    # m.UNROLL_FACTOR = 1
    m.CLK_FREQ = int(1e6)
    m.IN_CHANNEL_TYPE = HwIOStructRdVld
    print(to_rtl_str(m, target_platform=Artix7Fast(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[
        #   LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        #   LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        # ]
    )))

