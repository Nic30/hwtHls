import re
from typing import List, Tuple, Dict, Union, Sequence, Callable, Optional

from hwt.hdl.operatorDefs import AllOps, OpDefinition
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
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa, IoPortToIoOpsDictionary
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup
from hwtHls.llvm.llvmIr import Value, Type, FunctionType, Function, VectorOfTypePtr, BasicBlock, Argument, \
    PointerType, ConstantInt, APInt, verifyFunction, verifyModule, TypeToIntegerType, \
    PHINode, LlvmCompilationBundle, LLVMContext, LLVMStringContext, ArrayType, MDString, \
    ConstantAsMetadata, MDNode, Module, IRBuilder, UndefValue
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi4Lite import Axi4Lite
from hwtLib.types.ctypes import uint32_t

RE_ID_WITH_NUMBER = re.compile('[^0-9]+|[0-9]+')


class ToLlvmIrTranslator():
    """
    A container class which contains all necessary objects for LLVM.
    It can also translate between hwtHls SSA and LLVM SSA (in booth directions).

    While converting there are several issues:
    1. LLVM does not have multi-level logic type like VHDL STD_LOGIC_VECTOR or Verilog wire/logic.
      * all x/z/u are replaced with 0 or with UndefValue if value is fully undefined
    2. LLVM does not have bit slicing and concatenation operators.
      * all replaced with zext, sext, hwtHls.bitrangeGet/hwtHls.bitConcat
    
    :note: Information about IO are stored in function attributes
    :ivar _branchTmpBlocks: dictionary to keep track of BasicBlocks generated during conversion of branch instruction
        used to resolve argument of PHIs, specified in dictionary format
        original block to list of tuples LLVM basic block and list of original successors
    """

    def __init__(self, label: str, topIo: IoPortToIoOpsDictionary, parentUnit: Unit):
        self.label = label
        self.llvm = LlvmCompilationBundle(label)
        self.ctx: LLVMContext = self.llvm.ctx
        self.strCtx: LLVMStringContext = self.llvm.strCtx
        self.module: Module = self.llvm.module
        self.b: IRBuilder = self.llvm.builder
        self.topIo = topIo
        self.ioSorted: Optional[Tuple[str, Union[Interface, MultiPortGroup, BankedPortGroup],
                 Tuple[List[HlsRead],
                       List[HlsWrite]]]] = None
        self.parentUnit = parentUnit
        self.ioToVar: Dict[Interface, Tuple[Argument, Type, Type]] = {}
        self.varMap: Dict[Union[SsaValue, SsaBasicBlock], Value] = {}
        self._branchTmpBlocks: Dict[SsaBasicBlock, List[Tuple[BasicBlock, List[SsaBasicBlock]]]] = {}
        self._afterTranslation: List[Callable[[ToLlvmIrTranslator], None]] = []

        b = self.b
        self._opConstructorMap0 = {
            AllOps.AND: b.CreateAnd,
            AllOps.OR: b.CreateOr,
            AllOps.XOR: b.CreateXor,
        }
        self._opConstructorMap1 = {
            AllOps.ADD: b.CreateAdd,
            AllOps.SUB: b.CreateSub,
            AllOps.MUL: b.CreateMul,
        }

        self._opConstructorMapSignedCmp = {
            AllOps.NE: b.CreateICmpNE,
            AllOps.EQ: b.CreateICmpEQ,
            AllOps.LE: b.CreateICmpSLE,
            AllOps.LT: b.CreateICmpSLT,
            AllOps.GT: b.CreateICmpSGT,
            AllOps.GE: b.CreateICmpSGE,
        }
        self._opConstructorMapUnsignedCmp = {
            AllOps.NE: b.CreateICmpNE,
            AllOps.EQ: b.CreateICmpEQ,
            AllOps.LE: b.CreateICmpULE,
            AllOps.LT: b.CreateICmpULT,
            AllOps.GT: b.CreateICmpUGT,
            AllOps.GE: b.CreateICmpUGE,
        }

    def addAfterTranslationUnique(self, fn: Callable[['ToLlvmIrTranslator'], None]):
        if fn not in self._afterTranslation:
            self._afterTranslation.append(fn)

    def mdGetStr(self, s: str):
        """
        Get LLVM metadata string from python string
        """
        return MDString.get(self.ctx, self.strCtx.addStringRef(s))

    def mdGetUInt32(self, i: int):
        """
        Get LLVM metadata uint32 from python int
        """
        return ConstantAsMetadata.getConstant(self._translateExprInt(i, self._translateType(uint32_t)))

    def mdGetTuple(self, items: Sequence[Union[ConstantAsMetadata, MDString, MDNode]], insertSelfAsFirts: bool):
        """
        Get LLVM metadata tuple from python sequence
        """
        itemsAsMetadata = [i.asMetadata() for i in items]
        res = MDNode.get(self.ctx, itemsAsMetadata, insertTmpAsFirts=insertSelfAsFirts)
        return res

    def createFunctionPrototype(self, name: str, args:List[Tuple[str, Type, Type]], returnType: Type):
        strCtx = self.strCtx
        _argTypes = VectorOfTypePtr()
        for _, t, _ , _ in args:
            _argTypes.push_back(t)

        FT = FunctionType.get(returnType, _argTypes, False)
        F = Function.Create(FT, Function.ExternalLinkage, strCtx.addTwine(name), self.module)

        for a, (aName, _, _, _) in zip(F.args(), args):
            a.setName(strCtx.addTwine(aName))

        argAddrWidths = self.mdGetTuple([self.mdGetUInt32(addrWidth) for (_, _, _, addrWidth) in args], False)
        F.setMetadata(self.strCtx.addStringRef("hwtHls.param_addr_width"),
                       self.mdGetTuple([argAddrWidths, ], True))
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

    def _translateExprHValue(self, v: HValue):
        if isinstance(v, BitsVal):
            t = self._translateType(v._dtype)
            if v._is_full_valid():
                _v = APInt(v._dtype.bit_length(), self.strCtx.addStringRef(f"{v.val:x}"), 16)
                return ConstantInt.get(t, _v)
            elif v.vld_mask == 0:
                return UndefValue.get(t)
            else:
                raise NotImplementedError(v)
        else:
            raise NotImplementedError(v)

    def _translateExpr(self, v: Union[SsaInstr, HValue]):
        if isinstance(v, HValue):
            c = self.varMap.get(v, None)
            if c is None:
                c = self._translateExprHValue(v)
                self.varMap[v] = c

            return c
        else:
            return self.varMap[v]  # if variable was defined it must be there

    def _translateExprOperand(self, operator: OpDefinition, resTy: HdlType,
                              operands: Tuple[Union[SsaInstr, HValue]],
                              instrName: str, instrForDebug):
        b = self.b
        if operator == AllOps.CONCAT and isinstance(resTy, Bits):
            ops = [self._translateExpr(op) for op in operands]
            return b.CreateBitConcat(ops)

        elif operator == AllOps.INDEX and isinstance(operands[0]._dtype, Bits):
            op0, op1 = operands
            op0 = self._translateExpr(op0)
            if isinstance(op1._dtype, HSlice):
                op1 = int(op1.val.stop)
            else:
                op1 = int(op1)

            return b.CreateBitRangeGetConst(op0, op1, resTy.bit_length())

        else:
            args = (self._translateExpr(a) for a in operands)
            if operator in (AllOps.BitsAsSigned, AllOps.BitsAsUnsigned, AllOps.BitsAsVec):
                op0, = args
                # LLVM uses sign/unsigned variants of instructions and does not have signed/unsigned as a part of type or variable
                return op0

            name = self.strCtx.addTwine(self._formatVarName(instrName) if instrName else "")
            if operator == AllOps.NOT:
                op0, = args
                # op0 xor -1
                mask = APInt.getAllOnesValue(resTy.bit_length())
                return b.CreateXor(op0, ConstantInt.get(TypeToIntegerType(op0.getType()), mask), name)

            elif operator == AllOps.MINUS_UNARY:
                op0, = args
                return b.CreateNeg(op0, name, False, False)
            elif operator == AllOps.TERNARY:
                opC, opTrue, opFalse = args
                return b.CreateSelect(opC, opTrue, opFalse, name, None)

            constructor_fn = self._opConstructorMap0.get(operator, None)
            if constructor_fn is not None:
                return constructor_fn(*args, name)

            constructor_fn = self._opConstructorMap1.get(operator, None)
            if constructor_fn is not None:
                return constructor_fn(*args, name, False, False)
            else:
                assert len(operands) == 2, instrForDebug
                isSigned = bool(operands[0]._dtype.signed)
                if isSigned != bool(operands[1]._dtype.signed):
                    raise NotImplementedError("signed+unsigned cmp")

                if isSigned:
                    _opConstructorMap2 = self._opConstructorMapSignedCmp
                else:
                    _opConstructorMap2 = self._opConstructorMapUnsignedCmp

                return _opConstructorMap2[operator](*args, name)

    def _translateInstr(self, instr: SsaInstr):
        if isinstance(instr, (HlsRead, HlsWrite)):
            return instr._translateToLlvm(self)
        else:
            return self._translateExprOperand(
                instr.operator, instr._dtype, instr.operands, instr._name, instr)

    def _translate(self, bb: SsaBasicBlock):
        llvmBb = self.varMap[bb]
        b = self.b
        b.SetInsertPoint(llvmBb)

        for phi in bb.phis:
            phi: SsaPhi
            llvmPhi: PHINode = b.CreatePHI(self._translateType(phi._dtype), len(phi.operands), self.strCtx.addTwine(self._formatVarName(phi._name)))
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

    def _getInterfaceTypeForFnArg(self, i: Interface, ioIndex: int,
                                  reads: List[HlsRead], writes: List[HlsWrite]) -> Tuple[Type, Type]:
        wordType = None
        if reads:
            wordType = reads[0]._getNativeInterfaceWordType()
            if not reads[0]._isBlocking:
                wordType = Bits(wordType.bit_length() + 1)
            elif not isinstance(wordType, Bits):
                wordType = Bits(wordType.bit_length())

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

        ptrT = PointerType.get(self.ctx, ioIndex + 1)
        if isinstance(i, (BramPort_withoutClk, Axi4Lite)):
            addrWidth = i.ADDR_WIDTH
            arrTy = wordType[int(2 ** i.ADDR_WIDTH)]
            elmT = self._translateArrayType(arrTy)
        else:
            elmT = self._translateType(wordType)
            addrWidth = 0

        return ptrT, elmT, addrWidth

    def translate(self, start_bb: SsaBasicBlock):
        # create a function where we place the code and the arguments for a io interfaces
        ioTuplesWithName = [
            (getInterfaceName(self.parentUnit, io[0] if isinstance(io, (MultiPortGroup, BankedPortGroup)) else io), io, ioOps)
            for io, ioOps in self.topIo.items()
        ]
        ioSorted = self.ioSorted = sorted(ioTuplesWithName, key=lambda x: self.splitStrToStrsAndInts(x[0]))
        # name, pointer type, element type, address width
        params: List[str, Type, Type, int] = [
            (name,
             *self._getInterfaceTypeForFnArg(intf[0]
                                           if isinstance(intf, tuple)
                                           else intf,
                                            ioIndex, reads, writes))
            for ioIndex, (name, intf, (reads, writes)) in enumerate(ioSorted)]
        main = self.createFunctionPrototype(self.label, params, Type.getVoidTy(self.ctx))
        self.llvm.main = main

        ioToVar = self.ioToVar
        for a, (_, i, (_, _)), (_, ptrT, t, _) in zip(main.args(), ioSorted, params):
            ioToVar[i] = (a, ptrT, t)

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

        for cb in self._afterTranslation:
            cb(self)

        assert verifyFunction(main) is False
        assert verifyModule(self.module) is False

        return self


