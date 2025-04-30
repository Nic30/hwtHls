from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import MachineRegisterInfo, MachineInstr
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction
from hwtSimApi.triggers import StopSimumulation


def _decodeOpcode_BR(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    # TargetOpcode.HWTFPGA_BR or TargetOpcode.G_BR

    nextBb = instr.getOperand(0)
    assert nextBb.isMBB()
    nextBb = nextBb.getMBB()
    bb = instr.getParent()

    def _opcode_BR(nowTime: int, regs: list[HConst]):
        waveLog = interpret.waveLog
        if waveLog is not None:
            waveLog.logChange(nowTime, interpret._simBlockLabel, nextBb, None)

        interpret._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
        return nextBb

    return _opcode_BR


def _decodeOpcode_BRCOND(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    # TargetOpcode.HWTFPGA_BRCOND or TargetOpcode.G_BRCOND
    bb = instr.getParent()
    cond, nextBb = interpret._decodeInstArguments(MRI, instr, instr.operands())
    if isinstance(cond, HConst):
        assert cond._is_full_valid(), (instr, "Branch condition must be valid")
        if cond:

            def _opcode_BRCOND_constCond(nowTime: int, regs: list[HConst]):
                waveLog = interpret.waveLog
                if waveLog is not None:
                    waveLog.logChange(nowTime, interpret._simBlockLabel, nextBb, None)

                interpret._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
                return nextBb

            return _opcode_BRCOND_constCond
        else:

            def _opcode_BRCOND_nop(nowTime: int, regs: list[HConst]):
                return nextBb

            return _opcode_BRCOND_nop

    else:
        hasFallTrough = bb.back() == instr
        if hasFallTrough:
            fallTroughMb = bb.getFallThrough(False)

        def _opcode_BRCOND_nonConstCond(nowTime: int, regs: list[HConst]):
            _cond = regs[cond]
            assert _cond is not None and _cond._is_full_valid(), (instr, "Branch condition must be valid")
            if _cond:
                _nextBb = nextBb
            elif hasFallTrough:
                _nextBb = fallTroughMb
            else:
                _nextBb = None

            if _nextBb is not None:
                waveLog = interpret.waveLog
                if waveLog is not None:
                    waveLog.logChange(nowTime, interpret._simBlockLabel, _nextBb, None)
    
                interpret._runBlockPhis(bb, _nextBb, waveLog, regs, nowTime)
                return _nextBb

        return _opcode_BRCOND_nonConstCond


def _opcode_HWTFPGA_RET(nowTime: int, regs: list[HConst]):
    raise StopSimumulation()


def _decodeOpcode_HWTFPGA_RET(interpret: "LlvmMirInterpret", MRI: MachineRegisterInfo, instr: MachineInstr) -> LlvmMirInstrFunction:
    return _opcode_HWTFPGA_RET
