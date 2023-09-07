from itertools import islice
from typing import Tuple, List, Generator, Union

from hwt.code import Concat
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import INT, SLICE
from hwt.hdl.value import HValue
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.llvm.llvmIr import parseMIR, LlvmCompilationBundle, MachineFunction, MachineBasicBlock, MachineInstr, TargetOpcode, MachineOperand, \
    CmpInst, TypeToIntegerType, Register
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel


class SimIoUnerflowErr(Exception):
    """
    This exception is raised when there is not enough data on some IO, it may mean that
    the simulation did finish or simulated function is missing some data
    """


def runLlvmMachineFunction(mf: MachineFunction, args: Tuple[Generator[Union[int, HValue], None, None], List[HValue], ...]):
    """
    :param args: arguments for executed function, generator is used for inputs, list is for RAM/ROMs and outputs streams 
    """
    MRI = mf.getRegInfo()
    regs: List[Union[HValue, List[Union[int, HValue]], None]] = [None for _ in range(MRI.getNumVirtRegs())]
    mb: MachineBasicBlock = mf.getBlockNumbered(0)
    # globalValues: Dict[Register, HValue] = {}
    assert mb is not None
    while True:
        nextMb = None
        ops: List[Union[Register, MachineBasicBlock, int, HValue]] = []
        for mi in mb:
            mi: MachineInstr
            # print(mi)
            opc = mi.getOpcode()
            ops.clear()
            for mo in mi.operands():
                mo: MachineOperand
                if mo.isReg():
                    r = mo.getReg()
                    if mo.isDef():
                        ops.append(r)
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

            elif opc == TargetOpcode.HWTFPGA_CLOAD or opc == TargetOpcode.HWTFPGA_CSTORE:
                val, io, index, cond = ops
                isBlocking = isinstance(cond, int)
                if isBlocking:
                    if not cond:
                        raise AssertionError("Always disabled load or store, this instruction should not exits", mi)
                else:
                    assert cond._is_full_valid(), mi
                    if not cond:
                        if opc == TargetOpcode.HWTFPGA_CLOAD:
                            llt = MRI.getType(val)
                            assert llt.isValid()
                            width = llt.getSizeInBits()
                            t = Bits(width)
                            regs[val.virtRegIndex()] = t.from_py(0, vld_mask=1 << width - 1)
                        continue

                if not isinstance(index, int) or index != 0:
                    raise NotImplementedError(mi)

                if opc == TargetOpcode.HWTFPGA_CLOAD:
                    try:
                        v = next(io)
                    except StopIteration:
                        raise SimIoUnerflowErr("undeflow on io argument", mi)

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
                else:
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
                    raise AssertionError("Indexing on undefined value", mi)
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
                        assert c._is_full_valid(), mi
                        if c:
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
            else:
                op = HlsNetlistAnalysisPassMirToNetlistLowLevel.OPC_TO_OP.get(opc)
                if op  is AllOps.NOT:
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


def runMirStr(mirStr: str, nameOfMain: str, args: list):
    ctx = LlvmCompilationBundle(nameOfMain)
    m = parseMIR(mirStr, nameOfMain, ctx)
    MMI = ctx.getMachineModuleInfo()
    assert m is not None
    f = m.getFunction(ctx.strCtx.addStringRef(nameOfMain))
    assert f is not None
    mf = MMI.getMachineFunction(f)
    assert mf is not None
    try:
        runLlvmMachineFunction(mf, args)
    except SimIoUnerflowErr:
        pass

    return ctx, MMI, m, mf
