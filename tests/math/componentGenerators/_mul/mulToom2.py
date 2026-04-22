#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.structValBase import HStructRtlSignalBase
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.mathAutoExt import addShifted, addAutoExt, subAutoExt
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from tests.math.componentGenerators._mul.mulUtils import PipelinedMultiplier


class PipelinedMultiplierToom2(_BaseALU1HwModule):
    """
    Toom-Cook Toom-2 is the same as Karatsuba

    https://blog.lambdaclass.com/weird-ways-to-multiply-really-fast-with-karatsuba-toom-cook-and-fourier/
    https://github.com/blavignac/projet_long_g2/blob/main/code_digilent_nexys4/toom_cook_2.py
    10.1145/1277548.1277552
    https://github.com/FlorentCLMichel/karatsuba_multiplication_verilog/blob/main/src/karatsuba_mul.v
    https://github.com/Anagrimonia/toom-cook-3-algorithm
    https://github.com/DreamPast/ulbn/blob/master/ulbn.c#L1539
    https://github.com/libtom/libtommath/blob/develop/s_mp_mul_karatsuba.c
    """

    @override
    def hwConfig(self):
        PipelinedMultiplier.hwConfig(self)
        self.CHECK_FOR_INEFFICIENCY = False

    @override
    def hwDeclr(self):
        PipelinedMultiplier.hwDeclr(self)

    def aluFn(self, inp: HStructRtlSignalBase, isSim:bool=False) -> HBitsRtlSignal:
        a: AnyHBitsValue = inp.a
        b: AnyHBitsValue = inp.b

        # :note: sign affect only how values are exteded in final adders
        isSigned = a._dtype.signed
        assert a._dtype == b._dtype
        width = a._dtype.bit_length()
        assert width > self.MAX_MUL_LHS_WIDTH or width > self.MAX_MUL_RHS_WIDTH, \
            "This alg. should be only used for operand widths which require spliting"

        # width1 = width // 2  # width of a_1 and b_1
        width2 = (width + 1) // 2  # width of a_0 and b_0
        # width3 = width2 + 1  # width of a_1+b_1

        a0 = a[width2:]._cast_sign(False)
        b0 = b[width2:]._cast_sign(False)
        a1 = a[:width2]._cast_sign(False)
        b1 = b[:width2]._cast_sign(False)

        # zext to 2* width2 beacause hwt mul result has same width as operands
        z0 = a0._zext(2 * width2) * b0._zext(2 * width2)  # 2*partWidth
        z1 = addAutoExt(a0, a1)._ext(2 * width2 + 2) * \
             addAutoExt(b0, b1)._ext(2 * width2 + 2)  # 2*(partWidth + 1)
        z2 = a1._zext(2 * width2) * b1._zext(2 * width2)  # 2*halfWidth
        # tmpSumWidth = 2 * partWidth + 1
        # z1 - z2 - z0
        # c1 = zext(zext(z1, tmpSumWidth) - zext(z2, tmpSumWidth), tmpSumWidth + 1) - zext(z0, tmpSumWidth + 1)
        c1 = subAutoExt(subAutoExt(z1._cast_sign(isSigned), z2._cast_sign(isSigned)), z0._cast_sign(isSigned))
        # (z2 << (2*m2)) + ((z1 - z2 - z0) << m2) + z0
        c0_1 = addShifted(z0._cast_sign(isSigned), c1, width2, 2 * width)
        return addShifted(c0_1, z2._cast_sign(isSigned), 2 * width, self.T.bit_length())._reinterpret_cast(self.T)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # from hwtHls.llvm.llvmIr import LlvmCompilationBundle
    from hwt.serializer.verilog import VerilogSerializer
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from hwtLib.types.ctypes import uint64_t, uint32_t
    #    :note: inp. bitwidth/DSPs/LUTs: 16/4/16, 32/4/31, 64/10/234, 128//
    #    :note: inp. bitwidth/DSPs: 16/3, 32/4, 64/11, 128/38
    m = PipelinedMultiplierToom2()
    m.T = HBits(64, signed=True)
    m.MAX_MUL_LHS_WIDTH = m.MAX_MUL_RHS_WIDTH = 16
    m.CLK_FREQ = int(100e6)
    m.IN_CHANNEL_TYPE = HwIOStruct
    m.OUT_CHANNEL_TYPE = HwIOStruct
    platform = Artix7Fast(
       # debugFilter={HlsDebugBundle.DBG_4_4_arch,},
       debugFilter=HlsDebugBundle.ALL_RELIABLE,
       llvmCliArgs=[
           # LLVM_CLI_COMMON_OPTS.debugOnly("legalizer"),
           # LLVM_CLI_COMMON_OPTS.TIME_PASSES,
           # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
           # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
           # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
           # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
           ]
       )
    print(to_rtl_str(m, serializer_cls=VerilogSerializer, target_platform=platform))  #
