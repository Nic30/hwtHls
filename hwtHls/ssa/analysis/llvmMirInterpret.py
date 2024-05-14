from datetime import datetime
from io import StringIO
from itertools import islice
from typing import Tuple, List, Generator, Union, Optional, Dict, Iterable, Any, \
    Callable

from hwt.code import Concat
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import INT, SLICE
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.code import OP_CTLZ, OP_CTTZ, OP_CTPOP
from hwtHls.llvm.llvmIr import parseMIR, LlvmCompilationBundle, MachineFunction, MachineBasicBlock, MachineInstr, TargetOpcode, MachineOperand, \
    CmpInst, TypeToIntegerType, Register, LLVMStringContext, MachineRegisterInfo
from hwtHls.ssa.analysis.llvmIrInterpret import VcdLlvmIrCodelineFormatter, \
    VcdLlvmIrSimTimeFormatter, VcdLlvmIrBBFormatter, SimIoUnderflowErr, _prepareWaveWriterTopIo, \
    LlvmIrInterpret
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.triggers import StopSimumulation
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import LogValueFormatter, \
    VcdBitsFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter


class VcdLlvmIrBBFormatter(LogValueFormatter):

    def bind_var_info(self, varInfo: "VcdVarWritingInfo"):
        self.vcdId = varInfo.vcdId

    def format(self, newVal: MachineBasicBlock, updater, t: int, out: StringIO):
        # val = newVal.getName().str()
        # name = newVal.printAsOperand()[len("label "):]
        # name = RE_ID.sub("_", name)
        name = f"{newVal.getNumber()}:{newVal.getName().str():s}"
        out.write(f"s{name:s} {self.vcdId:s}\n")


class ListWithSetitemListener(list):

    def __init__(self, __iterable:Iterable, listener:Callable[None, [list, Union[slice, int], Any]]) -> None:
        list.__init__(self, __iterable)
        self._listener = listener

    def __setitem__(self, __s:Union[slice, int], __o) -> None:
        self._listener(self, __s, __o)
        list.__setitem__(self, __s, __o)


