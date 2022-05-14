from itertools import islice
from typing import Dict, Union, Tuple, List

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import Concat
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.defs import SLICE, INT
from hwt.hdl.value import HValue
from hwt.math import log2ceil
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.hlsStreamProc.statementsIo import HlsStreamProcRead, \
    HlsStreamProcWrite
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.llvm.llvmIr import LLVMContext, Module, IRBuilder, LLVMStringContext, IntegerType, Value, \
    Type, FunctionType, Function, VectorOfTypePtr, BasicBlock, Argument, PointerType, TypeToPointerType, \
    ConstantInt, APInt, verifyFunction, verifyModule, TypeToIntegerType, LoadInst, StoreInst, Instruction, \
    UserToInstruction, ValueToInstruction, Use, ValueToConstantInt, InstructionToICmpInst, ICmpInst, CmpInst, \
    PHINode, InstructionToPHINode
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtHls.ssa.value import SsaValue
from ipCorePackager.constants import INTF_DIRECTION
from pyMathBitPrecise.bit_utils import ValidityError, mask

SIGNED_CMP_OPS = (
    CmpInst.Predicate.ICMP_SGT,
    CmpInst.Predicate.ICMP_SGE,
    CmpInst.Predicate.ICMP_SLT,
    CmpInst.Predicate.ICMP_SLE,
)


