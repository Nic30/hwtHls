from copy import copy
from datetime import datetime
from typing import Generator, Union, Optional, Callable, Sequence

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwtHls.llvm.llvmIr import parseMIR, LlvmCompilationBundle, MachineFunction, \
    MachineBasicBlock, MachineInstr, TargetOpcode, MachineOperand, \
    CmpInst, TypeToIntegerType, Register, LLVMStringContext, MachineRegisterInfo, \
    HwtHlsIoMetadata_get, HwtHlsIoMetadata
from hwtHls.platform.platform import ComponentGeneratorDict
from hwtHls.ssa.analysis.llvmIrInterpret import VcdLlvmIrCodelineFormatter, \
    VcdLlvmIrSimTimeFormatter, _prepareWaveWriterTopIo, LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretInt import _opcode_Intrinsic_usub_sat, \
    _opcode_Intrinsic_uadd_sat, _opcode_Intrinsic_sadd_sat, \
    _opcode_Intrinsic_ssub_sat
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpretInt import _decodeOpcode_HWTFPGA_EXTRACT, \
    _decodeOpcode_G_EXTRACT, _decodeOpcode_HWTFPGA_MERGE_VALUES, \
    _decodeOpcode_HWTFPGA_MUX, _decodeOpcode_G_SELECT, \
    _decodeOpcode_COPY, _decodeOpcode_G_ICMP, \
    _decodeOpcode_G_TRUNC, _decodeOpcode_G_ZEXT, _decodeOpcode_G_SEXT, \
    _makeMinMaxDecoder, makeDecode_AddSubSatBin
from hwtHls.ssa.analysis.llvmMirInterpretJump import _decodeOpcode_BR, \
    _decodeOpcode_BRCOND, _decodeOpcode_HWTFPGA_RET
from hwtHls.ssa.analysis.llvmMirInterpretMem import _decodeOpcode_HWTFPGA_ARG_GET, \
    _decodeOpcode_HWTFPGA_CLOAD, _decodeOpcode_G_LOAD, \
    _decodeOpcode_HWTFPGA_CSTORE, _decodeOpcode_G_STORE, \
    _decodeOpcode_HWTFPGA_IMPLICIT_DEF, _decodeOpcode_G_IMPLICIT_DEF, \
    _decodeOpcode_G_CONSTANT, _decodeOpcode_G_GLOBAL_VALUE, \
    _decodeOpcode_G_PTR_ADD
from hwtHls.ssa.analysis.llvmMirInterpretOthers import _makeDecodeOpcodeFunction, \
    _decodeOpcode_HWTFPGA_PYOBJECT_PLACEHOLDER
from hwtHls.ssa.analysis.llvmMirInterpretUtils import LlvmMirInstrFunction, \
    DictWithSetitemListener, VcdLlvmMirBBFormatter
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtHls.ssa.translation.toLlvm import PyObjectPlaceholderList
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.triggers import StopSimumulation
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import VcdBitsFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter


