import re
from typing import List, Tuple, Dict, Union

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.slice import HSlice
from hwt.hdl.types.struct import HStruct
from hwt.hdl.value import HValue
from hwt.interfaces.std import BramPort_withoutClk
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getInterfaceName
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.statementsRead import HlsRead, HlsReadAddressed
from hwtHls.frontend.ast.statementsWrite import HlsWrite, HlsWriteAddressed
from hwtHls.llvm.llvmIr import Value, Type, FunctionType, Function, VectorOfTypePtr, BasicBlock, Argument, \
    PointerType, TypeToPointerType, ConstantInt, APInt, verifyFunction, verifyModule, TypeToIntegerType, \
    PHINode, LlvmCompilationBundle, LLVMContext, LLVMStringContext, ArrayType, TypeToArrayType
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi4Lite import Axi4Lite
from hwtLib.types.ctypes import uint64_t
from hwt.synthesizer.unit import Unit


RE_ID_WITH_NUMBER = re.compile('[^0-9]+|[0-9]+')


class ToLlvmIrTranslator():
    """
    A container class which contains all necessary objects for LLVM.
    It can also translate between hwtHls SSA and LLVM SSA (in bouth directions).

    While converting there are several issues:
    1. LLVM does not have multi level logic type like vhdl STD_LOGIC_VECTOR or verilog wire/logic.
      * all x/z/u are replaced with 0
    2. LLVM does not have bit slicing and concatenation operators.
      * all replaced by shifting and masking
    3. LLVM does not have equivalent of HlsNetNodeRead/HlsNetNodeWrite
      * all read/write expressions are replaced with a function unique for each interface.

    :ivar _branchTmpBlocks: dictionary to keep track of BasicBlocks generated during conversion of branch instruction
        used to resolve argument of Phis, specified in dictionary format
        original block to list of tuples LLVM basic block and list of original successors
    """

    def __init__(self, label: str, topIo: Dict[Interface, Tuple[List[HlsRead], List[HlsWrite]]], parentUnit: Unit):
        self.label = label
        self.llvm = LlvmCompilationBundle(label)
        self.ctx: LLVMContext = self.llvm.ctx
        self.strCtx: LLVMStringContext = self.llvm.strCtx
        self.mod = self.llvm.mod
        self.b = self.llvm.builder
        self.topIo = topIo
        self.parentUnit = parentUnit
        self._branchTmpBlocks: Dict[SsaBasicBlock, List[Tuple[BasicBlock, List[SsaBasicBlock]]]] = {}
        self._MdMetaslotName = self.strCtx.addStringRef("hwtHls.metaslot")

    def createFunctionPrototype(self, name: str, args:List[Tuple[Type, str]], returnType: Type):
        strCtx = self.strCtx
        _argTypes = VectorOfTypePtr()
        for _, t in args:
            _argTypes.push_back(t)

        FT = FunctionType.get(returnType, _argTypes, False)
        F = Function.Create(FT, Function.ExternalLinkage, strCtx.addTwine(name), self.mod)

        for a, (aName, _) in zip(F.args(), args):
            a.setName(strCtx.addTwine(aName))

        return F

    def _formatVarName(self, name):
        return name.replace("%", "")

    def _translateType(self, hdlType: HdlType):
        if isinstance(hdlType, (Bits, HStruct)):
            return Type.getIntNTy(self.ctx, hdlType.bit_length())
        else:
            raise NotImplementedError(hdlType)

    def _translatePtrType(self, hdlType: HdlType, addressSpace: int):
        if isinstance(hdlType, (Bits, HStruct)):
            return Type.getIntNPtrTy(self.ctx, hdlType.bit_length(), addressSpace)
        else:
            raise NotImplementedError(hdlType)

    def _translateArrayType(self, hdlType: HArray):
        elemType = self._translateType(hdlType.element_t)
        return ArrayType.get(elemType, int(hdlType.size))

    def _translateExprInt(self, v: int, t: Type):
        if v < 0:
            raise NotImplementedError()

        _v = APInt(t.getBitWidth(), self.strCtx.addStringRef(f"{v:x}"), 16)
        # t = self._translateType(Bits(v), ptr=False)
        return ConstantInt.get(t, _v)

    def _translateExpr(self, v: Union[SsaValue, HValue]):
        if isinstance(v, HValue):
            if isinstance(v, BitsVal):
                _v = APInt(v._dtype.bit_length(), self.strCtx.addStringRef(f"{v.val:x}"), 16)
                t = self._translateType(v._dtype)
                return ConstantInt.get(t, _v)
            else:
                raise NotImplementedError(v)
            return v

        return self.varMap[v]  # if variable was defined it must be there

    def _translateInstr(self, instr: SsaInstr):
        b = self.b
        if isinstance(instr, HlsRead):
            src: Argument = self.ioToVar[instr._src]
            t: PointerType = TypeToPointerType(src.getType())
            if isinstance(instr, HlsReadAddressed):
                indexes = [self._translateExprInt(0, self._translateType(uint64_t)), self._translateExpr(instr.operands[0]), ]
                arrTy: ArrayType = TypeToArrayType(t.getPointerElementType())
                elmT = arrTy.getElementType()
                ptr = b.CreateGEP(arrTy, src, indexes)
            else:
                assert t is not None, src.getType()
                elmT = t.getPointerElementType()
                ptr = src

            return b.CreateLoad(elmT, ptr, True,
                                self.strCtx.addTwine(self._formatVarName(instr._name)))

        elif isinstance(instr, HlsWrite):
            dst = self.ioToVar[instr.dst]
            src = self._translateExpr(instr.getSrc())
            t: PointerType = TypeToPointerType(dst.getType())
            if isinstance(instr, HlsWriteAddressed):
                indexes = [self._translateExprInt(0, self._translateType(uint64_t)),
                                                     self._translateExpr(instr.getIndex()), ]
                arrTy: ArrayType = TypeToArrayType(t.getPointerElementType())
                elmT = arrTy.getElementType()
                dst = b.CreateGEP(arrTy, dst, indexes)
            
            return b.CreateStore(src, dst, True)

        elif instr.operator == AllOps.CONCAT and isinstance(instr._dtype, Bits):
            ops = [self._translateExpr(op) for op in instr.operands]
            return b.CreateBitConcat(ops)

        elif instr.operator == AllOps.INDEX and isinstance(instr.operands[0]._dtype, Bits):
            op0, op1 = instr.operands
            op0 = self._translateExpr(op0)
            # res_t = self._translateType(instr._dtype)
            if isinstance(op1._dtype, HSlice):
                op1 = self._translateExprInt(int(op1.val.stop), TypeToIntegerType(op0.getType()))
            else:
                op1 = self._translateExprInt(int(op1), TypeToIntegerType(op0.getType()))

            return b.CreateBitRangeGet(op0, op1, instr._dtype.bit_length())

        else:
            args = (self._translateExpr(a) for a in instr.operands)
            name = self.strCtx.addTwine(self._formatVarName(instr._name))
            if instr.operator == AllOps.NOT:
                op0, = args
                # xor -1
                mask = APInt.getAllOnesValue(instr._dtype.bit_length())
                return b.CreateXor(op0, ConstantInt.get(TypeToIntegerType(op0.getType()), mask), name)

            _opConstructorMap0 = {
                AllOps.AND: b.CreateAnd,
                AllOps.OR: b.CreateOr,
                AllOps.XOR: b.CreateXor,
            }

            constructor_fn = _opConstructorMap0.get(instr.operator, None)
            if constructor_fn is not None:
                return constructor_fn(*args, name)

            _opConstructorMap1 = {
                AllOps.ADD: b.CreateAdd,
                AllOps.SUB: b.CreateSub,
                AllOps.MUL: b.CreateMul,
            }
            constructor_fn = _opConstructorMap1.get(instr.operator, None)
            if constructor_fn is not None:
                return constructor_fn(*args, name, False, False)
            else:
                isSigned = bool(instr.operands[0]._dtype.signed)
                if isSigned != bool(instr.operands[1]._dtype.signed):
                    raise NotImplementedError()
                if isSigned:
                    _opConstructorMap2 = {
                        AllOps.NE: b.CreateICmpNE,
                        AllOps.EQ: b.CreateICmpEQ,
                        AllOps.LE: b.CreateICmpSLE,
                        AllOps.LT: b.CreateICmpSLT,
                        AllOps.GT: b.CreateICmpSGT,
                        AllOps.GE: b.CreateICmpSGE,
                    }
                else:
                    _opConstructorMap2 = {
                        AllOps.NE: b.CreateICmpNE,
                        AllOps.EQ: b.CreateICmpEQ,
                        AllOps.LE: b.CreateICmpULE,
                        AllOps.LT: b.CreateICmpULT,
                        AllOps.GT: b.CreateICmpUGT,
                        AllOps.GE: b.CreateICmpUGE,
                    }
                return _opConstructorMap2[instr.operator](*args, name)

    def _translate(self, bb: SsaBasicBlock):
        llvmBb = self.varMap[bb]
        b = self.b
        b.SetInsertPoint(llvmBb)

        for phi in bb.phis:
            phi: SsaPhi
            llvmPhi: PHINode = b.CreatePHI(self._translateType(phi._dtype), len(phi.operands), self.strCtx.addTwine(phi._name))
            self.varMap[phi] = llvmPhi

        for instr in bb.body:
            assert instr not in self.varMap
            i = self._translateInstr(instr)
            self.varMap[instr] = i

        # :note: potentially we need to add an extra blocks because LLVM branch instructions
        # do not support multiple non conditional inputs and we need to generate additional blocks
        preLastTargetsI = len(bb.successors.targets) - 2
        lastTargetsI = preLastTargetsI + 1
        llvmBb = self.varMap[bb]
        branchTmpBlocks = self._branchTmpBlocks[bb] = []

        # firstPairOfSuccessors = True
        for i, (c, sucBb, meta) in enumerate(bb.successors.targets):

            doBreak = False    
            if i == preLastTargetsI:
                nextC, nextB, nextMeta = bb.successors.targets[i + 1]
                assert nextC is None, ("last jump from block must be unconditional", bb, bb.successors)
                br = b.CreateCondBr(self._translateExpr(c), self.varMap[sucBb], self.varMap[nextB], None)
                if nextMeta is not None:
                    raise NotImplementedError(nextMeta)

                branchTmpBlocks.append((llvmBb, [sucBb, nextB]))
                doBreak = True
            elif i == lastTargetsI:
                assert c is None, ("last jump from block must be unconditional", bb, bb.successors)
                br = b.CreateBr(self.varMap[sucBb])
                branchTmpBlocks.append((llvmBb, [sucBb, ]))
                doBreak = True  # would break on its own, added just to improve code readability
            else:
                # need to generate a new block
                branchTmpBlocks.append((llvmBb, [sucBb, ]))
                newLlvmBb = BasicBlock.Create(self.ctx, self.strCtx.addTwine(bb.label), self.llvm.main, None)
                b.SetInsertPoint(llvmBb)
                br = b.CreateCondBr(self._translateExpr(c), self.varMap[sucBb], newLlvmBb, None)
                llvmBb = newLlvmBb
                b.SetInsertPoint(llvmBb)

            if meta is not None:
                for m in meta:
                    m.toLlvm(self, br)

            if doBreak:
                break

        if not bb.successors.targets:
            b.CreateRetVoid()

    @staticmethod
    def splitStrToStrsAndInts(name):
        key = []
        for part in RE_ID_WITH_NUMBER.findall(name):
            try:
                key.append(int(part))
            except ValueError:
                key.append(part)
        return key

    def _getInterfaceTypeForFnArg(self, i: Interface, ioIndex: int, reads: List[HlsRead], writes: List[HlsWrite]):
        wordType = None
        if reads:
            wordType = reads[0]._getNativeInterfaceWordType()

        if writes:
            _wordType = writes[0]._getNativeInterfaceWordType()
            if wordType is None or wordType is _wordType:
                wordType = _wordType 
            else:
                w0 = wordType.bit_length()
                w1 = _wordType.bit_length()
                # the type may be different between read and write
                # this is for example if the write word has write mask and read has not
                # for LLVM we need just a single pointer, in this case we
                # we extend the type of pointer to larger type
                if w0 < w1:
                    wordType = _wordType

        if isinstance(i, (BramPort_withoutClk, Axi4Lite)):
            arrTy = wordType[int(2 ** i.ADDR_WIDTH)]
            llvmArrTy = self._translateArrayType(arrTy)
            return PointerType.get(llvmArrTy, ioIndex + 1) 
        else:
            return self._translatePtrType(wordType, ioIndex + 1)

    def translate(self, start_bb: SsaBasicBlock):
        # create a function where we place the code and the arguments for a io interfaces
        io_sorted = sorted(self.topIo.items(), key=lambda x: self.splitStrToStrsAndInts(getInterfaceName(self.parentUnit, x[0])))
        params = [
            (getInterfaceName(self.parentUnit, i), self._getInterfaceTypeForFnArg(i, ioIndex, reads, writes))
            for ioIndex, (i, (reads, writes)) in enumerate(io_sorted)]
        self.llvm.main = main = self.createFunctionPrototype(self.label, params, Type.getVoidTy(self.ctx))
        ioToVar: Dict[Interface, Argument] = {}
        for a, (i, (_, _)) in zip(main.args(), io_sorted):
            ioToVar[i] = a
        self.ioToVar = ioToVar
        self.varMap: Dict[Union[SsaValue, SsaBasicBlock], Value] = {}
        allBlocksSet = set()
        allBlocks = list(collect_all_blocks(start_bb, allBlocksSet))
        for bb in allBlocks:
            llvmBb = BasicBlock.Create(self.ctx, self.strCtx.addTwine(bb.label), main, None)
            self.varMap[bb] = llvmBb

        for b in allBlocks:
            self._translate(b)

        for b in allBlocks:
            for phi in b.phis:
                llvmPhi = self.varMap[phi]
                for (v, predBlock) in phi.operands:
                    # because the predecessor may be split on multiple blocks due to branch instruction
                    # expansion we need to get all potential predecessors
                    predFound = False
                    for llvmPredBlock, sucBlocks in self._branchTmpBlocks[predBlock]:
                        if b in sucBlocks:
                            llvmPhi.addIncoming(self._translateExpr(v), llvmPredBlock)
                            predFound = True
                    assert predFound, phi

        assert verifyFunction(main) is False
        assert verifyModule(self.mod) is False

        return self


class SsaPassToLlvm():
    """
    Convert hwtHls.ssa to LLVM SSA IR
    """

    def apply(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        io: Dict[Interface, Tuple[List[HlsRead], List[HlsWrite]]] = toSsa.collectIo()
        for i, (reads, writes) in io.items(): 
            for instr in reads:
                instr: HlsRead
                assert i is instr._src, (i, instr)
                assert instr._dtype.bit_length() == instr._getNativeInterfaceWordType().bit_length(), (
                    "In this stages the read operations must read only native type of interface",
                    instr, instr._getNativeInterfaceWordType())

            for instr in writes:
                instr: HlsWrite
                assert i is instr.dst, (i, instr)
                assert instr.operands[0]._dtype.bit_length() == instr._getNativeInterfaceWordType().bit_length(), (
                    "In this stages the read operations must read only native type of interface",
                    instr, instr.operands[0]._dtype, instr._getNativeInterfaceWordType())

        toLlvm = ToLlvmIrTranslator(toSsa.label, io, hls.parentUnit)
        toLlvm.translate(toSsa.start)
        toSsa.resolveIoNetlistConstructors(io)
        toSsa.start = toLlvm
