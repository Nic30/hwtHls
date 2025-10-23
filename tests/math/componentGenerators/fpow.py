#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from tests.math.componentGenerators._llvmIrInterpretFP import ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat
from tests.math.componentGenerators.ftan import TanCordicDivHwModule, \
    ComponentGeneratorFTAN
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import log2, exp2, OP_FPOW


# https://www.geeksforgeeks.org/exponential-squaring-fast-modulo-multiplication/
# def exponentiation(bas: int, exp: int):
#    if (exp == 0):
#        return 1
#    if (exp == 1):
#        return bas
#
#    t = exponentiation(bas, exp // 2);
#    t = t * t
#
#    if exp % 2 == 0:
#        return t
#
#    else:
#        return bas * t
# https://stackoverflow.com/questions/64941736/efficient-implementation-of-fixed-point-power-pow-function-with-argument-const
# https://gist.github.com/Madsy/1088393#file-gistfile1-c-L163
# https://forums.developer.nvidia.com/t/a-more-accurate-and-faster-implementation-of-powf/48743/3
# pow(x,y) == exp(y * log(x))
# def exponentiation(base: int, exp: int):
#     result = 1
#     while exp > 0:
#         if exp % 2 == 1:
#             result *= base
#         base *= base
#         exp //= 2
#     return result
@serializeParamsUniq
class PowHwModule(TanCordicDivHwModule):

    def hwDeclr(self) -> None:
        addClkRstn(self)
        T = self.T
        assert T.rounding == HFloatTmpRounding.ROUND_FLOOR, (T.rounding, "rounding on input should be disabled (only output is rounded)")
        assert T.saturation == HFloatTmpSaturation.SATURATE_NONE, T.rounding

        t = HBits(T.bit_length())
        _BaseALU1HwModule._addDataInDataOut(self,
                                            HStruct(
                                                (t, "a"),
                                                (t, "b"),
                                            ),
                                            t
                                            )

    @hlsBytecode
    def aluFn(self, _inp: HBitsRtlSignal) -> HBitsRtlSignal:
        T = self.T
        a = _inp.a._reinterpret_cast(T)._auto_cast(HFloatTmp)
        b = _inp.b._reinterpret_cast(T)._auto_cast(HFloatTmp)
        # :note: higher precision needs to be used internally to achieve nominal precision of output
        #     Pasca, Bogdan. “Floating-Point Exponentiation Units for Reconfigurable Computing.
        #     ” ACM Transactions on Reconfigurable Technology and Systems, Association for Computing Machinery (ACM), 2013.
        # pow(a,b) == exp(b * log(a))
        # powVal = exp(b * log(a))
        powVal = exp2(b * log2(a))
        return powVal._auto_cast(T)


class ComponentGeneratorFPOW_hwtHlsFpIntrinsic(ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat):

    @override
    @staticmethod
    def evalFn(v: float, p:float) -> float:
        return math.pow(v, p)


class ComponentGeneratorFPOW(ComponentGeneratorFTAN):
    INPUT_CNT = 2
    FP_HWMODULE_CLS = PowHwModule
    opDef = OP_FPOW


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators
    from tests.math.fixp.fixpTypes import HFixedPointQ

    m = PowHwModule()
    m.T = HFixedPointQ(10, 14, rounding=HFloatTmpRounding.ROUND_FLOOR, saturation=HFloatTmpSaturation.SATURATE_NONE)
    m.CLK_FREQ = int(10e6)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                         llvmCliArgs=[
                             # LLVM_CLI_COMMON_OPTS.filterPrintFuncs(["FixpCosSinCordic.mainThread",]),
                             # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                             # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_ARGUMENTS,
                             # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                             # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                         ]
                         )
    installMathLibComponentGenerators(platform, optThroughputVsArea=1.0, MAX_TABLE_ADDR_WIDTH=10)
    print(to_rtl_str(m, target_platform=platform))

    # test_values = [1., 2., 3., 4., 10., 0, 0.25, 0.75, 0.125, -1., -2., -3., -10. ]
    # for a in [1., 2., 3., 0.2, ]:
    #    for b in test_values:
    #        powVal = math.pow(a, b)
    #        powWithEVal = math.exp(b * math.log(a))
    #        powWith2Val = math.pow(2., b * math.log2(a))
    #        print(powVal, powWithEVal, powWith2Val)
    #