class LlvmMirInterpret():
    """
    An interpret of the LLVM Machine IR for HwtFpga target
    
    :ivar MF: llvm MachineInstance function which will be executed by this interpret
    :ivar timeStep: time step used for wave logging
    :ivar waveLog: writer for wave logging
    :ivar strCtx: string context for llvm string allocations during initialization of waveLog
    :ivar codelineOffset: offset from beginning from the MIR .ll file where function body starts
    """
    _dispatchDict: dict[TargetOpcode, Callable] = {
        TargetOpcode.HWTFPGA_BR: _decodeOpcode_BR,
        TargetOpcode.G_BR: _decodeOpcode_BR,
        TargetOpcode.HWTFPGA_BRCOND: _decodeOpcode_BRCOND,
        TargetOpcode.G_BRCOND: _decodeOpcode_BRCOND,
        TargetOpcode.HWTFPGA_RET: _decodeOpcode_HWTFPGA_RET,
        TargetOpcode.HWTFPGA_ARG_GET: _decodeOpcode_HWTFPGA_ARG_GET,
        TargetOpcode.HWTFPGA_CLOAD: _decodeOpcode_HWTFPGA_CLOAD,
        TargetOpcode.G_LOAD: _decodeOpcode_G_LOAD,
        TargetOpcode.HWTFPGA_CSTORE: _decodeOpcode_HWTFPGA_CSTORE,
        TargetOpcode.G_STORE: _decodeOpcode_G_STORE,
        TargetOpcode.HWTFPGA_EXTRACT: _decodeOpcode_HWTFPGA_EXTRACT,
        TargetOpcode.G_EXTRACT: _decodeOpcode_G_EXTRACT,
        TargetOpcode.HWTFPGA_MERGE_VALUES: _decodeOpcode_HWTFPGA_MERGE_VALUES,
        TargetOpcode.HWTFPGA_MUX: _decodeOpcode_HWTFPGA_MUX,
        TargetOpcode.G_SELECT: _decodeOpcode_G_SELECT,
        # TargetOpcode.G_FSHL: _decodeOpcode_G_FSHL, # already in HlsNetlistAnalysisPassMirToNetlistLowLevel.OPC_TO_OP
        # TargetOpcode.G_FSHR: _decodeOpcode_G_FSHR,
        TargetOpcode.COPY: _decodeOpcode_COPY,
        TargetOpcode.G_ICMP: _decodeOpcode_G_ICMP,
        TargetOpcode.HWTFPGA_ICMP: _decodeOpcode_G_ICMP,
        TargetOpcode.HWTFPGA_IMPLICIT_DEF: _decodeOpcode_HWTFPGA_IMPLICIT_DEF,
        TargetOpcode.G_IMPLICIT_DEF: _decodeOpcode_G_IMPLICIT_DEF,
        TargetOpcode.G_CONSTANT: _decodeOpcode_G_CONSTANT,
        TargetOpcode.G_GLOBAL_VALUE: _decodeOpcode_G_GLOBAL_VALUE,
        TargetOpcode.HWTFPGA_GLOBAL_VALUE: _decodeOpcode_G_GLOBAL_VALUE,
        TargetOpcode.G_TRUNC: _decodeOpcode_G_TRUNC,
        TargetOpcode.G_ZEXT: _decodeOpcode_G_ZEXT,
        TargetOpcode.G_SEXT: _decodeOpcode_G_SEXT,
        TargetOpcode.G_UMIN: _makeMinMaxDecoder(HwtOps.ULT),
        TargetOpcode.G_UMAX: _makeMinMaxDecoder(HwtOps.UGT),
        TargetOpcode.G_SMIN: _makeMinMaxDecoder(HwtOps.SLT),
        TargetOpcode.G_SMAX: _makeMinMaxDecoder(HwtOps.SGT),
        TargetOpcode.G_UADDSAT: makeDecode_AddSubSatBin(_opcode_Intrinsic_uadd_sat),
        TargetOpcode.G_USUBSAT: makeDecode_AddSubSatBin(_opcode_Intrinsic_usub_sat),
        TargetOpcode.G_SADDSAT: makeDecode_AddSubSatBin(_opcode_Intrinsic_sadd_sat),
        TargetOpcode.G_SSUBSAT: makeDecode_AddSubSatBin(_opcode_Intrinsic_ssub_sat),
        TargetOpcode.G_PTR_ADD: _decodeOpcode_G_PTR_ADD,
        TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER: _decodeOpcode_HWTFPGA_PYOBJECT_PLACEHOLDER,
        TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE: _decodeOpcode_HWTFPGA_PYOBJECT_PLACEHOLDER,
        TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE_WITH_SIDEEFECT: _decodeOpcode_HWTFPGA_PYOBJECT_PLACEHOLDER,
        TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER_WITH_SIDEEFFECT: _decodeOpcode_HWTFPGA_PYOBJECT_PLACEHOLDER,
        **{
            opc: _makeDecodeOpcodeFunction(opc, op)
            for opc, op in HlsNetlistAnalysisPassMirToNetlistLowLevel.OPC_TO_OP.items()
        },
    }

    def __init__(self,
                 llvm: LlvmCompilationBundle,
                 placeholderObjectSlots: PyObjectPlaceholderList,
                 componentGenerators: ComponentGeneratorDict,
                 fnArgs: tuple[Generator[Union[int, HConst], None, None], list[HConst], ...],
                 timeStep: int=CLK_PERIOD):
        assert llvm.main
        self.MF: MachineFunction = llvm.getMachineFunction(llvm.main)
        assert self.MF
        self.timeStep = timeStep
        self.strCtx: LLVMStringContext = llvm.strCtx
        self.waveLog: Optional[VcdWriter] = None
        self.codelineOffset: int = 0
        self.ioMetadata: list[HwtHlsIoMetadata] = HwtHlsIoMetadata_get(self.MF.getFunction())
        self.fnArgs = fnArgs
        self.placeholderObjectSlots = placeholderObjectSlots
        self.componentGenerators = componentGenerators
        self._dispatchDict = copy(self._dispatchDict)
        for opc, cg in componentGenerators.items():
            if isinstance(opc, TargetOpcode):
                self._dispatchDict[opc] = cg.llvmMirInterpretDecode

        # dictionary which holds list of compiled function exec. functions for each block
        self._decodedBlocks: dict[MachineBasicBlock, list[tuple[MachineInstr, LlvmMirInstrFunction]]] = {}
        # dictionary (src, dst block) -> tuples (phi dst reg, new value)
        self._decodedBlockPhis: dict[tuple[MachineBasicBlock, MachineBasicBlock],
                                     list[tuple[int, Union[HBitsConst, int]]]
                                     ] = {}
        # object used as a key for current block value in wave logger
        self._simBlockLabel: Optional[object] = None
        self.nowTime: Optional[int] = None

    def installWaveLog(self, waveLog: VcdWriter, codelineOffset: int=0):
        LlvmIrInterpret.installWaveLog(self, waveLog, codelineOffset)

    def _prepareVcdWriter(self):
        waveLog = self.waveLog
        assert waveLog
        MF = self.MF
        MRI: MachineRegisterInfo = MF.getRegInfo()
        strCtx = self.strCtx
        waveLog.date(datetime.now())
        waveLog.timescale(1)
        instrCodeline: dict[MachineInstr, int] = {}
        simCodelineLabel = object()
        simTimeLabel = object()
        simBlockLabel = object()
        with waveLog.varScope("__sim__") as simScope:
            simScope.addVar(simCodelineLabel, "codeline", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrCodelineFormatter(instrCodeline))
            simScope.addVar(simTimeLabel, "step", VCD_SIG_TYPE.WIRE, 64, VcdLlvmIrSimTimeFormatter(self.timeStep))
            simScope.addVar(simBlockLabel, "block", VCD_SIG_TYPE.WIRE, 64, VcdLlvmMirBBFormatter())

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

                        width = llt.getScalarSizeInBits()
                        assert reg.isVirtual(), reg
                        regI = reg.virtRegIndex()
                        name = f"%{regI}"
                        fnScope.addVar(regI, name, VCD_SIG_TYPE.WIRE, width, VcdBitsFormatter())

                codelineOffset += 2

        waveLog.enddefinitions()
        return instrCodeline, simCodelineLabel, simTimeLabel, simBlockLabel

    def _prepareInstrArguments(self, args: list[Union[HConst, MachineBasicBlock, int]], regs: list[HConst]) -> list[Union[HConst, MachineBasicBlock]]:
        """
        :attention: do not use this for Imm operands as int is used for registers but is also value of Imm itself
        """
        # prepare values for arguments
        ops: list[Union[HConst, MachineBasicBlock]] = []
        for v in args:
            if isinstance(v, int):
                v = regs[v]
            ops.append(v)
        return ops

    @staticmethod
    def _decodeBlocks_getPhiIncomingValueForBlock(phi: MachineInstr, bb: MachineBasicBlock):
        vOp = None
        res = None
        for MO in phi.operands():
            MO: MachineOperand
            if MO.isMBB():
                if MO.getMBB() == bb:
                    return vOp
            vOp = MO
        if res is None:
            raise AssertionError("Predecessor was not found in phi operands", bb, phi)

    @staticmethod
    def _decodeInstArguments(MRI: MachineRegisterInfo, miForDebugOnly: MachineInstr, operandValues: Sequence[MachineOperand]):
        # prepare values for arguments
        ops: list[Union[HConst, MachineBasicBlock, int]] = []
        for mo in operandValues:
            mo: MachineOperand
            if mo.isReg():
                r: Register = mo.getReg()
                if mo.isDef():
                    ops.append(r.virtRegIndex())
                elif mo.isUndef():
                    llt = MRI.getType(mo.getReg())
                    assert llt.isValid()
                    width = llt.getScalarSizeInBits()
                    ops.append(HBits(width).from_py(None))
                else:
                    v = r.virtRegIndex()
                    # v = regs[r.virtRegIndex()]
                    # if v is None:
                    #    llt = MRI.getType(r)
                    #    assert llt.isValid(), (r, r.virtRegIndex(), "This may happen if use is not dominated by any def")
                    #    width = llt.getScalarSizeInBits()
                    #    v = HBits(width).from_py(None)
                    ops.append(v)

            elif mo.isMBB():
                ops.append(mo.getMBB())
            elif mo.isImm():
                ops.append(mo.getImm())
            elif mo.isCImm():
                c = mo.getCImm()
                v = c.getValue()
                t = TypeToIntegerType(c.getType())
                if t is None:
                    raise NotImplementedError(miForDebugOnly, mo)
                pyT = HBits(t.getBitWidth())
                v = int(v)
                if v < 0:  # convert to unsigned
                    v = pyT.all_mask() + v + 1
                ops.append(pyT.from_py(v))
            elif mo.isPredicate():
                ops.append(CmpInst.Predicate(mo.getPredicate()))
            elif mo.isGlobal():
                ops.append(mo.getGlobal())
            else:
                raise NotImplementedError(miForDebugOnly, mo)

        return ops

    def _decodeEnableCondition(self, instr: MachineInstr) -> tuple[Union[int], bool]:
        """
        Some instructions like HWTFPGA_CLOAD have an additionl enable condition, which were generated
        during predication of instructions in IfConverter and others, this functions extract it
        """
        condMo: MachineOperand = instr.getOperand(instr.getNumExplicitOperands() - 1)
        hasRuntimeCond = condMo.isReg()
        if not hasRuntimeCond:
            if condMo.isImm():
                if not condMo.getImm():
                    raise AssertionError("Always disabled instruction, this instruction should not exits", instr)
            elif condMo.isCImm():
                if not condMo.getCImm():
                    raise AssertionError("Always disabled instruction, this instruction should not exits", instr)
            else:
                raise AssertionError("Uknown type of enCond operand", condMo, instr)
            r = None
        else:
            assert condMo.isReg(), instr
            r = condMo.getReg().virtRegIndex()
        return r, hasRuntimeCond

    def _decodePhiArgument(self, MRI: MachineRegisterInfo, phi: MachineInstr, vOp: MachineOperand) -> Union[int, HBitsConst]:
        if vOp.isReg():
            r = vOp.getReg()
            assert not vOp.isDef(), vOp

            if vOp.isUndef():
                llt = MRI.getType(vOp.getReg())
                assert llt.isValid()
                width = llt.getScalarSizeInBits()
                res = HBits(width).from_py(None)
            else:
                res = r.virtRegIndex()

        elif vOp.isCImm():
            c = vOp.getCImm()
            v = c.getValue()
            t = TypeToIntegerType(c.getType())
            if t is None:
                raise NotImplementedError(phi, vOp)
            pyT = HBits(t.getBitWidth())
            v = int(v)
            if v < 0:  # convert to unsigned
                v = pyT.all_mask() + v + 1
            res = pyT.from_py(v)

        return res

    def _make_opcode_fn_fallThrough(self, bb: MachineBasicBlock, fallThroughNextBB: MachineBasicBlock):
        """
        :note: wraped in extra function so bb, fallThroughNextBB will get captured in function scope
        """

        def _opcode_default_fallthrough(nowTime: int, regs: list[HConst]):
            assert fallThroughNextBB is not None
            nextBb = fallThroughNextBB
            waveLog = self.waveLog
            if waveLog is not None:
                waveLog.logChange(nowTime, self._simBlockLabel, nextBb, None)
            self._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
            return nextBb

        return _opcode_default_fallthrough

    def _decodeBlocks(self):
        MRI: MachineRegisterInfo = self.MF.getRegInfo()
        decodedBlockPhis = self._decodedBlockPhis
        for bb in self.MF:
            bb: MachineBasicBlock
            for predBb in bb.predecessors():
                phis = decodedBlockPhis[(predBb, bb)] = []
                for phi in bb:
                    phi: MachineInstr
                    opc = phi.getOpcode()
                    if opc != TargetOpcode.G_PHI and opc != TargetOpcode.PHI:
                        break

                    v = self._decodeBlocks_getPhiIncomingValueForBlock(phi, predBb)
                    assert v is not None, phi
                    v = self._decodePhiArgument(MRI, phi, v)
                    phiDst = phi.getOperand(0).getReg().virtRegIndex()
                    phis.append((phiDst, v))

            bbDecoded = self._decodedBlocks[bb] = []
            for instr in bb:
                instr: MachineInstr
                opc = instr.getOpcode()
                if opc == TargetOpcode.G_PHI or opc == TargetOpcode.PHI:
                    continue
                iDecoded = self._decodeLlvmMirInstr(MRI, bb, instr, opc)
                assert iDecoded is not None, instr
                bbDecoded.append((instr, iDecoded))

            if not bbDecoded:
                fallThroughNextBB = bb.getFallThrough(True)
                bbDecoded.append((None, self._make_opcode_fn_fallThrough(bb, fallThroughNextBB)))

    def _decodeLlvmMirInstr(self, MRI: MachineRegisterInfo, bb: MachineBasicBlock, instr: MachineInstr, opc: TargetOpcode) -> LlvmMirInstrFunction:
        decodeOpcodeFn = self._dispatchDict.get(opc)
        if decodeOpcodeFn is not None:
            instrFn = decodeOpcodeFn(self, MRI, instr)
            if opc not in (TargetOpcode.HWTFPGA_BR,
                           TargetOpcode.G_BR,) and  bb.back() == instr:
                # need to handle fall trough for non branches and not taken conditional branches
                fallTroughMb = bb.getFallThrough(False)

                def _opcode_falltrough(nowTime: int, regs: list[HConst]):
                    nextBb = instrFn(nowTime, regs)
                    if nextBb is not None:
                        return nextBb
                    else:
                        nextBb = fallTroughMb
                        waveLog = self.waveLog
                        if waveLog is not None:
                            waveLog.logChange(nowTime, self._simBlockLabel, nextBb, None)
                        self._runBlockPhis(bb, nextBb, waveLog, regs, nowTime)
                        return nextBb

                return _opcode_falltrough
            else:
                return instrFn

        else:
            raise NotImplementedError(instr)

    def _runBlockPhis(self, predBb: MachineBasicBlock, bb: MachineBasicBlock,
                      waveLog: Optional[VcdWriter],
                      regs: list[HConst], nowTime: int):
        """
        Atomically evaluate PHIs at the top of the block.
        """
        assert bb is not None, predBb
        # print(bb.printAsOperand())
        newPhiVals = []
        for phi, v in self._decodedBlockPhis[(predBb, bb)]:
            if isinstance(v, int):
                v = regs[v]

            newPhiVals.append((phi, v))

        for phi, v in newPhiVals:
            # print("_runBlockPhis", phi, v)
            regs[phi] = v

    def _run(self, bb: MachineBasicBlock, regs: list[HConst], wallTime:Optional[int]):
        waveLog = self.waveLog
        timeStep = self.timeStep
        if waveLog is not None:
            _, simCodelineLabel, simTimeLabel, self._simBlockLabel = self._prepareVcdWriter()
        else:
            simCodelineLabel = None
            simTimeLabel = None
            self._simBlockLabel = None
        decodedBlocks = self._decodedBlocks
        bbDecoded = decodedBlocks[bb]
        self.nowTime = nowTime = -timeStep
        while True:
            assert bbDecoded, bb
            for instr, instrDecoded in bbDecoded:
                nowTime += timeStep
                self.nowTime = nowTime
                if waveLog is not None:
                    waveLog.logChange(nowTime, simTimeLabel, nowTime, None)
                    if instr is not None:
                        # instr may be None if this is fallThrough at the end of the block to successor block
                        waveLog.logChange(nowTime, simCodelineLabel, instr, None)

                nextBb = instrDecoded(nowTime, regs)
                if wallTime is not None and nowTime >= wallTime:
                    raise StopSimumulation()
                if nextBb is not None:
                    bb = nextBb
                    bbDecoded = decodedBlocks[nextBb]
                    break

    def run(self, wallTime:Optional[int]=None):
        """
        :param fnArgs: arguments for executed function, generator is used for inputs,
            list is for RAM/ROMs and outputs streams 
        """
        MF = self.MF
        MRI: MachineRegisterInfo = MF.getRegInfo()

        # registers storing value of variables in this interpret
        regs: list[Union[HConst, list[Union[int, HConst]], None]] = {
            i: None for i in range(MRI.getNumVirtRegs())
        }
        LlvmIrInterpret._initGlobalsFromIr(self, MF.getFunction().getParent(), regs)

        waveLog = self.waveLog
        if waveLog is not None:

            def logToWave(_:dict[HConst], i: int, v: HConst):
                if not isinstance(v, HBitsConst):
                    return  # case of HWTFPGA_ARG_GET and similar

                if i in waveLog._idScope:
                    waveLog.logChange(self.nowTime, i, v, None)

            regs = DictWithSetitemListener(regs, logToWave)

        self._decodeBlocks()
        bb: MachineBasicBlock = next(iter(MF))
        assert bb is not None
        self._run(bb, regs, wallTime)

    @classmethod
    def runMirStr(cls,
                  llvm: LlvmCompilationBundle,
                  placeholderObjectSlots: PyObjectPlaceholderList,
                  componentGenerators: ComponentGeneratorDict,
                  nameOfMain: str,
                  mirStr: str,
                  fnArgs: tuple[Generator[Union[int, HConst], None, None], list[HConst], ...],
                  timeStep: int=CLK_PERIOD):
        m = parseMIR(mirStr, nameOfMain, llvm)
        MMI = llvm.getMachineModuleInfo()
        assert m is not None
        llvm.main = m.getFunction(llvm.strCtx.addStringRef(nameOfMain))
        assert llvm.main is not None
        interpret = cls(llvm, placeholderObjectSlots, componentGenerators, fnArgs)

        try:
            interpret.run()
        except SimIoUnderflowErr:
            # some io consumed all the inputs
            pass
        except StopSimumulation:
            # HWTFPGA_RET or similar is asking to stop the simulation
            pass

        return llvm, MMI, m, interpret.MF