class LlvmMirInterpret():
    """
    An interpret of the LLVM Machine IR for HwtFpga target
    
    :ivar MF: llvm MachineInstance function which will be executed by this interpret
    :ivar timeStep: time step used for wave logging
    :ivar waveLog: writer for wave logging
    :ivar strCtx: string context for llvm string allocations during initialization of waveLog
    :ivar codelineOffset: offset from beginning from the MIR .ll file where function body starts
    """

    def __init__(self, MF: MachineFunction, timeStep: int=CLK_PERIOD):
        self.MF = MF
        self.timeStep = timeStep
        self.waveLog: Optional[VcdWriter] = None
        self.strCtx: Optional[LLVMStringContext] = None
        self.codelineOffset: int = 0

    def installWaveLog(self, waveLog: VcdWriter, strCtx: LLVMStringContext, codelineOffset: int=0):
        LlvmIrInterpret.installWaveLog(self, waveLog, strCtx, codelineOffset)

    def _prepareVcdWriter(self):
        waveLog = self.waveLog
        assert waveLog
        MF = self.MF
        MRI: MachineRegisterInfo = MF.getRegInfo()
        strCtx = self.strCtx
        waveLog.date(datetime.now())
        waveLog.timescale(1)
        instrCodeline: Dict[MachineInstr, int] = {}
        simCodelineLabel = object()
        simTimeLabel = object()
        simBlockLabel = object()
        with waveLog.varScope("__sim__") as simScope:
            simScope.addVar(simCodelineLabel, "codeline", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrCodelineFormatter(instrCodeline))
            simScope.addVar(simTimeLabel, "step", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrSimTimeFormatter(self.timeStep))
            simScope.addVar(simBlockLabel, "block", VCD_SIG_TYPE.ENUM, 0, VcdLlvmIrBBFormatter())

        _prepareWaveWriterTopIo(waveLog, strCtx, MF.getFunction())
        seen = set()
        codelineOffset = self.codelineOffset
        with waveLog.varScope(MF.getName().str().replace(".", "_")) as fnScope:
            for bb in MF:
                bb: MachineBasicBlock
                for instr in bb:
                    instr: MachineInstr
                    instrCodeline[instr] = codelineOffset
                    codelineOffset += 1
                    for op in instr.operands():
                        op: MachineOperand
                        if not op.isReg() or op.isUndef():
                            continue
                        reg: Register = op.getReg()
                        if reg in seen:
                            continue
                        else:
                            seen.add(reg)

                        llt = MRI.getType(reg)
                        if not llt.isValid():
                            continue

                        width = llt.getSizeInBits()
                        assert reg.isVirtual(), reg
                        regI = reg.virtRegIndex()
                        name = f"%{regI}"
                        fnScope.addVar(regI, name, VCD_SIG_TYPE.WIRE, width, VcdBitsFormatter())

                codelineOffset += 2

        waveLog.enddefinitions()
        return instrCodeline, simCodelineLabel, simTimeLabel, simBlockLabel

    def run(self, args: Tuple[Generator[Union[int, HValue], None, None], List[HValue], ...],
            wallTime:Optional[int]=None):
        """
        :param args: arguments for executed function, generator is used for inputs,
            list is for RAM/ROMs and outputs streams 
        """
        MF = self.MF
        timeStep = self.timeStep
        MRI: MachineRegisterInfo = MF.getRegInfo()
        waveLog = self.waveLog
        timeNow = -timeStep
        regs: List[Union[HValue, List[Union[int, HValue]], None]] = [None for _ in range(MRI.getNumVirtRegs())]
        if waveLog is not None:
            _, simCodelineLabel, simTimeLabel, simBlockLabel = self._prepareVcdWriter()

            def logToWave(_:List[HValue], i: int, v: HValue):
                if i in waveLog._idScope:
                    waveLog.logChange(timeNow, i, v, None)

            regs = ListWithSetitemListener(regs, logToWave)
        else:
            simCodelineLabel = None
            simTimeLabel = None
            simBlockLabel = None

        mb: MachineBasicBlock = MF.getBlockNumbered(0)
        # globalValues: Dict[Register, HValue] = {}

        assert mb is not None
        while True:
            timeNow += timeStep
            if wallTime is not None and wallTime <= timeNow:
                raise StopSimumulation()

            if waveLog is not None:
                waveLog.logChange(timeNow, simBlockLabel, mb, None)
            nextMb = None
            ops: List[Union[Register, MachineBasicBlock, int, HValue]] = []
            for mi in mb:
                mi: MachineInstr

                if waveLog is not None:
                    waveLog.logChange(timeNow, simTimeLabel, timeNow, None)
                    waveLog.logChange(timeNow, simCodelineLabel, mi, None)

                # print(mi)
                opc = mi.getOpcode()
                ops.clear()
                for mo in mi.operands():
                    mo: MachineOperand
                    if mo.isReg():
                        r = mo.getReg()
                        if mo.isDef():
                            ops.append(r)
                        elif mo.isUndef():
                            llt = MRI.getType(mo.getReg())
                            assert llt.isValid()
                            width = llt.getSizeInBits()
                            ops.append(Bits(width).from_py(None))
                        else:
                            ops.append(regs[r.virtRegIndex()])

                    elif mo.isMBB():
                        ops.append(mo.getMBB())
                    elif mo.isImm():
                        ops.append(mo.getImm())
                    elif mo.isCImm():
                        c = mo.getCImm()
                        v = c.getValue()
                        t = TypeToIntegerType(c.getType())
                        if t is None:
                            raise NotImplementedError(mi, mo)
                        pyT = Bits(t.getBitWidth())
                        v = int(v)
                        if v < 0:  # convert to unsigned
                            v = pyT.all_mask() + v + 1
                        ops.append(pyT.from_py(v))
                    elif mo.isPredicate():
                        ops.append(CmpInst.Predicate(mo.getPredicate()))
                    elif mo.isGlobal():
                        ops.append(mo.getGlobal())
                    else:
                        raise NotImplementedError(mi, mo)

                if opc == TargetOpcode.HWTFPGA_ARG_GET:
                    dst, i = ops
                    assert dst.virtRegIndex() == i
                    assert regs[i] is None, regs[i]
                    regs[i] = args[i]

                elif opc == TargetOpcode.HWTFPGA_CLOAD:
                    val, io, index, cond = ops
                    isBlocking = isinstance(cond, int)
                    if isBlocking:
                        if not cond:
                            raise AssertionError("Always disabled load or store, this instruction should not exits", mi)
                    else:
                        assert cond._is_full_valid(), mi
                        if not cond:
                            llt = MRI.getType(val)
                            assert llt.isValid()
                            width = llt.getSizeInBits()
                            t = Bits(width)
                            regs[val.virtRegIndex()] = t.from_py(0, vld_mask=1 << width - 1)

                            continue

                    if not isinstance(index, int) or index != 0:
                        raise NotImplementedError(mi)

                    try:
                        v = next(io)
                    except StopIteration:
                        raise SimIoUnderflowErr("underflow on io argument", mi)

                    llt = MRI.getType(val)
                    assert llt.isValid()
                    t = Bits(llt.getSizeInBits())
                    if isinstance(v, HValue):
                        if v._dtype != t:
                            assert v._dtype.bit_length() == t.bit_length(), (mi, v._dtype, t, v)
                            v = v._reinterpret_cast(t)
                    else:
                        v = t.from_py(v)
                    regs[val.virtRegIndex()] = v

                elif opc == TargetOpcode.HWTFPGA_CSTORE:
                    val, io, index, cond = ops
                    isBlocking = isinstance(cond, int)
                    if isBlocking:
                        if not cond:
                            raise AssertionError("Always disabled load or store, this instruction should not exits", mi)
                    else:
                        assert cond._is_full_valid(), mi
                        if not cond:
                            continue

                    if not isinstance(index, int) or index != 0:
                        raise NotImplementedError(mi)

                    assert opc == TargetOpcode.HWTFPGA_CSTORE, mi
                    io.append(val)

                elif opc == TargetOpcode.HWTFPGA_EXTRACT:
                    dst, src, index, width = ops
                    if isinstance(index, int):
                        if width == 1:
                            # to prefer more simple notation
                            index = INT.from_py(index)
                        else:
                            index = SLICE.from_py(slice(index + width, index, -1))
                    else:
                        raise NotImplementedError(mi)
                    if src is None:
                        raise AssertionError("Indexing on uninitialized value (this is use before def)", mi)
                    res = src[index]
                    regs[dst.virtRegIndex()] = res

                elif opc == TargetOpcode.HWTFPGA_MERGE_VALUES:
                    dst = ops[0]
                    # dst src{N}, width{N} - lowest bits first
                    assert (len(ops) - 1) % 2 == 0, ops
                    half = (len(ops) - 1) // 2
                    res = Concat(*reversed(ops[1:half + 1]))
                    regs[dst.virtRegIndex()] = res

                elif opc == TargetOpcode.HWTFPGA_MUX:
                    dst = ops[0]
                    res = NOT_SPECIFIED
                    for v, c in grouper(2, islice(ops, 1, None), padvalue=None):
                        if c is None:
                            res = v
                            break
                        else:
                            if not c._is_full_valid():
                                res = v._dtype.from_py(None)
                                break
                            elif c:
                                res = v
                                break
                    if res is not NOT_SPECIFIED:
                        regs[dst.virtRegIndex()] = res

                elif opc == TargetOpcode.HWTFPGA_ICMP:
                    dst, pred, src0, src1 = ops
                    op = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]
                    if src0._dtype.signed is not None:
                        src0 = src0.cast_sign(None)
                    if src1._dtype.signed is not None:
                        src1 = src1.cast_sign(None)
                    res = op._evalFn(src0, src1)
                    regs[dst.virtRegIndex()] = res
                elif opc == TargetOpcode.HWTFPGA_BR:
                    nextMb = ops[0]
                elif opc == TargetOpcode.HWTFPGA_BRCOND:
                    cond, _mb = ops
                    assert cond._is_full_valid(), (mi, "Branch condition must be valid")
                    if cond:
                        nextMb = _mb
                        break

                elif opc == TargetOpcode.IMPLICIT_DEF:
                    dst, = ops
                    llt = MRI.getType(ops[0])
                    assert llt.isValid()
                    t = Bits(llt.getSizeInBits())
                    regs[dst.virtRegIndex()] = t.from_py(None)

                else:
                    op = HlsNetlistAnalysisPassMirToNetlistLowLevel.OPC_TO_OP.get(opc)
                    if op in (AllOps.NOT, OP_CTLZ, OP_CTTZ, OP_CTPOP):
                        dst, src0 = ops
                        if src0._dtype.signed is not None:
                            src0 = src0.cast_sign(None)
                        res = op._evalFn(src0)
                        regs[dst.virtRegIndex()] = res
                        continue

                    if op is not None:
                        dst, src0, src1 = ops
                        if src0._dtype.signed is not None:
                            src0 = src0.cast_sign(None)
                        if src1._dtype.signed is not None:
                            src1 = src1.cast_sign(None)
                        res = op._evalFn(src0, src1)
                        regs[dst.virtRegIndex()] = res
                        continue

                    if opc == TargetOpcode.PseudoRET:
                        return

                    raise NotImplementedError(mi)

            if nextMb is not None:
                mb = nextMb
            else:
                mb = mb.getFallThrough(False)

    @classmethod
    def runMirStr(cls, mirStr: str, nameOfMain: str, args: list):
        ctx = LlvmCompilationBundle(nameOfMain)
        m = parseMIR(mirStr, nameOfMain, ctx)
        MMI = ctx.getMachineModuleInfo()
        assert m is not None
        f = m.getFunction(ctx.strCtx.addStringRef(nameOfMain))
        assert f is not None
        mf = MMI.getMachineFunction(f)
        assert mf is not None
        interpret = cls(mf)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass
        except StopSimumulation:
            pass

        return ctx, MMI, m, mf
