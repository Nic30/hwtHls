#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import split_to_segments, Concat
from hwt.hdl.commonConstants import b0
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.structValBase import HStructRtlSignalBase
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwParam import HwParam
from hwt.mathAutoExt import addAutoExt, addShifted
from hwt.pyUtils.arrayQuery import balanced_reduce
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragmaPreproc import PyBytecodeInPreproc
from tests.math.componentGenerators._mul.mulUtils import PipelinedMultiplier, \
    iter_antidiagonal_item_indexes


class PipelinedMultiplierChained(_BaseALU1HwModule):
    """
    Vedic Multiplier Urdhva Tiryakbhyam sutra "Vertically & Crosswise method"
    """

    @override
    def hwConfig(self):
        PipelinedMultiplier.hwConfig(self)
        self.CHECK_FOR_INEFFICIENCY = False
        self.RHS_IS_LHS = HwParam(False)

    @override
    def hwDeclr(self):
        PipelinedMultiplier.hwDeclr(self)

    def aluFn(self, inp: HStructRtlSignalBase, isSim:bool=False) -> HBitsRtlSignal:
        """
        This implementation uses multipliers in sequence which allows adders
        to be done after each multiplication which formats expression to 
        multiply accumulate (MAC, a * b + c) format which can be mapped to DSP blocks
        more efficiently
        .. code-block:: verilog
            // unsigned ul 32x32->64b
            wire [15:0] al = a[15:0];
            wire [15:0] ah = a[31:16];
            wire [15:0] bl = b[15:0];
            wire [15:0] bh = b[31:16];
    
            wire [32:0] al_bl = al * bl + 0;
            wire [32:0] ah_bl = ah * bl + { 16'h0000, al_bl[31:16] };
            wire [32:0] al_bh = al * bh + ah_bl[31:0];
            wire [32:0] ah_bh = ah * bh + { 15'h0000, al_bh[32:16] };
    
            assign prod[63:32] = ah_bh[31:0];
            assign prod[31:16] = al_bh[15:0];
            assign prod[15:0] = al_bl[15:0];
        :note: inp. and out bitwidth/DSPs: 32/4, 64/11, 128/38
        """
        isSigned = self.T.signed
        partWidth = min(self.MAX_MUL_LHS_WIDTH, self.MAX_MUL_RHS_WIDTH)
        # partial multiplications are always performed in unsigned
        a = [v._cast_sign(False) for v in split_to_segments(inp.a, partWidth)]
        b = [v._cast_sign(False) for v in split_to_segments(inp.b, partWidth)]
        assert len(a) > 1 or len(b) > 1, "This is just a simple multiply this module is not necessary"

        # perform matrix multiplication and sum shifted terms to obtain final result
        resultWidth = self.T.bit_length()
        resultBits: list[AnyHBitsValue] = []  # lower bits first
        prevAntidiagonalSumHiBits = None
        if isSim:
            preProc = lambda x: x
        else:
            preProc = PyBytecodeInPreproc

        RHS_IS_LHS = self.RHS_IS_LHS
        #print("RHS_IS_LHS", RHS_IS_LHS, len(a), len(b))
        #print(list(iter_antidiagonal_item_indexes(len(a), len(b))))
        for antiDiagonalIndex, antiDiagonalIndexes in enumerate(iter_antidiagonal_item_indexes(len(a), len(b))):
            # example iteration scheme
            # 0 1 3
            # 2 4 6
            # 5 7 8
            assert antiDiagonalIndexes
            antiDiagonalIndexes: list[tuple[int, int]]

            inResultOffset = max(0, antiDiagonalIndex - 1) * partWidth
            if inResultOffset >= resultWidth:
                # ignore remaining members of mul/sum as they are computing
                # bits which will not be used by the result
                #print("Breaking because of offset ", inResultOffset, resultWidth)
                break

