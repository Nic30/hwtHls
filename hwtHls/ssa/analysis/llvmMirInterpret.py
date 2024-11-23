from datetime import datetime
from io import StringIO
from itertools import islice
from typing import Tuple, List, Generator, Union, Optional, Dict, Iterable, Any, \
    Callable

from hwt.code import Concat
from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import INT, SLICE
from hwt.math import log2ceil
from hwt.pyUtils.arrayQuery import grouper
from hwtHls.code import OP_CTLZ, OP_CTTZ, OP_CTPOP, fshl, fshr, OP_SHL, OP_ASHR, \
    OP_LSHR, OP_FSHL, OP_FSHR
from hwtHls.llvm.llvmIr import parseMIR, LlvmCompilationBundle, MachineFunction, \
    MachineBasicBlock, MachineInstr, TargetOpcode, MachineOperand, \
    CmpInst, TypeToIntegerType, Register, LLVMStringContext, MachineRegisterInfo, \
    GlobalValue, ValueToGlobalValue, ValueToConstantArray, ValueToConstantDataArray, \
    ConstantDataArray, TypeToArrayType, ArrayType
from hwtHls.ssa.analysis.llvmIrInterpret import VcdLlvmIrCodelineFormatter, \
    VcdLlvmIrSimTimeFormatter, VcdLlvmIrBBFormatter, SimIoUnderflowErr, _prepareWaveWriterTopIo, \
    LlvmIrInterpret, PtrAddrTuple
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtSimApi.constants import CLK_PERIOD
from hwtSimApi.triggers import StopSimumulation
from pyDigitalWaveTools.vcd.common import VCD_SIG_TYPE
from pyDigitalWaveTools.vcd.value_format import LogValueFormatter, \
    VcdBitsFormatter