class SsaPassToLlvm(SsaPass):
    """
    Convert hwtHls.ssa to LLVM SSA IR
    
    :ivar llvmCliArgs: tuples (optionName, position, argName, argValue), argValue is also string 
    """

    def __init__(self, llvmCliArgs: List[Tuple[str, int, str, str]]=[]):
        self.llvmCliArgs = llvmCliArgs

    def apply(self, hls: "HlsScope", toSsa: HlsAstToSsa):
        ioDict = toSsa.collectIo()
        for i, (reads, writes) in ioDict.items():
            if not reads and not writes:
                raise AssertionError("Unused IO ", i)

            # for instr in reads:
            #    instr: HlsRead
            #    assert i == instr._src, (i, instr)
            #    nativeWordT = instr._getNativeInterfaceWordType()
            #    if instr._isBlocking:
            #        resTy._dtype.bit_length() == nativeWordT.bit_length(), (
            #            "In this stages the read operations must read only native type of interface",
            #            instr, nativeWordT)
            #    else:
            #        assert instr._dtype.bit_length() == nativeWordT.bit_length() + 1, (
            #            "In this stages the read operations must read only native type of interface",
            #            instr, nativeWordT)
            #
            # for instr in writes:
            #    instr: HlsWrite
            #    assert i == instr.dst, (i, instr)
            #    nativeWordT = instr._getNativeInterfaceWordType()
            #    assert instr.operands[0]._dtype.bit_length() == nativeWordT.bit_length(), (
            #        "In this stages the read operations must read only native type of interface",
            #        instr, instr.operands[0]._dtype, nativeWordT)

        toLlvm = ToLlvmIrTranslator(toSsa.label, ioDict, hls.parentUnit)
        for (optionName, position, argName, argValue) in self.llvmCliArgs:
            toLlvm.llvm.addLlvmCliArgOccurence(optionName, position, argName, argValue)
        toLlvm.translate(toSsa.start)
        toSsa.resolveIoNetlistConstructors(ioDict)
        toSsa.start = toLlvm
