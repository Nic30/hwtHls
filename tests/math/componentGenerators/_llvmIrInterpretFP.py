from typing import Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.llvm.llvmIr import Instruction, HFloatTmpConfig, APFloat, APInt, \
    InstructionToCallInst, MachineRegisterInfo, MachineInstr
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import LlvmIrInstrFunction
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import to_unsigned
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction


class ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary(ComponentGenerator):
    """
    Specialized variants of hwtHls.fp. intrinsic function appear during lowering to target instruction
    They are typically derived from llvm fp operators and alike with constrained fp type or value. 
    """

    def evalFn(self, x:float) -> float:
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def llvmIrInterpretDecode(self, interpret:"LlvmIrInterpret", instr:Instruction) -> LlvmIrInstrFunction:
        try:
            cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 1)
        except:
            raise AssertionError("Malformed HFloatTmpConfig operands in instruction", instr, HFloatTmpConfig.MEMBER_CNT)
        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        _v, = interpret._decodeInstArguments((instr.getOperand(0),))
        vIsConst = isinstance(_v, HConst)
        evalFn = self.evalFn

        def _intrinsic_specializedUnOperator(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if vIsConst:
                v = _v
            else:
                v = regs[_v]

            if v._is_full_valid():
                t = v._dtype
                v = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(v)))
                v = evalFn(float(v))
                v = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v))
                v = int(v)
                if v < 0:
                    v = to_unsigned(v, t.bit_length())
                res = t.from_py(v)
            else:
                res = resUndef
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_specializedUnOperator


class ComponentGeneratorForSpecializedHwtHlsFpIntrinsicUnary_binResult(ComponentGenerator):

    def evalFn(self, x:float) -> tuple[float, float]:
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def llvmIrInterpretDecode(self, interpret:"LlvmIrInterpret", instr:Instruction) -> LlvmIrInstrFunction:
        try:
            cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 1)
        except:
            raise AssertionError("Malformed HFloatTmpConfig operands in instruction", instr, HFloatTmpConfig.MEMBER_CNT)
        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        _v, = interpret._decodeInstArguments((instr.getOperand(0),))
        vIsConst = isinstance(_v, HConst)
        evalFn = self.evalFn

        def _intrinsic_specializedUnOperator_binResult(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            if vIsConst:
                v = _v
            else:
                v = regs[_v]

            if v._is_full_valid():
                t = v._dtype
                v = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(v)))
                v0, v1 = evalFn(float(v))
                v0 = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v0))
                v1 = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v1))
                v0 = int(v0)
                v1 = int(v1)
                if v0 < 0:
                    v0 = to_unsigned(v0, t.bit_length())
                if v1 < 0:
                    v1 = to_unsigned(v1, t.bit_length())

                res0 = t.from_py(v0)
                res1 = t.from_py(v1)
            else:
                res0 = resUndef
                res1 = resUndef
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, (res0, res1), None)
            regs[instr] = (res0, res1)

        return _intrinsic_specializedUnOperator_binResult


class ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatFloat(ComponentGenerator):

    def evalFn(self, a: float, b:float) -> float:
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def llvmIrInterpretDecode(self, interpret:"LlvmIrInterpret", instr:Instruction) -> LlvmIrInstrFunction:
        ops = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1)))
        try:
            cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 2)
        except:
            raise AssertionError("Malformed HFloatTmpConfig operands in instruction", instr, HFloatTmpConfig.MEMBER_CNT)
        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        evalFn = self.evalFn

        def _intrinsic_specialized_BinOperator_FloatFloat(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            op0, op1 = interpret._prepareInstrArguments(ops, regs)
            if op0._is_full_valid() and op1._is_full_valid():
                t = op0._dtype
                op0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(op0)))
                op0 = float(op0)
                op1 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(op1)))
                op1 = float(op1)
                v = evalFn(op0, op1)
                v = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v))
                res = int(v)
                if res < 0:
                    res = to_unsigned(res, t.bit_length())
                res = t.from_py(res)
            else:
                res = resUndef
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_specialized_BinOperator_FloatFloat