from pyDigitalWaveTools.vcd.writer import VcdWriter
from pyMathBitPrecise.bit_utils import mask


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

        self._dispatchDict: Dict[int, Callable] = {
            TargetOpcode.HWTFPGA_ARG_GET.value: self._opcode_HWTFPGA_ARG_GET,
            TargetOpcode.HWTFPGA_CLOAD.value: self._opcode_HWTFPGA_CLOAD,
            TargetOpcode.G_LOAD.value: self._opcode_G_LOAD,
            TargetOpcode.HWTFPGA_CSTORE.value: self._opcode_HWTFPGA_CSTORE,
            TargetOpcode.G_STORE.value: self._opcode_G_STORE,
            TargetOpcode.HWTFPGA_EXTRACT.value: self._opcode_HWTFPGA_EXTRACT,
            TargetOpcode.G_EXTRACT.value: self._opcode_G_EXTRACT,
            TargetOpcode.HWTFPGA_MERGE_VALUES.value: self._opcode_HWTFPGA_MERGE_VALUES,
            TargetOpcode.HWTFPGA_MUX.value: self._opcode_HWTFPGA_MUX,
            TargetOpcode.G_SELECT.value: self._opcode_G_SELECT,
            TargetOpcode.G_FSHL.value: self._opcode_G_FSHL,
            TargetOpcode.G_FSHR.value: self._opcode_G_FSHR,
            TargetOpcode.COPY.value: self._opcode_COPY,
            TargetOpcode.G_ICMP.value: self._opcode_G_ICMP,
            TargetOpcode.HWTFPGA_ICMP.value: self._opcode_G_ICMP,
            TargetOpcode.HWTFPGA_IMPLICIT_DEF.value: self._opcode_HWTFPGA_IMPLICIT_DEF,
            TargetOpcode.G_IMPLICIT_DEF.value: self._opcode_G_IMPLICIT_DEF,
            TargetOpcode.G_CONSTANT.value: self._opcode_G_CONSTANT,
            TargetOpcode.G_GLOBAL_VALUE.value: self._opcode_G_GLOBAL_VALUE,
            TargetOpcode.HWTFPGA_GLOBAL_VALUE.value: self._opcode_G_GLOBAL_VALUE,
            TargetOpcode.G_TRUNC.value: self._opcode_G_TRUNC,
            TargetOpcode.G_ZEXT.value: self._opcode_G_ZEXT,
            TargetOpcode.G_SEXT.value: self._opcode_G_SEXT,
            TargetOpcode.G_PTR_ADD.value: self._opcode_G_PTR_ADD,
        }

        for opc, op in HlsNetlistAnalysisPassMirToNetlistLowLevel.OPC_TO_OP.items():
            self._dispatchDict[opc.value] = self._makeOpcodeFunction(opc, op)
        self.fnArgs: Optional[Tuple] = None

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

                        width = llt.getScalarSizeInBits()
                        assert reg.isVirtual(), reg
                        regI = reg.virtRegIndex()
                        name = f"%{regI}"
                        fnScope.addVar(regI, name, VCD_SIG_TYPE.WIRE, width, VcdBitsFormatter())

                codelineOffset += 2

        waveLog.enddefinitions()
        return instrCodeline, simCodelineLabel, simTimeLabel, simBlockLabel

    @staticmethod
    def _runBlockPhis(MRI: MachineRegisterInfo, predBb: MachineBasicBlock, bb: MachineBasicBlock, waveLog: Optional[VcdWriter], regs:List[Union[HConst, List[Union[int, HConst]], None]], nowTime: int):
        """
        Atomically evaluate PHIs at the top of the block.
        """
        newPhiVals: List[Tuple[Register, HConst]] = []
        for mi in bb:
            opc = mi.getOpcode()
            if opc != TargetOpcode.G_PHI and opc != TargetOpcode.PHI:
                break
            vOp = None
            res = None
            for MO in mi.operands():
                MO: MachineOperand
                if MO.isMBB():
                    if MO.getMBB() == predBb:
                        if vOp.isReg():
                            r = vOp.getReg()
                            if vOp.isDef():
                                res = r
                            elif vOp.isUndef():
                                llt = MRI.getType(vOp.getReg())
                                assert llt.isValid()
                                width = llt.getScalarSizeInBits()
                                res = HBits(width).from_py(None)
                            else:
                                res = regs[r.virtRegIndex()]

                        elif vOp.isCImm():
                            c = vOp.getCImm()
                            v = c.getValue()
                            t = TypeToIntegerType(c.getType())
                            if t is None:
                                raise NotImplementedError(mi, vOp)
                            pyT = HBits(t.getBitWidth())
                            v = int(v)
                            if v < 0:  # convert to unsigned
                                v = pyT.all_mask() + v + 1
                            res = pyT.from_py(v)
                        newPhiVals.append((mi.getOperand(0).getReg(), res))
                        break
                vOp = MO
            if res is None:
                raise AssertionError("Predecessor was not found in phi operands", predBb, mi)

        for phiDst, v in newPhiVals:
            regs[phiDst.virtRegIndex()] = v

    def _makeOpcodeFunction(self, opcode: TargetOpcode, op: HOperatorDef):
        """
        Create opcode function for rest of the operands
        """
        if op in (HwtOps.NOT, OP_CTLZ, OP_CTTZ, OP_CTPOP):

            def _opcode_HWTFPGA_NOT_and_bitcounts(MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
                dst, src0 = ops
                if src0._dtype.signed is not None:
                    src0 = src0.cast_sign(None)
                res = op._evalFn(src0)
                regs[dst.virtRegIndex()] = res

            return _opcode_HWTFPGA_NOT_and_bitcounts

        elif op in (OP_SHL, OP_ASHR, OP_LSHR):

            if opcode in (TargetOpcode.G_SHL, TargetOpcode.G_ASHR, TargetOpcode.G_LSHR):

                def _opcode_shift(MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
                    dst, src0, src1 = ops
                    if src0._dtype.signed is not None:
                        src0 = src0.cast_sign(None)
                    if src1._dtype.signed is not None:
                        src1 = src1.cast_sign(None)
                    dstTy = MRI.getType(dst)
                    assert dstTy.isValid(), mi
                    width = dstTy.getScalarSizeInBits()
                    src1 = src1[log2ceil(width + 1):]  # truncate shiftAmount
                    res = op._evalFn(src0, src1)
                    regs[dst.virtRegIndex()] = res

            else:
                assert opcode in (TargetOpcode.HWTFPGA_SHL, TargetOpcode.HWTFPGA_ASHR, TargetOpcode.HWTFPGA_LSHR), opcode

                def _opcode_shift(MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
                    dst, src0, sh, width = ops
                    if src0._dtype.signed is not None:
                        src0 = src0.cast_sign(None)
                    if sh._dtype.signed is not None:
                        sh = sh.cast_sign(None)
                    assert sh._dtype.bit_length() == log2ceil(width + 1), (mi, sh._dtype.bit_length(), log2ceil(width + 1))
                    res = op._evalFn(src0, sh)
                    regs[dst.virtRegIndex()] = res

            return _opcode_shift

        elif op in (OP_FSHL, OP_FSHR):
            if opcode in (TargetOpcode.G_FSHL, TargetOpcode.G_FSHR):

                def _opcode_funel_shift(MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
                    dst, src0, src1, sh = ops
                    if src0._dtype.signed is not None:
                        src0 = src0.cast_sign(None)
                    if src1._dtype.signed is not None:
                        src1 = src1.cast_sign(None)
                    if sh._dtype.signed is not None:
                        sh = sh.cast_sign(None)
                    dstTy = MRI.getType(dst)
                    assert dstTy.isValid(), mi
                    width = dstTy.getScalarSizeInBits()
                    sh = sh[log2ceil(width + 1):]  # truncate shiftAmount
                    res = op._evalFn(src0, src1, sh)
                    regs[dst.virtRegIndex()] = res

            else:
                assert opcode in (TargetOpcode.HWTFPGA_FSHL, TargetOpcode.HWTFPGA_FSHR), opcode

                def _opcode_funel_shift(MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
                    dst, src0, src1, sh, width = ops
                    if src0._dtype.signed is not None:
                        src0 = src0.cast_sign(None)
                    if src1._dtype.signed is not None:
                        src1 = src1.cast_sign(None)
                    if sh._dtype.signed is not None:
                        sh = sh.cast_sign(None)
                    assert sh._dtype.bit_length() == log2ceil(width + 1), (mi, sh._dtype.bit_length(), log2ceil(width + 1))
                    res = op._evalFn(src0, src1, sh)
                    regs[dst.virtRegIndex()] = res

            return _opcode_funel_shift

        else:

            def _opcode_arithmetic(MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
                dst, src0, src1 = ops
                if src0._dtype.signed is not None:
                    src0 = src0.cast_sign(None)
                if src1._dtype.signed is not None:
                    src1 = src1.cast_sign(None)
                res = op._evalFn(src0, src1)
                regs[dst.virtRegIndex()] = res

            return _opcode_arithmetic

    def _opcode_HWTFPGA_ARG_GET(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, i = ops
        assert dst.virtRegIndex() == i
        assert regs[i] is None, regs[i]
        regs[i] = self.fnArgs[i]

    def _opcode_HWTFPGA_CLOAD(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        val, io, index, width, cond = ops
        isBlocking = isinstance(cond, int)
        if isBlocking:
            if not cond:
                raise AssertionError("Always disabled load or store, this instruction should not exits", mi)
        else:
            assert cond._is_full_valid(), mi
            if not cond:
                t = HBits(width)
                regs[val.virtRegIndex()] = t.from_py(0, vld_mask=1 << width - 1)
                return

        if not isinstance(index, int) or index != 0:
            assert isinstance(io, GlobalValue), io
            v = LlvmIrInterpret._getItemFromLocalPointer(regs, PtrAddrTuple((io, index)), width, mi)
        else:
            try:
                v = next(io)
            except StopIteration:
                raise SimIoUnderflowErr("underflow on io argument", mi)

            t = HBits(width)
            if isinstance(v, HConst):
                if v._dtype != t:
                    assert v._dtype.bit_length() == t.bit_length(), (mi, v._dtype, t, v)
                    v = v._reinterpret_cast(t)
            else:
                v = t.from_py(v)
        regs[val.virtRegIndex()] = v

    def _opcode_G_LOAD(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, io = ops
        llt = MRI.getType(dst)
        assert llt.isValid()
        width = llt.getScalarSizeInBits()
        if isinstance(io, (GlobalValue, PtrAddrTuple)):
            # load from local memory
            v = LlvmIrInterpret._getItemFromLocalPointer(regs, io, width, mi)
        else:
            # load from IO
            try:
                v = next(io)
            except StopIteration:
                raise SimIoUnderflowErr("underflow on io argument", mi)

            t = HBits(width)
            if isinstance(v, HConst):
                if v._dtype != t:
                    assert v._dtype.bit_length() == t.bit_length(), (mi, v._dtype, t, v)
                    v = v._reinterpret_cast(t)
            else:
                v = t.from_py(v)
        regs[dst.virtRegIndex()] = v

    def _opcode_HWTFPGA_CSTORE(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        val, io, index, width, cond = ops
        isBlocking = isinstance(cond, int)
        if isBlocking:
            if not cond:
                raise AssertionError("Always disabled load or store, this instruction should not exits", mi)
        else:
            assert cond._is_full_valid(), mi
            if not cond:
                return

        if not isinstance(index, int) or index != 0:
            raise NotImplementedError(mi)

        io.append(val)

    def _opcode_G_STORE(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        val, io = ops
        io.append(val)

    def _opcode_HWTFPGA_EXTRACT(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, src, srcWidth, index, width = ops
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
        if not isinstance(src, HConst):
            raise AssertionError(mi, src)
        assert src._dtype.bit_length() == srcWidth, (src._dtype.bit_length() == srcWidth)
        res = src[index]
        assert res is not None, mi
        regs[dst.virtRegIndex()] = res

    def _opcode_G_EXTRACT(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, src, index = ops
        width = MRI.getType(dst).getScalarSizeInBits()
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

    def _opcode_HWTFPGA_MERGE_VALUES(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst = ops[0]
        # dst src{N}, width{N} - lowest bits first
        assert (len(ops) - 1) % 2 == 0, ops
        half = (len(ops) - 1) // 2
        res = Concat(*reversed(ops[1:half + 1]))
        regs[dst.virtRegIndex()] = res

    def _opcode_HWTFPGA_MUX(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
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

    def _opcode_G_SELECT(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, c, srcT, srcF = ops
        if not c._is_full_valid():
            res = srcT._dtype.from_py(None)
        elif c:
            res = srcT
        else:
            res = srcF
        regs[dst.virtRegIndex()] = res

    def _opcode_G_FSHL(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, a, b, c = ops
        regs[dst.virtRegIndex()] = fshl(a, b, c)

    def _opcode_G_FSHR(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, a, b, c = ops
        regs[dst.virtRegIndex()] = fshr(a, b, c)

    def _opcode_COPY(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, src = ops
        regs[dst.virtRegIndex()] = src

    def _opcode_G_ICMP(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, pred, src0, src1 = ops
        op = HlsNetlistAnalysisPassMirToNetlistLowLevel.CMP_PREDICATE_TO_OP[pred]
        if src0._dtype.signed is not None:
            src0 = src0.cast_sign(None)
        if src1._dtype.signed is not None:
            src1 = src1.cast_sign(None)
        res = op._evalFn(src0, src1)
        regs[dst.virtRegIndex()] = res

    def _opcode_HWTFPGA_IMPLICIT_DEF(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, width = ops
        t = HBits(width)
        regs[dst.virtRegIndex()] = t.from_py(None)

    def _opcode_G_IMPLICIT_DEF(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, = ops
        llt = MRI.getType(ops[0])
        assert llt.isValid(), mi
        t = HBits(llt.getScalarSizeInBits())
        regs[dst.virtRegIndex()] = t.from_py(None)

    def _opcode_G_CONSTANT(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, val = ops
        regs[dst.virtRegIndex()] = val

    def _opcode_G_GLOBAL_VALUE(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, val = ops
        regs[dst.virtRegIndex()] = ValueToGlobalValue(val)

    def _opcode_G_TRUNC(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, val = ops
        llt = MRI.getType(dst)
        assert llt.isValid(), mi
        regs[dst.virtRegIndex()] = val[llt.getScalarSizeInBits():]

    def _opcode_G_ZEXT(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, val = ops
        llt = MRI.getType(dst)
        assert llt.isValid(), mi
        width = val._dtype.bit_length()
        newWidth = llt.getScalarSizeInBits()
        regs[dst.virtRegIndex()] = HBits(newWidth - width).from_py(0)._concat(val)

    def _opcode_G_SEXT(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, val = ops
        llt = MRI.getType(dst)
        assert llt.isValid(), mi
        width = val._dtype.bit_length()
        if width == 1:
            msb = val
        else:
            msb = val[width - 1]

        newWidth = llt.getScalarSizeInBits()
        padBits = newWidth - width
        if msb._is_full_valid():
            if msb:
                pad = mask(padBits)
            else:
                pad = 0
        else:
            pad = None

        regs[dst.virtRegIndex()] = HBits(padBits).from_py(pad)._concat(val)

    def _opcode_G_PTR_ADD(self, MRI: MachineRegisterInfo, regs: List[HConst], mi: MachineInstr, ops: list):
        dst, op0, op1 = ops

        if isinstance(op0, PtrAddrTuple):
            _base, index = op0
        else:
            _base = op0
            index = 0
        if isinstance(_base, GlobalValue):
            base = _base
        else:
            base = ValueToGlobalValue(_base)
            assert base is not None, _base

        baseMem = base.getOperand(0)  # extract data from GlobalValue
        # scale op1 from uint8_t* to native type of array
        arrVal = ValueToConstantArray(baseMem)
        if arrVal is None:
            arrVal = ValueToConstantDataArray(baseMem)
            assert arrVal, (mi, baseMem)
            arrVal: ConstantDataArray
            arrTy: ArrayType = TypeToArrayType(arrVal.getType())
            assert arrTy, baseMem
            elementTy = arrTy.getElementType()
        else:
            elementTy = arrVal.getOperand(0).getType()
        elementWidth = elementTy.getScalarSizeInBits()
        elementSize = elementWidth // 8
        if elementWidth > elementSize * 8:
            elementSize += 1
        op1 = op1 // elementSize

        index = op1 + index

        assert isinstance(base, GlobalValue), base
        regs[dst.virtRegIndex()] = PtrAddrTuple((base, index))

    def run(self, fnArgs: Tuple[Generator[Union[int, HConst], None, None], List[HConst], ...],
            wallTime:Optional[int]=None):
        """
        :param fnArgs: arguments for executed function, generator is used for inputs,
            list is for RAM/ROMs and outputs streams 
        """
        self.fnArgs = fnArgs
        MF = self.MF
        timeStep = self.timeStep
        MRI: MachineRegisterInfo = MF.getRegInfo()
        waveLog = self.waveLog
        timeNow = -timeStep
        regs: List[Union[HConst, List[Union[int, HConst]], None]] = [None for _ in range(MRI.getNumVirtRegs())]
        if waveLog is not None:
            _, simCodelineLabel, simTimeLabel, simBlockLabel = self._prepareVcdWriter()

            def logToWave(_:List[HConst], i: int, v: HConst):
                if not isinstance(v, HConst):
                    return  # case of HWTFPGA_ARG_GET and similar

                if i in waveLog._idScope:
                    waveLog.logChange(timeNow, i, v, None)

            regs = ListWithSetitemListener(regs, logToWave)
        else:
            simCodelineLabel = None
            simTimeLabel = None
            simBlockLabel = None

        mb: MachineBasicBlock = next(iter(MF))
        # globalValues: Dict[Register, HConst] = {}

        assert mb is not None
        while True:
            timeNow += timeStep
            if wallTime is not None and wallTime <= timeNow:
                raise StopSimumulation()

            if waveLog is not None:
                waveLog.logChange(timeNow, simBlockLabel, mb, None)
            nextMb = None
            ops: List[Union[Register, MachineBasicBlock, int, HConst]] = []
            PHI_OPS = (TargetOpcode.G_PHI.value, TargetOpcode.PHI.value)
            for mi in mb:
                mi: MachineInstr
                # print(mi)
                opc = mi.getOpcode()
                if opc in PHI_OPS:
                    # this should be already evaluated
                    continue

                if waveLog is not None:
                    waveLog.logChange(timeNow, simTimeLabel, timeNow, None)
                    waveLog.logChange(timeNow, simCodelineLabel, mi, None)

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
                            width = llt.getScalarSizeInBits()
                            ops.append(HBits(width).from_py(None))
                        else:
                            v = regs[r.virtRegIndex()]
                            if v is None:
                                llt = MRI.getType(r)
                                assert llt.isValid(), (r, r.virtRegIndex(), "This may happen if use is not dominated by any def")
                                width = llt.getScalarSizeInBits()
                                v = HBits(width).from_py(None)
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
                            raise NotImplementedError(mi, mo)
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
                        raise NotImplementedError(mi, mo)

                opcodeFn = self._dispatchDict.get(opc)
                if opcodeFn is not None:
                    opcodeFn(MRI, regs, mi, ops)
                elif opc == TargetOpcode.HWTFPGA_BR or opc == TargetOpcode.G_BR:
                    nextMb = ops[0]
                    self._runBlockPhis(MRI, mb, nextMb, waveLog, regs, timeNow)
                elif opc == TargetOpcode.HWTFPGA_BRCOND or opc == TargetOpcode.G_BRCOND:
                    cond, _mb = ops
                    assert cond._is_full_valid(), (mi, "Branch condition must be valid")
                    if cond:
                        nextMb = _mb
                        self._runBlockPhis(MRI, mb, nextMb, waveLog, regs, timeNow)
                        break
                elif opc == TargetOpcode.HWTFPGA_RET:
                    return
                else:
                    raise NotImplementedError(mi)

            if nextMb is None:
                nextMb = mb.getFallThrough(False)
            self._runBlockPhis(MRI, mb, nextMb, waveLog, regs, timeNow)
            mb = nextMb

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
