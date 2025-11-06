from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwtHls.code import OP_SHL, OP_ASHR, \
    OP_LSHR, OP_FSHL, OP_FSHR
from hwtHls.llvm.llvmIr import TargetOpcode, MachineRegisterInfo, MachineInstr
from hwtHls.ssa.analysis.llvmMirInterpretInt import \
    _makeDecode_G_shift, _makeDecode_shift, \
    makeDecode_funel_shift, makeDecode_G_funel_shift, \
    makeDecode_arithmeticBin, makeDecode_arithUnary
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction


def _makeDecodeOpcodeFunction(opcode: TargetOpcode, opDef: HOperatorDef):
    """
    Create opcode function for rest of the operands
    """
    if opDef is HwtOps.NOT:
        return makeDecode_arithUnary(opDef)
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

    # elif opcode in HlsNetlistAnalysisPassMirToNetlistLowLevel._FP_BIN_OPCODES:
    #     if opcode in HlsNetlistAnalysisPassMirToNetlistLowLevel._FP_BIN_OPCODES_FLOAT_INT:
    #         rhsIsSigned = opcode == TargetOpcode.G_FPOWI
    #         return _makeDecodeFpBinary_floatInt(opDef, rhsIsSigned)
    #     else:
    #         return _makeDecodeFpBinary(opDef)

    # elif opcode in HlsNetlistAnalysisPassMirToNetlistLowLevel._FP_UNARY_OPCODES:
    #     return _makeDecodeFpUnary(opDef)
    else:
        return makeDecode_arithmeticBin(opDef)


def _decodeOpcode_HWTFPGA_PYOBJECT_PLACEHOLDER(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    fnIdOp = instr.getOperand(1)
    assert fnIdOp.isImm(), instr
    fnId = fnIdOp.getImm()
    ph: "HardBlockHwModule" = interpret.placeholderObjectSlots[fnId][0]
    gen: "ComponentGeneratorForHardBlock" = interpret.componentGenerators[ph.getComponentGeneratorKey()]
    return gen.llvmMirInterpretDecode(interpret, MRI, instr, ph)