class ComponentGeneratorForSpecializedHwtHlsFpIntrinsicBinary_FloatInt(ComponentGenerator):

    def evalFn(self, a: float, b:int) -> float:
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def llvmIrInterpretDecode(self, interpret:"LlvmIrInterpret", instr:Instruction) -> LlvmIrInstrFunction:
        ops = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1)))
        try:
            cfg: HFloatTmpConfig = HFloatTmpConfig.fromCallArgs(InstructionToCallInst(instr), 2)
        except:
            raise AssertionError("Malformed HFloatTmpConfig operands in instruction", instr, HFloatTmpConfig.MEMBER_CNT)
        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        evalFn = self.evalFn

        def _intrinsic_specialized_BinOperator_FloatInt(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            op0, op1 = interpret._prepareInstrArguments(ops, regs)
            if op0._is_full_valid() and op1._is_full_valid():
                t = op0._dtype
                op0 = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(t.bit_length(), int(op0)))
                op0 = float(op0)
                v = evalFn(op0, int(op1))
                v = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(v))
                res = int(v)
                if res < 0:
                    res = to_unsigned(res, t.bit_length())
                res = t.from_py(res)
            else:
                res = resUndef
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_specialized_BinOperator_FloatInt

    def llvmMirInterpretDecode(self, interpret: LlvmMirInterpret, MRI: MachineRegisterInfo, instr: MachineInstr, rhsIsSigned=False, evalFn=None) -> LlvmMirInstrFunction:
        try:
            cfg: HFloatTmpConfig = HFloatTmpConfig.fromMachineInstrOperands(instr, 3)
        except:
            raise AssertionError("Malformed HFloatTmpConfig operands in instruction", instr, HFloatTmpConfig.MEMBER_CNT)
        dst, _src0, _src1 = interpret._decodeInstArguments(MRI, instr, (instr.getOperand(0), instr.getOperand(1), instr.getOperand(2)))
        src0IsConst = isinstance(_src0, HConst)
        src1IsConst = isinstance(_src1, HConst)
        cond, hasRuntimeCond = interpret._decodeEnableCondition(instr)

        resUndef = HBits(cfg.getBitWidth()).from_py(None)
        if evalFn is None:
            evalFn = self.opDef._evalFn

        def _opcode_FP_binary_floatInt(nowTime: int, regs: list[HConst]):
            if hasRuntimeCond and not regs[cond]:
                res = resUndef
            else:
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
                    try:
                        res = evalFn(float(src0), int(src1))
                    except:
                        raise
                    res = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(res))
                    res = int(res)
                    if res < 0:
                        res = to_unsigned(res, t.bit_length())
                    res = t.from_py(res)
                else:
                    res = resUndef

            regs[dst] = res

        return _opcode_FP_binary_floatInt


class ComponentGeneratorForUnSpecializedHwtHlsFpIntrinsicBinary_FloatInt(ComponentGenerator):

    def evalFn(self, a: float, b:int) -> float:
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__)

    @override
    def llvmIrInterpretDecode(self, interpret:"LlvmIrInterpret", instr:Instruction) -> LlvmIrInstrFunction:
        ops = interpret._decodeInstArguments((instr.getOperand(0), instr.getOperand(1)))
        resUndef = HFloatTmp.from_py(None)
        evalFn = self.evalFn

        def _intrinsic_fp_unspecialized_floatInt(waveLog: Optional[VcdWriter], nowTime: int, regs: dict[Instruction, HConst]):
            op0, op1 = interpret._prepareInstrArguments(ops, regs)
            if op0._is_full_valid() and op1._is_full_valid():
                res = evalFn(float(op0), int(op1))
                res = HFloatTmp.from_py(res)
            else:
                res = resUndef
            # inlined interpret._storeInstrResult from perf. reasons
            if waveLog is not None:
                waveLog.logChange(nowTime, instr, res, None)
            regs[instr] = res

        return _intrinsic_fp_unspecialized_floatInt

