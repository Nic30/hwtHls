from typing import Dict, Union

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.hlsStreamProc.statements import HlsStreamProcRead, \
    HlsStreamProcWrite
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.llvm.toLlvm import LLVMContext, Module, IRBuilder, LLVMStringContext, IntegerType, Value, \
    Type, FunctionType, Function, VectorOfTypePtr, BasicBlock, Argument, PointerType, TypeToPointerType, \
    ConstantInt, APInt, runOpt, verifyFunction, verifyModule, TypeToIntegerType, LoadInst, StoreInst, Instruction, \
    UserToInstruction, ValueToInstruction, Use, ValueToConstantInt, InstructionToICmpInst, ICmpInst, CmpInst, \
    PHINode, InstructionToPHINode
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.context import SsaContext
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.value import SsaValue
from ipCorePackager.constants import INTF_DIRECTION
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import SLICE, INT
from hwtHls.ssa.phi import SsaPhi
from pyMathBitPrecise.bit_utils import ValidityError, mask
from hwtHls.ssa.translation.fromAst.astToSsa import AstToSsa
from hwtHls.llvm.toLlvmPy import ToLlvmIrTranslator
from hwt.code import Concat


def getValAndShift(v: Value):
    i = ValueToInstruction(v)
    if i is not None:
        if i.getOpcode() == Instruction.BinaryOps.Shl:
            base, sh = tuple(o.get() for o in i.iterOperands())
            sh = ValueToConstantInt(sh)
            if sh is None:
                # has no shift
                return (v, 0)
            sh = int(sh.getValue())
            _base = ValueToInstruction(base)
            if _base is not None and _base.getOpcode() == Instruction.CastOps.ZExt:
                # pop ZExt
                base, = (o.get() for o in _base.iterOperands())
            return (base, sh)
        elif i.getOpcode() == Instruction.CastOps.ZExt:
            o, = (o.get() for o in i.iterOperands())
            return getValAndShift(o)
    else:
        c = ValueToConstantInt(v)
        if c is not None:
            c = int(c.getValue())
            # find offset of a value
            assert c != 0, "This can not be 0 because this would be already optimized out"
            sh = 0
            while True:
                if (1 << sh) & c:
                    break
                sh += 1
            base = Bits(TypeToIntegerType(v.getType()).getBitWidth() - sh).from_py(c >> sh)
            return (base, sh)

    return (v, 0)


def bit_len(v: Union[HValue, Value]):
    if isinstance(v, HValue):
        return v._dtype.bit_length()
    else:
        return TypeToIntegerType(v.getType()).getBitWidth()


