#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Type

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import split_to_segments
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b0 as b0_const
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.structValBase import HStructRtlSignalBase
from hwt.hwIOs.hwIOStruct import HwIOStructVld, HwIOStructRdVld, HwIOStruct
from hwt.hwParam import HwParam
from hwt.mathAutoExt import addAutoExt, \
    addAutoExtMany, subAutoExt, addShiftedMany, mulFullWidth
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtLib.types.ctypes import uint64_t
from tests.math.componentGenerators._mul.mulUtils import PipelinedMultiplier


class PipelinedMultiplierToom2_5(_BaseALU1HwModule):
    """
    Multiply two integers A and B using Toom-2.5 algorithm.
    * Toom-2.5 is a variant of Toom-Cook algorithm for operands with operands of non-equal size. 
    (A is split to 3 parts, B to 2 parts)
    :note: width of operands must be 3:2 otherwise operands are internally extended
    
    Bodrato, Marco and Alberto Zanoni. "What About Toom-Cook Matrices Optimality ?" (2006). https://api.semanticscholar.org/CorpusID:14057309
    """

    @override
    def hwConfig(self):
        self.CLK_FREQ: int = HwParam(int(100e6))
        self.T: HBits = HwParam(uint64_t)
        self.T_LHS: Optional[HBits] = HwParam(None)
        self.T_RHS: Optional[HBits] = HwParam(None)
        self.UNROLL_FACTOR: int = HwParam(1)
        self.MAIN_FN_META: int = HwParam(None)
        self.IN_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructVld)
        self.OUT_CHANNEL_TYPE: Type[HwIOStructRdVld] = HwParam(HwIOStructRdVld)
        self.CHECK_FOR_INEFFICIENCY = HwParam(True)

    @override
    def hwDeclr(self):
        PipelinedMultiplier.hwDeclr(self)

        if self.CHECK_FOR_INEFFICIENCY:
            assert self.T_LHS is not None
            assert self.T_RHS is not None
            _, partWidth, _, _ = self._getPartWidth(self.T_LHS, self.T_RHS)
            assert self.T_LHS.bit_length() == 3 * partWidth, (self.T_RHS.bit_length(), partWidth)
            assert self.T_RHS.bit_length() == 2 * partWidth, (self.T_LHS.bit_length(), partWidth)

    @staticmethod
    def _getPartWidth(aType: HBits, bType: HBits):
        # Determine sizes for splitting
        aWidth = aType.bit_length()
        bWidth = bType.bit_length()
        isSigned = aType.signed or bType.signed
        partaWidth = (aWidth + 2) // 3
        partbWidth = (bWidth + 1) // 2
        partWidth = max(partaWidth, partbWidth)
        return isSigned, partWidth, aWidth, bWidth

    @staticmethod
    @hwt_expr_producer
    def _splitToParts(a: AnyHBitsValue, b: AnyHBitsValue, partWidth:int):
        # :note: only top part remains signed
        # :note: sign extend if operand is signed and width is not multiple of partWidth
        aParts = [
            v
            if isLast else
            v._cast_sign(False)
            for isLast, v in iter_with_last(split_to_segments(a, partWidth, extendLast=True))
            ]
        bParts = [
            v
            if isLast else
            v._cast_sign(False)
            for isLast, v in iter_with_last(split_to_segments(b, partWidth, extendLast=True))
            ]

        return aParts, bParts

    def aluFn(self, inp: HStructRtlSignalBase, isSim:bool=False) -> AnyHBitsValue:
        a: AnyHBitsValue = inp.a
        b: AnyHBitsValue = inp.b
        isSigned, partWidth, aWidth, bWidth = self._getPartWidth(a._dtype, b._dtype)
        # :note: partWidth must be same for a/b, it represents the base (shift)
        #  of each term in final recomposition and if the
        #  base is not the same the recomposition becames more complex
        (a0, a1, a2), (b0, b1) = self._splitToParts(a, b, partWidth)
        # x = base = 1 << partWidth
        # a(x) = a2*x^2 + a1*x + a0
        # b(x) = b1*x + b0

        # Toom-2.5 matrix
        #
        # v(  0) = (   0   0   0   1)
        # v(  1) = (   1   1   1   1)
        # v( -1) = (  -1   1  -1   1)
        # v(inf) = (   1   0   0   0)

        # Evaluate at 4 points: 0, 1, -1, ∞
        # (named p)              (named q)
        # a(0) = a0              b(0) = b0
        # a(1) = a0 + a1 + a2,   b(1) = b0 + b1
        # a(-1) = a0 - a1 + a2   b(-1) = b0 - b1
        # a(inf) = a2            b(inf) = b1
        #
        # v(n) = a(n) * b(n)
        if isSim:
            _a0 = int(a0)
            _a1 = int(a1)
            _a2 = int(a2)
            _b0 = int(b0)
            _b1 = int(b1)
      
        # :note: the intermediate results are natively signed, and if the polynome is evaluated in negative
        #        point it must be signed and there is no way around
        p0 = a0
        q0 = b0
        v0 = mulFullWidth(p0, q0)
        if isSim:
            _v0 = _a0 * _b0
            assert int(v0) == _v0, (int(v0), _a0, _b0)

        # p1 =  a0 + a1 + a2
        p1 = addAutoExtMany(a0, a1, a2)
        if isSim:
            _p1 = (_a0 + _a1 + _a2)
            assert int(p1) == _p1, (int(p1), _a0 + _a1 + _a2)

        # q1 = b0 + b1
        q1 = addAutoExt(b0, b1)
        if isSim:
            _q1 = _b0 + _b1
            assert int(q1) == _q1, (_b0, _b1)
        v1 = mulFullWidth(p1, q1)._cast_sign(isSigned)
        if isSim:
            _v1 = _p1 * _q1
            assert int(v1) == _v1, (int(v1), _p1, _q1)

        pm1 = addAutoExt(subAutoExt(a0, a1)._cast_sign(True), a2)
        if isSim:
            _pm1 = _a0 - _a1 + _a2
            assert int(pm1) == _pm1, (pm1, _pm1)
        qm1 = subAutoExt(b0, b1)._cast_sign(True)
        if isSim:
            _qm1 = _b0 - _b1
            assert int(qm1) == _qm1, (qm1, _qm1)
        vm1 = mulFullWidth(pm1, qm1)._cast_sign(True)
        if isSim:
            _vm1 = _pm1 * _qm1
            assert int(vm1) == _vm1, (int(vm1), _vm1)

        pinf = a2
        qinf = b1
        vinf = mulFullWidth(pinf, qinf)._cast_sign(isSigned)
        if isSim:
            _vinf = _a2 * _b1
            assert int(vinf) == _vinf, (vinf, _vinf)

        # --- Interpolation (solve for result coefficients) ---
        # The resulting polynomial C(x) = C3*x^3 + C2*x^2 + C1*x + C0.
        # Linear algegra solution of for specified Toom-2.5 matrix.
        # There are several options, this one is not used as it is less balanced expression
        # c1 = subAutoExt(v1, vm1)[:1]
        # c2 = subAutoExt(
        #         subAutoExt(
        #             addAutoExt(v1, vm1)[:1],
        #             v0),
        #         vinf)
        c0 = v0
        c1 = subAutoExt(subAutoExt(v1, vm1)[:1], vinf)
        if isSim:
            _c1 = (_v1 - _vm1) // 2 - _vinf
            assert int(c1) == _c1, (c1, _c1)
        c2 = subAutoExt(addAutoExt(v1, vm1), v0._concat(b0_const))[:1]
        if isSim:
            _c2 = (_v1 + _vm1 - 2 * _v0) // 2
            assert int(c2) == _c2, (c2, _c2)
        c3 = vinf

        # Recomposition
        # result = c0 + c1*x + c2*x^2 + c3*x^3
        sh = partWidth
        result = addShiftedMany([
            (c0, 0),
            (c1, sh),
            (c2, 2 * sh),
            (c3, 3 * sh),
        ], maxResultWidth=aWidth + bWidth)._cast_sign(isSigned)

        if isSim:
            _result0 = addShiftedMany([
                (c0, 0),
                (c1, sh),
            ])
            _result0Ref = _v0 + (_c1 << sh)
            assert int(_result0) == _result0Ref, (_result0, _result0Ref)
            _result1 = addShiftedMany([
                (_result0, 0),
                (c2, 2 * sh),
            ])
            _result0Ref += _c2 << (2 * sh)
            assert int(_result1) == _result0Ref, (_result1, _result0Ref)
            _result0Ref += _vinf << (3 * sh)
            assert int(result) == _result0Ref, (result, _result0Ref)
            assert int(result) == int(a) * int(b), (int(result), int(a) * int(b))

        return result._reinterpret_cast(self.T)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # from hwtHls.llvm.llvmIr import LlvmCompilationBundle
    from hwt.serializer.verilog import VerilogSerializer
    from hwtHls.platform.xilinx.artix7 import Artix7Fast

    #    :note: inp. bitwidth/DSPs/LUTs: 16/4/16, 32/4/31, 64/10/234, 128//
    #    :note: inp. bitwidth/DSPs: 16/3, 32/4, 64/11, 128/38
    m = PipelinedMultiplierToom2_5()
    m.T_LHS = HBits(24, signed=True)
    m.T_RHS = HBits(16, signed=True)
    m.T = HBits(24 + 16, signed=True)

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

