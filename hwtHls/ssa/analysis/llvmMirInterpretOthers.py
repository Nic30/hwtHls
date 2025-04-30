from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwtHls.code import OP_CTLZ, OP_CTTZ, OP_CTPOP, OP_SHL, OP_ASHR, \
    OP_LSHR, OP_FSHL, OP_FSHR
from hwtHls.llvm.llvmIr import TargetOpcode, MachineRegisterInfo, MachineInstr, HFloatTmpConfig, \
    APInt, APFloat
from hwtHls.netlist.extraOps import OP_UDIVREM, OP_SDIVREM
from hwtHls.ssa.analysis.llvmMirInterpretInt import makeDecode_G_bitcounts, \
    makeDecode_HWTFPGA_NOT_or_bitcounts, _makeDecode_G_shift, _makeDecode_shift, \
    makeDecode_funel_shift, makeDecode_G_funel_shift, \
    makeDecode_arithmeticBinRes, makeDecode_arithmeticBin
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from pyMathBitPrecise.bit_utils import to_unsigned
from hwt.hdl.types.defs import BIT


def _makeDecodeFpUnary(opDef: HOperatorDef):

    def _decodeFpUnary(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 2)
        dst, _src0 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0), instr.getOperand(1)))
        src0IsConst = isinstance(_src0, HConst)
        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        evalFn = opDef._evalFn

        # resTy = HBits(log2ceil(w + 1))
        def _opcode_FP_unary(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]

            if src0._dtype.signed is not None:
                src0 = src0._cast_sign(None)

            if src0._is_full_valid():
                t = src0._dtype
                src0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src0)))
                res = evalFn(float(src0))
                res = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(res))
                res = int(res)
                if res < 0:
                    res = to_unsigned(res, t.bit_length())
                res = t.from_py(res)
            else:
                res = resUndef

            regs[dst] = res

        return _opcode_FP_unary

    return _decodeFpUnary


def _makeDecodeFpBinary(opDef: HOperatorDef):

    def _decodeFpBinary(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 3)
        dst, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0), instr.getOperand(1), instr.getOperand(2)))
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)

        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        evalFn = opDef._evalFn

        # resTy = HBits(log2ceil(w + 1))
        def _opcode_FP_binary(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]

            if src0._dtype.signed is not None:
                src0 = src0._cast_sign(None)

            if src1._dtype.signed is not None:
                src1 = src1._cast_sign(None)

            if src0._is_full_valid() and src1._is_full_valid():
                t = src0._dtype
                src0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src0)))
                src1 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src1)))
                res = evalFn(float(src0), float(src1))
                res = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(res))
                res = int(res)
                if res < 0:
                    res = to_unsigned(res, t.bit_length())
                res = t.from_py(res)
            else:
                res = resUndef

            regs[dst] = res

        return _opcode_FP_binary

    return _decodeFpBinary


def _makeDecodeFpBinary_floatInt(opDef: HOperatorDef, rhsIsSigned: bool):

    def _decodeFpBinary_floatInt(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
        cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 3)
        dst, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0), instr.getOperand(1), instr.getOperand(2)))
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)

        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        evalFn = opDef._evalFn

        def _opcode_FP_binary(nowTime: int, regs: list[HConst]):
            if src0IsConst:
                src0 = _src0
            else:
                src0 = regs[_src0]
            if src1IsConst:
                src1 = _src1
            else:
                src1 = regs[_src1]

            if src0._dtype.signed is not None:
                src0 = src0._cast_sign(None)

            if rhsIsSigned:
                src1 = src1._cast_sign(True)
            elif src1._dtype.signed is not None:
                src1 = src1._cast_sign(None)

            if src0._is_full_valid() and src1._is_full_valid():
                t = src0._dtype
                src0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src0)))
                res = evalFn(float(src0), int(src1))
                res = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(res))
                res = int(res)
                if res < 0:
                    res = to_unsigned(res, t.bit_length())
                res = t.from_py(res)
            else:
                res = resUndef

            regs[dst] = res

        return _opcode_FP_binary

    return _decodeFpBinary_floatInt


def _decode_HWTFPGA_FP_FCMP(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 3)
    dst, predicate, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0),
                                                                               instr.getOperand(1),
                                                                               instr.getOperand(2),
                                                                               instr.getOperand(3)))
    src0IsConst = isinstance(_src0, HConst)
    src1IsConst = isinstance(_src1, HConst)
    resUndef = BIT.from_py(None)
    opDef = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_FP_OP_PY[predicate]
    evalFn = opDef._evalFn

    def _opcode_HWTFPGA_FP_FCMP(nowTime: int, regs: list[HConst]):
        if src0IsConst:
            src0 = _src0
        else:
            src0 = regs[_src0]
        if src1IsConst:
            src1 = _src1
        else:
            src1 = regs[_src1]

        if src0._dtype.signed is not None:
            src0 = src0._cast_sign(None)

        if src1._dtype.signed is not None:
            src1 = src1._cast_sign(None)

        if src0._is_full_valid() and src1._is_full_valid():
            t = src0._dtype
            src0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src0)))
            src1 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(src1)))
            res = evalFn(float(src0), float(src1))
            res = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(res))
            res = BIT.from_py(res)
        else:
            res = resUndef

        regs[dst] = res

    return _opcode_HWTFPGA_FP_FCMP


def _makeDecodeOpcodeFunction(opcode: TargetOpcode, opDef: HOperatorDef):
    """
    Create opcode function for rest of the operands
    """
    if opDef in (HwtOps.NOT, OP_CTLZ, OP_CTTZ, OP_CTPOP):
        if opcode in (TargetOpcode.G_CTLZ, TargetOpcode.G_CTTZ, TargetOpcode.G_CTPOP):
            return makeDecode_G_bitcounts(opDef)
        else:
            return makeDecode_HWTFPGA_NOT_or_bitcounts(opDef)

    elif opDef in (OP_SHL, OP_ASHR, OP_LSHR):

        if opcode in (TargetOpcode.G_SHL, TargetOpcode.G_ASHR, TargetOpcode.G_LSHR):
            return _makeDecode_G_shift(opDef)

        else:
            assert opcode in (TargetOpcode.HWTFPGA_SHL, TargetOpcode.HWTFPGA_ASHR, TargetOpcode.HWTFPGA_LSHR), opcode
            return _makeDecode_shift(opDef)

    elif opDef in (OP_FSHL, OP_FSHR):
        if opcode in (TargetOpcode.G_FSHL, TargetOpcode.G_FSHR):
            return makeDecode_G_funel_shift(opDef)
        else:
            assert opcode in (TargetOpcode.HWTFPGA_FSHL, TargetOpcode.HWTFPGA_FSHR), opcode
            return makeDecode_funel_shift(opDef)

    elif opDef in (OP_UDIVREM, OP_SDIVREM):
        return makeDecode_arithmeticBinRes(opDef)

    elif opcode in HlsNetlistAnalysisPassMirToNetlistLowLevel._FP_BIN_OPCODES:
        if opcode in HlsNetlistAnalysisPassMirToNetlistLowLevel._FP_BIN_OPCODES_FLOAT_INT:
            rhsIsSigned = opcode == TargetOpcode.G_FPOWI
            return _makeDecodeFpBinary_floatInt(opDef, rhsIsSigned)
        else:
            return _makeDecodeFpBinary(opDef)

    elif opcode in HlsNetlistAnalysisPassMirToNetlistLowLevel._FP_UNARY_OPCODES:
        return _makeDecodeFpUnary(opDef)
    else:
        return makeDecode_arithmeticBin(opDef)