class FromLlvmIrTranslator():
    """
    :ivar argToIntf: a dictionary which maps the top function argument to an Interface on hardware level
    :ivar newBlocksBegin: translated blocks
    :ivar newBlocksEnd: ends of translated blocks which may be a different block than begin
        because the block may require some blocks to be generated inside
    """

    def __init__(self, hls: HlsStreamProc, ssaCtx: SsaContext, topIo: Dict[Interface, INTF_DIRECTION]):
        self.ssaCtx = ssaCtx
        self.hls = hls
        self.topIo = topIo
        self.argToIntf: Dict[Argument, Interface] = {}
        self.newBlocksBegin: Dict[BasicBlock, SsaBasicBlock] = {}
        self.newBlocksEnd: Dict[BasicBlock, SsaBasicBlock] = {}
        self.newValues: Dict[Value, Union[SsaValue, HValue]] = {}

    def _translateType(self, t):
        it = TypeToIntegerType(t)
        if it is not None:
            it: IntegerType
            return Bits(it.getBitWidth())
        else:
            raise NotImplementedError(t)

    def _translateExpr(self, v: Union[Value, Use]):
        assert isinstance(v, (Value, Use)), v
        if isinstance(v, Use):
            v = v.get()
        if not isinstance(v, Value):
            c = None
        else:
            c = ValueToConstantInt(v)

        if c is not None:
            val = int(c.getValue())
            t = self._translateType(v.getType())
            if not t.signed and val < 0:
                val = t.all_mask() + val + 1
            return t.from_py(val)

        return self.newValues[v]  # if not in this dict. the value was not defined before use

    def _translateSignedExpr(self, v):
        v = self._translateExpr(v)
        if v._dtype.signed:
            return v
        elif isinstance(v, HValue):
            v: HValue
            return v._convSign(True)
        else:
            resT = Bits(v._dtype.bit_length(), signed=True)
            castInstr = SsaInstr(v.block.ctx, resT, AllOps.BitsAsSigned, [v])
            v.block.appendInstruction(castInstr)
            return castInstr

    def translateBasicBlock(self, block: BasicBlock):
        newBlock: SsaBasicBlock = self.newBlocksBegin[block]
        for instr in block:
            instr: Instruction
            op = instr.getOpcode()
            if op == Instruction.MemoryOps.Load.value:
                a = tuple(instr.iterOperands())[0].get()
                io = self.argToIntf[a]
                res_t = self._translateType(instr.getType())
                _res_t = ToLlvmIrTranslator._getNativeInterfaceType(io)
                if isinstance(_res_t, Bits):
                    if _res_t.signed is not None:
                        res_t = Bits(res_t.bit_length(), io._dtype.signed)
                # else:
                #    res_t = Bits(res_t.bit_length())
                    
                _instr = HlsStreamProcRead(self.hls, io, res_t)

            elif op == Instruction.MemoryOps.Store.value:
                ops = tuple(o.get() for o in instr.iterOperands())
                src = self._translateExpr(ops[0])
                io = self.argToIntf[ops[1]]
                _instr = HlsStreamProcWrite(self.hls, src, io)

            else:
                BinaryOps = Instruction.BinaryOps
                if op == BinaryOps.Shl.value:
                    # <<, all concatenations and bit slices should be extracted, this must be a non constant shift
                    mainVar, sh = (self._translateExpr(v) for v in instr.iterOperands())
                    assert not isinstance(sh, BitsVal), (sh, "If this was constant it should already be converted")
                    raise NotImplementedError("Non constant shift", instr)

                elif op == BinaryOps.LShr.value:
                    raise NotImplementedError(instr, "Should be converted to hwtHls.bitRangeGet")

                elif op == BinaryOps.AShr.value:
                    raise NotImplementedError(instr)

                elif op == Instruction.CastOps.Trunc:
                    raise NotImplementedError(instr, "Should be converted to hwtHls.bitConcat")
                
                elif op == Instruction.CastOps.ZExt.value:
                    res_t = self._translateType(instr.getType())
                    a, = (self._translateExpr(o) for o in instr.iterOperands())
                    _instr = SsaInstr(self.ssaCtx, res_t, AllOps.CONCAT,
                                      [Bits(res_t.bit_length() - a._dtype.bit_length()).from_py(0), a])

                elif op == Instruction.TermOps.Br.value:
                    assert not newBlock.successors.targets
                    ops = tuple(instr.iterOperands())
                    if len(ops) == 1:
                        newBlock.successors.addTarget(None, self.newBlocksBegin[ops[0].get()])
                    else:
                        c, sucF, sucT = (o.get() for o in ops)
                        newBlock.successors.addTarget(self._translateExpr(c), self.newBlocksBegin[sucT])
                        newBlock.successors.addTarget(None, self.newBlocksBegin[sucF])
                    continue
                elif op == Instruction.TermOps.Ret.value:
                    continue
                elif op == Instruction.TermOps.Switch.value:
                    ops = tuple(instr.iterOperands())
                    opLen = len(ops)
                    switchOn, defaultDst = islice(ops, 0, 2)
                    switchOn = self._translateExpr(switchOn)
                    assert opLen > 2 and opLen % 2 == 0, ops
                    condDst: List[Tuple[SsaValue, SsaBasicBlock]] = []
                    exprBuilder = SsaExprBuilder(newBlock)
                    for v, dst in grouper(2, islice(ops, 2, None)):
                        v = self._translateExpr(v)
                        v = exprBuilder._binaryOp(switchOn, AllOps.EQ, v.cast_sign(switchOn._dtype.signed))
                        condDst.append((v, self.newBlocksBegin[dst.get()]))
                    condDst.append((None, self.newBlocksBegin[defaultDst.get()]))

                    for c, dst in condDst:
                        newBlock.successors.addTarget(c, dst)
                    continue

                elif op == Instruction.OtherOps.PHI.value:
                    res_t = self._translateType(instr.getType())
                    _instr = SsaPhi(self.ssaCtx, res_t)
                    newBlock.appendPhi(_instr)
                    self.newValues[instr] = _instr
                    continue
                elif op == Instruction.OtherOps.Call:
                    ops = list(instr.iterOperands())
                    fn = ops.pop().get()
                    fn_name = fn.getName().str()
                    if fn_name == 'llvm.fshl.i2':
                        # funnel shift left
                        ops = tuple(self._translateExpr(v) for v in ops)
                        a, b, sh = ops
                        w = a._dtype.bit_length()
                        _instr = SsaInstr(self.ssaCtx, Bits(2 * w),
                                          AllOps.CONCAT, [a, b])
                        newBlock.appendInstruction(_instr)
                        if isinstance(sh, BitsVal):
                            sh = int(sh)
                            _instr = SsaInstr(self.ssaCtx, a._dtype, AllOps.CONCAT, [_instr, SLICE.from_py(slice(2 * w - sh, w - sh, -1))])
                        else:
                            raise NotImplementedError(instr)

                    elif fn_name.startswith("hwtHls.bitRangeGet"):
                        base, lowBitI, _ = list(instr.iterOperands())
                        base = self._translateExpr(base)
                        lowBitI = self._translateExpr(lowBitI)
                        res_t = self._translateType(instr.getType())
                        res_w = res_t.bit_length()
                        if res_w == 1:
                            if isinstance(lowBitI, BitsVal) and lowBitI._dtype != INT:
                                _lowBitI = int(lowBitI)
                                if _lowBitI >= 0 and _lowBitI < 2 ** (INT.bit_length() - 1):
                                    lowBitI = INT.from_py(_lowBitI)  # convert directly to int to avoid unnecessary casts
                            _instr = SsaInstr(self.ssaCtx, res_t, AllOps.INDEX, [base, lowBitI])
                        else:
                            res_w = res_t.bit_length()
                            w = base._dtype.bit_length()
                            if isinstance(lowBitI, BitsVal):
                                # static selection of bit range
                                lowBitI = int(lowBitI)
                                index = SLICE.from_py(slice(lowBitI + res_w, lowBitI, -1))
                                _instr = SsaInstr(self.ssaCtx, res_t, AllOps.INDEX, [base, index])
                            else:
                                # mux using bit select
                                noOfValues = min(w // int(res_t.bit_length()), 2 ** lowBitI._dtype.bit_length())
                                eb = SsaExprBuilder(newBlock, len(newBlock.body))
                                # [todo] there is a premise that the index selects non overlapping slices, this may not be guaranted
                                index = eb._binaryOp(lowBitI, AllOps.INDEX, SLICE.from_py(slice(lowBitI._dtype.bit_length(),
                                                                                              log2ceil(res_w - 1),
                                                                                              -1)))
                                caseVals = []
                                for last, i in iter_with_last(range(noOfValues)):
                                    if last:
                                        c = None
                                    else:
                                        c = eb._binaryOp(index, AllOps.EQ, index._dtype.from_py(i))
                                    caseVals.append(c)
                                
                                caseBlocks, sequel = eb.insertBlocks(caseVals)
                                sequel: SsaBasicBlock
                                phi = SsaPhi(sequel.ctx, res_t)
                                for i, c, br in zip(range(noOfValues), caseVals, caseBlocks):
                                    br: SsaBasicBlock
                                    sel = SsaInstr(self.ssaCtx, res_t, AllOps.INDEX, [base, SLICE.from_py(slice(res_w * (i + 1), res_w * i, -1))])
                                    newBlock.appendInstruction(sel)
                                    phi.appendOperand(sel, br)
                                sequel.appendPhi(phi)
                                
                                self.newValues[instr] = phi
                                newBlock = self.newBlocksEnd[block] = sequel
                                continue

                    elif fn_name.startswith("hwtHls.bitConcat"):
                        res_t = self._translateType(instr.getType())
                        ops = list(self._translateExpr(v) for v in ops)
                        assert len(ops) >= 2, ops
                        while True:
                            # take values on the righ (LSB) side and concatenate them
                            o0 = ops.pop()
                            o1 = ops.pop()
                            while ops and isinstance(o1, BitsVal) and isinstance(ops[-1], BitsVal):
                                # reduce all prefix constant to a single number
                                o1 = Concat(ops.pop(), o1)
                                
                            _instr = SsaInstr(self.ssaCtx, Bits(o0._dtype.bit_length() + o1._dtype.bit_length()), AllOps.CONCAT, [o1, o0])
                            newBlock.appendInstruction(_instr)
                            if ops:
                                ops.append(_instr)
                            else:
                                break
                        assert _instr._dtype == res_t, (instr, _instr)
                        self.newValues[instr] = _instr
                        continue
                    else:
                        raise NotImplementedError(instr)
                    
                else:
                    res_t = self._translateType(instr.getType())
                    translateOperand = self._translateExpr
                    if op == Instruction.OtherOps.ICmp:
                        instr: ICmpInst = InstructionToICmpInst(instr)
                        P = CmpInst.Predicate
                        p = instr.getPredicate()
                        operator = {
                            P.ICMP_EQ:AllOps.EQ,
                            P.ICMP_NE:AllOps.NE,
                            P.ICMP_UGT:AllOps.GT,
                            P.ICMP_UGE:AllOps.GE,
                            P.ICMP_ULT:AllOps.LT,
                            P.ICMP_ULE:AllOps.LE,
                            P.ICMP_SGT:AllOps.GT,
                            P.ICMP_SGE:AllOps.GE,
                            P.ICMP_SLT:AllOps.LT,
                            P.ICMP_SLE:AllOps.LE,
                        }[p]
                        if p in SIGNED_CMP_OPS:
                            translateOperand = self._translateSignedExpr
                    else:
                        operator = {
                            BinaryOps.Add.value: AllOps.ADD,
                            # BinaryOps.FAdd
                            BinaryOps.Sub.value: AllOps.SUB,
                            # BinaryOps.FSub
                            BinaryOps.Mul.value: AllOps.MUL,
                            # BinaryOps.FMul
                            BinaryOps.UDiv.value: AllOps.DIV,
                            BinaryOps.SDiv.value: AllOps.DIV,
                            # BinaryOps.FDiv
                            # BinaryOps.URem
                            # BinaryOps.SRem
                            # BinaryOps.FRem
                            BinaryOps.And.value: AllOps.AND,
                            BinaryOps.Or.value: AllOps.OR,
                            BinaryOps.Xor.value: AllOps.XOR,
                            Instruction.OtherOps.Select.value: AllOps.TERNARY,
                        }.get(op, None)

                        if operator is None:
                            raise NotImplementedError(instr)

                    ops = [translateOperand(o) for o in instr.iterOperands()]
                    op1 = 0
                    if operator is AllOps.XOR and isinstance(ops[1], HValue):
                        try:
                            op1 = int(ops[1])
                        except ValidityError:
                            pass
                        if op1 == mask(res_t.bit_length()):
                            operator = AllOps.NOT
                            ops = [ops[0], ]
                    _instr = SsaInstr(self.ssaCtx, res_t, operator, ops)

            self.newValues[instr] = _instr
            newBlock.appendInstruction(_instr)

    def translateBasicBlockPhis(self, block: BasicBlock):
        newBlock = self.newBlocksBegin[block]
        for phi, newPhi in zip(block, newBlock.phis):
            phi: PHINode = InstructionToPHINode(phi)
            newPhi: SsaPhi
            for v, b in zip(phi.iterOperands(), phi.iterBlocks()):
                v = v.get()
                assert b is not None
                newPhi.appendOperand(self._translateExpr(v), self.newBlocksEnd[b])

    def translate(self, main: Function):
        # resolve the argument to io interface mapping
        ioByName: Dict[str, Interface] = {}
        for i in self.topIo.keys():
            cur = ioByName.setdefault(getSignalName(i), i)
            assert cur is i, (i, cur)

        argToIntf = self.argToIntf
        for arg in main.args():
            name = arg.getName().str()
            argToIntf[arg] = ioByName[name]

        # generate new blocks, we need to do this in advance because we need targets for jumps
        newBlocksBegin = self.newBlocksBegin
        newBlocksEnd = self.newBlocksEnd
        start = None
        for bb in main:
            bb: BasicBlock
            newBlocksEnd[bb] = newBlocksBegin[bb] = newBb = SsaBasicBlock(self.ssaCtx, bb.getName().str())
            if start is None:
                start = newBb

        for bb in main:
            bb: BasicBlock
            self.translateBasicBlock(bb)

        # fill phi operands
        for bb in main:
            bb: BasicBlock
            self.translateBasicBlockPhis(bb)

        return start


class SsaPassFromLlvm():

    def apply(self, hls: "HlsStreamProc", to_ssa: AstToSsa):
        toLlvm: ToLlvmIrTranslator = to_ssa.start
        fromLlvm = FromLlvmIrTranslator(hls, to_ssa.ssaCtx, toLlvm.topIo)
        # mf = toLlvm.llvm.getMachineFunction(toLlvm.llvm.main)
        # print(mf)
        to_ssa.start = fromLlvm.translate(toLlvm.llvm.main)