#            print("antiDiagonalIndexes", antiDiagonalIndex, antiDiagonalIndexes)    
            antidiagonal = []
            for diagItemIndex, (aIndex, bIndex) in enumerate(antiDiagonalIndexes):
                aPart = preProc(a[aIndex]._zext(2 * partWidth))
                aPart._name = f"aPart{aIndex:d}"
                aPart._hasGenericName = False
                bPart = preProc(b[bIndex]._zext(2 * partWidth))
                bPart._name = f"bPart{bIndex:d}"
                bPart._hasGenericName = False
                prodPart = preProc(aPart * bPart)
                prodPart._name = f"prodPart_{aIndex:d}_{bIndex:d}"
                prodPart._hasGenericName = False
                # print(RHS_IS_LHS, diagItemIndex, aIndex, bIndex)
                if RHS_IS_LHS:
                    # :note: if a is b we need to compute only upper right triangle
                    #        and multiply items above diagonal by 2, because multiplication is commutative
                    # :note: the matrix of products is actually composed of lines parallel with antidiagonal
                    #        (from right top to bottom left)
                    #        The first line has just 1 item (0, 0) and it represents bits 0 to segment width
                    #        bits of result
                    #  i0 +                                  # 2*SW width, lower SW bits to result, upper SW bits to next addition
                    #  (i1 << SW) + (i2 << SW)               # 2*SW + log2(3), upper SW bits from prev row + i1 + i2, lower SW bits to result
                    #                                        # upper bits to next layer of adders for next multipliers
                    #  ...
                    # :note: if this is a x**2 case we can omit left triangle and simply multiply all items above diagonal by 2
                    diagHalf = (diagItemIndex + 1) // 2
                    if diagItemIndex < diagHalf:
                        prodPart = prodPart._concat(b0)  # prodPart *= 2

                antidiagonal.append(prodPart)
                if RHS_IS_LHS and diagItemIndex == diagHalf:
                    break


            if prevAntidiagonalSumHiBits is not None:
                # append upper bits from last level sum
                antidiagonal.append(prevAntidiagonalSumHiBits)

            # sum all members of diagonal without any scale, auto extend to prevent overflows
            antidiagonalSum = preProc(balanced_reduce(antidiagonal, addAutoExt))
            assert antidiagonalSum._dtype.bit_length() > partWidth

            # extract lower bits for result
            # :note: the parts may be from different times in pipeline for now, the dealy is matched at the end of this fn.
            resultBits.append(antidiagonalSum[partWidth:])
            # pass upper bits to next level
            prevAntidiagonalSumHiBits = preProc(antidiagonalSum[:partWidth])

        resultBits.append(prevAntidiagonalSumHiBits)
        result = Concat(*reversed(resultBits))._cast_sign(isSigned)
        if isSigned:
            # in signed multiplication the lower half bits of result are same as for unsigned
            # there are two metods how to impement this.
            # 1. abs of inputs, compute usigned multiply, negate is input sign did not match
            # 2. fix sign afterwards
            #    .. code-block:: python
            #        a_hi = a.msb().sext(partWidth)
            #        b_hi = b.msb().sext(partWidth)
            #        - (a_hi * b_lo) << off0
            #        - (b_hi * a_lo) << off1
            #        #+ (a_hi * b_hi) << off2 # fixes only top 2 bits of the result
            #        ==
            #        - (-b_lo << off0) if a.msb() else 0
            #        - (-a_lo << off1) if b.msb() else 0
            #        #+ (-1 << off2) if a.msb() != b.msb() else 0
            #        ==
            #        + (b_lo << off0) if a.msb() else 0
            #        + (a_lo << off1) if b.msb() else 0
            #        #+ (-1 << off2) if a.msb() != b.msb() else 0
            offB = partWidth * len(b)
            offA = partWidth * len(a)
            # offAB = partWidth * (len(a) + len(b))
            aMsb = inp.a.getMsb()
            bMsb = inp.b.getMsb()
            w = result._dtype.bit_length()
            result = addShifted(result, aMsb._ternary(inp.b, inp.b._dtype.from_py(0)), offB, w)
            result = addShifted(result, bMsb._ternary(inp.a, inp.a._dtype.from_py(0)), offA, w)
            # result = addShifted(result, (aMsb ^ bMsb)._sext(2)._cast_sign(True), offAB, w)

        return result[resultWidth:]._reinterpret_cast(self.T)


if __name__ == "__main__":
    from hwt.hdl.types.bits import HBits
    from hwt.serializer.verilog import VerilogSerializer
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast

    m = PipelinedMultiplierChained()
    m.T = HBits(32, signed=False)
    m.RHS_IS_LHS = False
    m.IN_CHANNEL_TYPE = m.OUT_CHANNEL_TYPE = HwIOStruct
    m.CLK_FREQ = int(100e6)
    # m.T = HBits(64)
    m.MAX_MUL_LHS_WIDTH = 16
    m.MAX_MUL_RHS_WIDTH = 16
    p = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                   # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED]
    )
    #installFpComponentGenerators(p)
    print(to_rtl_str(m, serializer_cls=VerilogSerializer, target_platform=p))  # {HlsDebugBundle.DBG_23_arch}