class FromLlvmIrTranslator():

    def __init__(self, hls: HlsStreamProc, ssaCtx: SsaContext, topIo: Dict[Interface, INTF_DIRECTION]):
        self.ssaCtx = ssaCtx
        self.hls = hls
        self.topIo = topIo
        self.argToIntf: Dict[Argument, Interface] = {}
        self.newBlocks: Dict[BasicBlock, SsaBasicBlock] = {}
        self.newValues: Dict[Value, Union[SsaValue, HValue]] = {}

    def _translateType(self, t):
        it = TypeToIntegerType(t)
        if it is not None:
            it: IntegerType
            return Bits(it.getBitWidth())
        else:
            raise NotImplementedError()

    def _translateExpr(self, v: Union[Value, Use]):
        if isinstance(v, Use):
            v = v.get()
        if not isinstance(v, Value):
            c = None
        else:
            c = ValueToConstantInt(v)

        if c is not None:
            val = int(c.getValue())
            return self._translateType(v.getType()).from_py(val)

        try:
            return self.newValues[v]
        except KeyError:
            raise

    def translateBasicBlock(self, block: BasicBlock):
        newBlock: SsaBasicBlock = self.newBlocks[block]
        for instr in block:
            instr: Instruction
            op = instr.getOpcode()
            if op == Instruction.MemoryOps.Load.value:
                a = tuple(instr.iterOperands())[0].get()
                io = self.argToIntf[a]
                res_t = self._translateType(instr.getType())
                if ToLlvmIrTranslator._getNativeInterfaceType(io).signed is not None:
                    res_t = Bits(res_t.bit_length(), io._dtype.signed)

                _instr = HlsStreamProcRead(self.hls, io, res_t)

            elif op == Instruction.MemoryOps.Store.value:
                ops = tuple(o.get() for o in instr.iterOperands())
                src = self._translateExpr(ops[0])
                io = self.argToIntf[ops[1]]
                _instr = HlsStreamProcWrite(self.hls, src, io)

            else:
                BinaryOps = Instruction.BinaryOps
                if op == BinaryOps.Shl.value:
                    onlyConcatOr = True
                    for u in instr.users():
                        i = UserToInstruction(u)
                        if i is None:
                            onlyConcatOr = False
                            break
                        o = i.getOpcode()
                        if o != BinaryOps.Or.value:
                            onlyConcatOr = False

                    if onlyConcatOr:
                        continue
                    else:
                        raise NotImplementedError()

                elif op == BinaryOps.LShr.value:
                    # >>
                    # if users are just truncatenations this is a slice
                    onlyTruncats = True
                    for u in instr.users():
                        i = UserToInstruction(u)
                        if i is None or i.getOpcode() != Instruction.CastOps.Trunc.value:
                            onlyTruncats = False
                            break

                    if onlyTruncats:
                        # will convert to slice later when converting truncat
                        continue
                    else:
                        raise NotImplementedError(instr)

                elif op == BinaryOps.AShr.value:
                    raise NotImplementedError(instr)

                elif op == Instruction.CastOps.Trunc:
                    ops = list(instr.iterOperands())
                    assert len(ops) == 1
                    a = ValueToInstruction(ops[0].get())
                    res_t = self._translateType(instr.getType())
                    indexWidth = res_t.bit_length()
                    if a is not None and a.getOpcode() == BinaryOps.LShr.value:
                        mainVar, indexLow = a.iterOperands()
                        index = self._translateExpr(indexLow)
                    else:
                        index = 0
                        mainVar = a

                    if indexWidth != 1:
                        index = SLICE.from_py(slice(index + indexWidth, index, -1))
                    else:
                        index = INT.from_py(index)

                    _instr = SsaInstr(self.ssaCtx, res_t, AllOps.INDEX, [self._translateExpr(mainVar), index])

                elif op == Instruction.CastOps.ZExt.value:
                    # if this a part of concatenation only we need to skip it and convert the concatenation
                    # only later when visiting top | instruction
                    # the concatenation is realized as ((res_t)high<<offset | (res_t)low)
                    onlyConcatOrShift = True
                    for u in instr.users():
                        i = UserToInstruction(u)
                        if i is None:
                            onlyConcatOrShift = False
                            break
                        o = i.getOpcode()
                        if o != BinaryOps.Or.value and o != BinaryOps.Shl:
                            onlyConcatOrShift = False

                    if onlyConcatOrShift:
                        continue
                    else:
                        res_t = self._translateType(instr.getType())
                        a, = (self._translateExpr(o) for o in instr.iterOperands())
                        _instr = SsaInstr(self.ssaCtx, res_t, AllOps.CONCAT,
                                          [Bits(res_t.bit_length() - a._dtype.bit_length()).from_py(0), a])

                elif op == Instruction.TermOps.Br.value:
                    assert not newBlock.successors.targets
                    ops = tuple(instr.iterOperands())
                    if len(ops) == 1:
                        newBlock.successors.addTarget(None, self.newBlocks[ops[0].get()])
                    else:
                        c, sucT, sucF = ops
                        newBlock.successors.addTarget(self._translateExpr(c), self.newBlocks[sucT.get()])
                        newBlock.successors.addTarget(None, self.newBlocks[sucF.get()])
                    continue

                elif op == Instruction.OtherOps.PHI:
                    res_t = self._translateType(instr.getType())
                    _instr = SsaPhi(self.ssaCtx, res_t)
                    newBlock.appendPhi(_instr)
                    self.newValues[instr] = _instr
                    continue
                elif op == Instruction.TermOps.Ret:
                    continue
                else:
                    res_t = self._translateType(instr.getType())
                    if op == Instruction.OtherOps.ICmp:
                        instr: ICmpInst = InstructionToICmpInst(instr)
                        P = CmpInst.Predicate
                        operator = {
                            P.ICMP_EQ:AllOps.EQ,
                            P.ICMP_NE:AllOps.NE,
                            P.ICMP_UGT:AllOps.GT,
                            P.ICMP_UGE:AllOps.GE,
                            P.ICMP_ULT:AllOps.LT,
                            P.ICMP_ULE:AllOps.LE,
                            # ICMP_SGT
                            # ICMP_SGE
                            # ICMP_SLT
                            # ICMP_SLE
                        }[instr.getPredicate()]
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

                        elif operator is AllOps.OR:
                            (left, leftSh), (right, rightSh) = (getValAndShift(o.get()) for o in instr.iterOperands())
                            high, low = None, None
                            if leftSh != rightSh:
                                if leftSh < rightSh:
                                    left, right = right, left
                                    leftSh, rightSh = rightSh, leftSh
                                ops = []
                                resW = res_t.bit_length()
                                leftWidth = bit_len(left)
                                leftPad = resW - (leftWidth + leftSh)
                                rightWidth = bit_len(right)
                                middlePad = leftSh - (rightWidth + rightSh)
                                if leftPad >= 0 and middlePad >= 0:
                                    if leftPad:
                                        ops.append(Bits(leftPad).from_py(0))
                                    ops.append(left if isinstance(left, HValue) else self._translateExpr(left))
                                    if middlePad:
                                        ops.append(Bits(middlePad).from_py(0))
                                    ops.append(right if isinstance(right, HValue) else self._translateExpr(right))
                                    if rightSh:
                                        ops.append(Bits(rightSh).from_py(0))
                                if ops:
                                    _instr = ops[0]
                                    for o in ops[1:]:
                                        if isinstance(_instr, HValue) and isinstance(o, HValue):
                                            _instr = Concat(_instr, o)
                                        else:
                                            ops = [o if isinstance(o, (HValue, SsaValue)) else self._translateExpr(o) for o in (_instr, o)]
                                            _instr = SsaInstr(self.ssaCtx, res_t, AllOps.CONCAT, ops)
                                            newBlock.appendInstruction(_instr)

                                        self.newValues[instr] = _instr
                                    continue

                    ops = [self._translateExpr(o) for o in instr.iterOperands()]
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
        newBlock = self.newBlocks[block]
        for phi, newPhi in zip(block, newBlock.phis):
            phi: PHINode = InstructionToPHINode(phi)
            newPhi: SsaPhi
            for v, b in zip(phi.iterOperands(), phi.iterBlocks()):
                v = v.get()
                assert b is not None
                newPhi.appendOperand(self._translateExpr(v), self.newBlocks[b])

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
        newBlocks = self.newBlocks
        start = None
        for bb in main:
            bb: BasicBlock
            newBlocks[bb] = newBb = SsaBasicBlock(self.ssaCtx, bb.getName().str())
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
        to_ssa.start = fromLlvm.translate(toLlvm.main)

