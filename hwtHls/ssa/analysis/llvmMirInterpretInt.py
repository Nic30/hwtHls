from itertools import islice
from typing import Callable

from hwt.code import Concat
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import INT, SLICE
from hwt.math import log2ceil
from hwt.pyUtils.arrayQuery import grouper
from hwtHls.llvm.llvmIr import MachineRegisterInfo, MachineInstr
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel


def _decodeOpcode_HWTFPGA_EXTRACT(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, src, srcWidth, index, width = interpret._decodeInstArguments(MRI, instr, instr.operands())
    if isinstance(index, int):
        if width == 1:
            # to prefer more simple notation
            index = INT.from_py(index)
        else:
            index = SLICE.from_py(slice(index + width, index, -1))
    else:
        raise NotImplementedError(instr)

    srcIsConst = isinstance(src, HConst)

    def _opcode_HWTFPGA_EXTRACT(nowTime: int, regs: list[HConst]):
        if srcIsConst:
            _src = src
        else:
            _src = regs[src]
            if _src is None:
                raise AssertionError("Indexing on uninitialized value (this is use before def)", instr)
            elif not isinstance(_src, HConst):
                raise AssertionError(instr, _src)

        assert _src._dtype.bit_length() == srcWidth, (_src._dtype.bit_length() == srcWidth, instr, _src._dtype.bit_length(), "expected:", srcWidth)
        res = _src[index]
        assert res is not None, instr
        regs[dst] = res

    return _opcode_HWTFPGA_EXTRACT


def _decodeOpcode_G_EXTRACT(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, src, index = interpret._decodeInstArguments(MRI, instr, instr.operands())
    width = MRI.getType(instr.getOperand(0).getReg()).getScalarSizeInBits()
    if isinstance(index, int):
        if width == 1:
            # to prefer more simple notation
            index = INT.from_py(index)
        else:
            index = SLICE.from_py(slice(index + width, index, -1))
    else:
        raise NotImplementedError(instr)

    srcIsConst = isinstance(src, HConst)

    def _opcode_G_EXTRACT(nowTime: int, regs: list[HConst]):
        if srcIsConst:
            _src = src
        else:
            _src = regs[src]

            if src is None:
                raise AssertionError("Indexing on uninitialized value (this is use before def)", instr)
        regs[dst] = _src[index]

    return _opcode_G_EXTRACT


def _decodeOpcode_HWTFPGA_MERGE_VALUES(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst = instr.getOperand(0).getReg().virtRegIndex()
    opNum = instr.getNumOperands()
    # dst src{N}, width{N} - lowest bits first
    assert (opNum - 1) % 2 == 0, instr
    half = (opNum - 1) // 2
    ops = tuple(instr.operands())[1:half + 1]
    widths = tuple(instr.operands())[half + 1:]
    widths = tuple(w.getImm() for w in widths)
    ops = interpret._decodeInstArguments(MRI, instr, ops)

    def _opcode_HWTFPGA_MERGE_VALUES(nowTime: int, regs: list[HConst]):
        _ops = interpret._prepareInstrArguments(ops, regs)
        for i, (o, w) in enumerate(zip(_ops, widths)):
            if o is None:
                raise AssertionError("Indexing on uninitialized value (this is use before def)", i, instr.getOperand(i + 1), instr,)
            assert (o._dtype.bit_length() == w), (instr, i, o, w)
        res = Concat(*reversed(_ops))
        regs[dst] = res

    return _opcode_HWTFPGA_MERGE_VALUES


def _decodeOpcode_HWTFPGA_MUX(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dstReg = instr.getOperand(0).getReg()
    dst = dstReg.virtRegIndex()
    condValPairs = tuple(grouper(2, interpret._decodeInstArguments(MRI, instr, islice(instr.operands(), 1, None)), padvalue=None))
    llt = MRI.getType(dstReg)
    if llt.isValid():
        width = llt.getScalarSizeInBits()
        undefVal = HBits(width).from_py(None)
    else:
        undefVal = None
        for v, c in condValPairs:
            if isinstance(v, HConst):
                undefVal = v._dtype.from_py(None)
                break

    def _opcode_HWTFPGA_MUX(nowTime: int, regs: list[HConst]):
        res = NOT_SPECIFIED
        for v, c in condValPairs:
            if c is None and isinstance(c, int):
                assert regs[c] is not None, ("register operand was not previously defined", c, instr)
            if isinstance(v, int):
                assert regs[v] is not None, ("register operand was not previously defined", c, instr)

        for v, c in condValPairs:
            if c is None:
                if isinstance(v, int):
                    v = regs[v]
                res = v
                break
            else:
                # [todo] filter constant conditions in advance
                if isinstance(c, int):
                    c = regs[c]

                if not c._is_full_valid():
                    if undefVal is not None:
                        res = undefVal
                    else:
                        # it was not possible to resolve type compiletime, it must be resolved now
                        res = None
                        for _v, c in condValPairs:
                            _vVal = regs[_v]
                            if _vVal is not None:
                                res = _vVal._dtype.from_py(None)
                    break
                elif c:
                    if isinstance(v, int):
                        v = regs[v]
                    res = v
                    break

        if res is not NOT_SPECIFIED:
            regs[dst] = res

    return _opcode_HWTFPGA_MUX


def _decodeOpcode_G_SELECT(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, c, srcT, srcF = interpret._decodeInstArguments(MRI, instr, instr.operands())

    cIsConst = isinstance(c, HConst)
    tIsConst = isinstance(srcT, HConst)
    fIsConst = isinstance(srcF, HConst)
    llt = MRI.getType(instr.getOperand(0).getReg())
    if llt.isValid():
        width = llt.getScalarSizeInBits()
        undefVal = HBits(width).from_py(None)
    elif tIsConst:
        undefVal = srcT._dtype.from_py(None)
    elif fIsConst:
        undefVal = srcF._dtype.from_py(None)
    else:
        undefVal = None

    def _opcode_G_SELECT(nowTime: int, regs: list[HConst]):
        if cIsConst:
            _c = c
        else:
            _c = regs[c]

        if not _c._is_full_valid():
            if undefVal is None:
                res = regs[srcT]._dtype.from_py(None)
            else:
                res = undefVal
        elif _c:
            if tIsConst:
                res = srcT
            else:
                res = regs[srcT]
        else:
            if fIsConst:
                res = srcF
            else:
                res = regs[srcF]
        regs[dst] = res

    return _opcode_G_SELECT

# def _decodeOpcode_G_FSHL(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
#    ops = interpret._decodeInstArguments(MRI, instr, instr.operands())
#
#    def _opcode_G_FSHL(nowTime: int, regs: list[HConst]):
#        dst, a, b, c = interpret._prepareInstrArguments(ops)
#        regs[dst] = fshl(a, b, c)
#
#    return _opcode_G_FSHL
#
#
# def _decodeOpcode_G_FSHR(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
#    ops = interpret._decodeInstArguments(MRI, instr, instr.operands())
#
#    def _opcode_G_FSHR(nowTime: int, regs: list[HConst]):
#        dst, a, b, c = interpret._prepareInstrArguments(ops)
#        regs[dst] = fshr(a, b, c)
#
#    return _opcode_G_FSHR


def _decodeOpcode_COPY(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, src = interpret._decodeInstArguments(MRI, instr, instr.operands())
    srcIsConst = isinstance(src, HConst)

    def _opcode_COPY(nowTime: int, regs: list[HConst]):
        if srcIsConst:
            _src = src
        else:
            _src = regs[src]
        regs[dst] = _src

    return _opcode_COPY


def _decodeOpcode_G_ICMP(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, pred, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, instr.operands())
    op = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]
    evalFn = op._evalFn
    src0IsConst = isinstance(_src0, HConst)
    src1IsConst = isinstance(_src1, HConst)

    def _opcode_G_ICMP(nowTime: int, regs: list[HConst]):
        if src0IsConst:
            src0 = _src0
        else:
            src0 = regs[_src0]
        if src1IsConst:
            src1 = _src1
        else:
            src1 = regs[_src1]

        assert src0._dtype.signed is None, (instr, src0)
        assert src1._dtype.signed is None, (instr, src1)
        res = evalFn(src0, src1)
        regs[dst] = res

    return _opcode_G_ICMP


def _decodeOpcode_G_TRUNC(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, val = interpret._decodeInstArguments(MRI, instr, instr.operands())
    llt = MRI.getType(instr.getOperand(0).getReg())
    assert llt.isValid(), instr
    trucSlice = slice(llt.getScalarSizeInBits(), 0)
    valIsConst = isinstance(val, HConst)

    def _opcode_G_TRUNC(nowTime: int, regs: list[HConst]):
        if valIsConst:
            _val = val
        else:
            _val = regs[val]
        regs[dst] = _val[trucSlice]

    return _opcode_G_TRUNC


def _decodeOpcode_G_ZEXT(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, val = interpret._decodeInstArguments(MRI, instr, instr.operands())
    llt = MRI.getType(instr.getOperand(0).getReg())
    assert llt.isValid(), instr
    valMO = instr.getOperand(1)
    assert valMO.isReg(), instr
    srcLlt = MRI.getType(valMO.getReg())

    width = srcLlt.getScalarSizeInBits()
    newWidth = llt.getScalarSizeInBits()
    valIsConst = isinstance(val, HConst)

    def _opcode_G_ZEXT(nowTime: int, regs: list[HConst]):
        if valIsConst:
            _val = val
        else:
            _val = regs[val]
        assert _val._dtype.bit_length() == width
        regs[dst] = _val._zext(newWidth)

    return _opcode_G_ZEXT


def _decodeOpcode_G_SEXT(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    dst, val = interpret._decodeInstArguments(MRI, instr, instr.operands())
    llt = MRI.getType(instr.getOperand(0).getReg())
    assert llt.isValid(), instr
    valMO = instr.getOperand(1)
    assert valMO.isReg(), instr
    srcLlt = MRI.getType(valMO.getReg())

    width = srcLlt.getScalarSizeInBits()
    newWidth = llt.getScalarSizeInBits()
    valIsConst = isinstance(val, HConst)

    def _opcode_S_SEXT(nowTime: int, regs: list[HConst]):
        if valIsConst:
            _val = val
        else:
            _val = regs[val]
        assert _val._dtype.bit_length() == width
        regs[dst] = _val._sext(newWidth)

    return _opcode_S_SEXT


def _makeMinMaxDecoder(predicate: HOperatorDef):

    def _decodeOpcode_minmax(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        dst, val0, val1 = interpret._decodeInstArguments(MRI, instr, instr.operands())
        predFn = predicate._evalFn
        val0IsConst = isinstance(val0, HConst)
        val1IsConst = isinstance(val1, HConst)

        def _opcode_minmax(nowTime: int, regs: list[HConst]):
            if val0IsConst:
                _val0 = val0
            else:
                _val0 = regs[val0]
            if val1IsConst:
                _val1 = val1
            else:
                _val1 = regs[val1]

            p = predFn(_val0, _val1)
            if p._is_full_valid():
                if p:
                    v = _val0
                else:
                    v = _val1
            else:
                v = val0._dtype.from_py(None)
            regs[dst] = v

        return _opcode_minmax

    return _decodeOpcode_minmax


def _makeDecode_G_shift(opDef: HOperatorDef):

    def _decodeOpcode_G_shift(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        dst, _src0, _sh = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        shIsConst = isinstance(_sh, HConst)
        dstTy = MRI.getType(instr.getOperand(0).getReg())
        assert dstTy.isValid(), instr
        width = dstTy.getScalarSizeInBits()
        shAmountTruncSlice = SLICE.from_py(slice(log2ceil(width + 1), 0, -1))
        evalFn = opDef._evalFn

        def _opcode_shift(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
            if shIsConst:
                sh = _sh
            else:
                sh = regs[_sh]

            assert src0._dtype.signed is None
            assert sh._dtype.signed is None
            sh = sh[shAmountTruncSlice]  # truncate shiftAmount
            res = evalFn(src0, sh)
            regs[dst] = res

        return _opcode_shift

    return _decodeOpcode_G_shift


def _makeDecode_shift(opDef: HOperatorDef):

    def _decodeOpcode_shift(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        dst, _src0, _sh, width = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        shIsConst = isinstance(_sh, HConst)
        expectedShWidth = log2ceil(width + 1)
        evalFn = opDef._evalFn

        def _opcode_shift(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
            if shIsConst:
                sh = _sh
            else:
                sh = regs[_sh]
            assert src0._dtype.signed is None
            assert sh._dtype.signed is None
            assert sh._dtype.bit_length() == expectedShWidth, (instr, sh._dtype.bit_length(), expectedShWidth)
            res = evalFn(src0, sh)
            regs[dst] = res

        return _opcode_shift

    return _decodeOpcode_shift


def makeDecode_G_funel_shift(opDef: HOperatorDef):

    def _decodeOpcode_G_funel_shift(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        dst, _src0, _src1, _sh = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        shIsConst = isinstance(_sh, HConst)
        dstTy = MRI.getType(instr.getOperand(0).getReg())
        assert dstTy.isValid(), instr
        width = dstTy.getScalarSizeInBits()
        shAmountTruncSlice = SLICE.from_py(slice(log2ceil(width + 1), 0, -1))
        evalFn = opDef._evalFn

        def _opcode_G_funnel_shift(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]

            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]

            if shIsConst:
                sh = _sh
            else:
                sh = regs[_sh]

            assert src0._dtype.signed is None
            assert src1._dtype.signed is None
            assert sh._dtype.signed is None

            sh = sh[shAmountTruncSlice]
            res = evalFn(src0, src1, sh)
            regs[dst] = res

        return _opcode_G_funnel_shift

    return _decodeOpcode_G_funel_shift


def makeDecode_funel_shift(opDef: HOperatorDef):

    def _decodeOpcode_funel_shift(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        dst, _src0, _src1, _sh, width = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        shIsConst = isinstance(_sh, HConst)
        expectedShWidth = log2ceil(width + 1)
        evalFn = opDef._evalFn

        def _opcode_funnel_shift(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]

            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]

            if shIsConst:
                sh = _sh
            else:
                sh = regs[_sh]

            assert src0._dtype.signed is None
            assert src1._dtype.signed is None
            assert sh._dtype.signed is None

            assert sh._dtype.bit_length() == expectedShWidth, (instr, sh._dtype.bit_length(), expectedShWidth)
            res = evalFn(src0, src1, sh)
            regs[dst] = res

        return _opcode_funnel_shift

    return _decodeOpcode_funel_shift


def makeDecode_arithUnary(opDef: HOperatorDef):

    def _decodeOpcode_arithUnary(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        dst, _src0 = interpret._decodeInstArguments(MRI, instr, instr.operands())
        src0IsConst = isinstance(_src0, HConst)
        evalFn = opDef._evalFn

        def _opcode_arithUnary(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
            assert src0._dtype.signed is None
            res = evalFn(src0)
            regs[dst] = res

        return _opcode_arithUnary

    return _decodeOpcode_arithUnary


def makeDecode_arithmeticBin(opDef: HOperatorDef):

    def _decodeOpcode_arithmeticBin(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        try:
            dst, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, instr.operands())

        except:
            raise AssertionError("Instruction operands in invalid format or this is not binary arithmetic instruction", instr)
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        evalFn = opDef._evalFn

        def _opcode_arithmeticBin(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
                assert isinstance(src0, HConst), (instr, _src0, src0)

            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]
                assert isinstance(src1, HConst), (instr, _src1, src1)

            assert src0._dtype.signed is None
            assert src1._dtype.signed is None
            try:
                res = evalFn(src0, src1)
            except ZeroDivisionError:
                res = src0._dtype.from_py(None)
            regs[dst] = res

        return _opcode_arithmeticBin

    return _decodeOpcode_arithmeticBin


def _getBinInstrArgs_MUL_HL(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr):
    dst, _src0, _src1, _, _, _, _, _ = interpret._decodeInstArguments(MRI, instr, instr.operands())
    return dst, _src0, _src1


def makeDecode_arithmetic_MUL_HL(opDef: HOperatorDef):

    def _decodeOpcode_arithmetic_MUL_HL(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        try:
            dst, _src0, _src1, isSigned0, width0, isSigned1, width1, resultWidth = interpret._decodeInstArguments(MRI, instr, instr.operands())
        except:
            raise AssertionError("Instruction operands in invalid format or this is not binary arithmetic instruction", instr)

        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        evalFn = opDef._evalFn

        def _opcode_arithmeticBin(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
                assert isinstance(src0, HConst), (instr, _src0, src0)

            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]
                assert isinstance(src1, HConst), (instr, _src1, src1)

            assert src0._dtype.signed is None
            assert src1._dtype.signed is None
            try:
                res = evalFn(src0, src1, isSigned0, width0, isSigned1, width1, resultWidth)
            except ZeroDivisionError:
                res = src0._dtype.from_py(None)
            regs[dst] = res

        return _opcode_arithmeticBin

    return _decodeOpcode_arithmetic_MUL_HL


def makeDecode_arithmeticBinBin(evalFn: Callable[[int, int], [int, int]]):

    def _decodeOpcode_arithmeticBinBin(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        try:
            dst0, dst1, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, instr.operands())
        except:
            raise AssertionError("Instruction operands in invalid format or this is not binary arithmetic instruction", instr)
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)

        def _opcode_arithmeticBinBin(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
                assert isinstance(src0, HConst), (instr, _src0, src0)

            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]
                assert isinstance(src1, HConst), (instr, _src1, src1)

            assert src0._dtype.signed is None
            assert src1._dtype.signed is None
            try:
                res0, res1 = evalFn(src0, src1)
            except ZeroDivisionError:
                undef = src0._dtype.from_py(None)
                res0 = undef
                res1 = undef

            regs[dst0] = res0
            regs[dst1] = res1

        return _opcode_arithmeticBinBin

    return _decodeOpcode_arithmeticBinBin


def makeDecode_AddSubSatBin(evalFn: Callable[[HBitsConst, HBitsConst], HBitsConst]):

    def _decodeOpcode_AddSubSatBin(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        try:
            dst, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, instr.operands())
        except:
            raise AssertionError("Instruction operands in invalid format or this is not binary arithmetic instruction", instr)
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)

        def _opcode_AddSubSatBin(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
                assert isinstance(src0, HConst), (instr, _src0, src0)

            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]
                assert isinstance(src1, HConst), (instr, _src1, src1)

            assert src0._dtype.signed is None
            assert src1._dtype.signed is None
            res = evalFn((src0, src1))
            regs[dst] = res

        return _opcode_AddSubSatBin

    return _decodeOpcode_AddSubSatBin

