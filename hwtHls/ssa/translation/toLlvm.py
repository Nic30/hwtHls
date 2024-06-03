import re
from typing import List, Tuple, Dict, Union, Sequence, Callable, Optional

from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.function import HFunctionConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.slice import HSlice
from hwt.hdl.types.struct import HStruct
from hwt.hdl.const import HConst
from hwt.hwIOs.std import HwIOBramPort_noClk
from hwt.hwIO import HwIO
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_getName
from hwt.mainBases import RtlSignalBase
from hwt.hwModule import HwModule
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa, IoPortToIoOpsDictionary
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.hardBlock import HardBlockHwModule
from hwtHls.io.portGroups import MultiPortGroup, BankedPortGroup, \
    getFirstInterfaceInstance
from hwtHls.llvm.llvmIr import Value, Type, FunctionType, Function, VectorOfTypePtr, BasicBlock, Argument, \
    PointerType, ConstantInt, APInt, verifyFunction, verifyModule, TypeToIntegerType, \
    PHINode, LlvmCompilationBundle, LLVMContext, LLVMStringContext, ArrayType, MDString, \
    ConstantAsMetadata, MDNode, Module, IRBuilder, UndefValue, FunctionCallee, Intrinsic
from hwtHls.code import OP_CTLZ, OP_CTTZ, OP_CTPOP, OP_BITREVERSE, \
    OP_FSHL, OP_FSHR, OP_ZEXT, OP_SEXT, OP_ASHR, OP_LSHR, OP_SHL, OP_UMAX, \
    OP_SMAX, OP_UMIN, OP_SMIN
from hwtHls.netlist.hdlTypeVoid import _HVoidOrdering
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.transformation.utils.blockAnalysis import collect_all_blocks
from hwtHls.ssa.value import SsaValue
from hwt.pyUtils.typingFuture import override
from hwtLib.amba.axi4Lite import Axi4Lite
from hwtLib.types.ctypes import uint32_t
from pyMathBitPrecise.bit_utils import iter_bits_sequences, get_bit_range

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

    def __init__(self, label: str, topIo: IoPortToIoOpsDictionary, parentHwModule: HwModule):
        self.label = label
        self.llvm = LlvmCompilationBundle(label)
        self.ctx: LLVMContext = self.llvm.ctx
        self.strCtx: LLVMStringContext = self.llvm.strCtx
        self.module: Module = self.llvm.module
        self.b: IRBuilder = self.llvm.builder
        self.topIo = topIo
        self.ioSorted: Optional[Tuple[str, Union[HwIO, MultiPortGroup, BankedPortGroup],
                 Tuple[List[HlsRead],
                       List[HlsWrite]]]] = None
        self.parentHwModule = parentHwModule
        self.ioToVar: Dict[HwIO, Tuple[Argument, Type, Type]] = {}
        self.varMap: Dict[Union[SsaValue, SsaBasicBlock], Value] = {}
        self._branchTmpBlocks: Dict[SsaBasicBlock, List[Tuple[BasicBlock, List[SsaBasicBlock]]]] = {}
        self._afterTranslation: List[Callable[[ToLlvmIrTranslator], None]] = []
        self.placeholderObjectSlots = []

        b = self.b
        self._opConstructorMap = {
            HwtOps.AND: b.CreateAnd,
            HwtOps.OR: b.CreateOr,
            HwtOps.XOR: b.CreateXor,

            HwtOps.ADD: b.CreateAdd,
            HwtOps.SUB: b.CreateSub,
            HwtOps.MUL: b.CreateMul,
            HwtOps.UDIV: b.CreateUDiv,
            HwtOps.SDIV: b.CreateSDiv,
            OP_ASHR: b.CreateAShr,
            OP_LSHR: b.CreateLShr,
            OP_SHL: b.CreateShl,
        }
        self._opIntrinsic = {
            OP_CTLZ: Intrinsic.ctlz,
            OP_CTTZ: Intrinsic.cttz,
            OP_CTPOP: Intrinsic.ctpop,
            OP_BITREVERSE: Intrinsic.bitreverse,
            OP_FSHL: Intrinsic.fshl,
            OP_FSHR: Intrinsic.fshr,
            OP_UMAX: Intrinsic.umax,
            OP_SMAX: Intrinsic.smax,
            OP_UMIN: Intrinsic.umin,
            OP_SMIN: Intrinsic.smin,
        }
        self._opConstructorMapCmp = {
            HwtOps.NE: b.CreateICmpNE,
            HwtOps.EQ: b.CreateICmpEQ,

            HwtOps.SLE: b.CreateICmpSLE,
            HwtOps.SLT: b.CreateICmpSLT,
            HwtOps.SGT: b.CreateICmpSGT,
            HwtOps.SGE: b.CreateICmpSGE,

            HwtOps.ULE: b.CreateICmpULE,
            HwtOps.ULT: b.CreateICmpULT,
            HwtOps.UGT: b.CreateICmpUGT,
            HwtOps.UGE: b.CreateICmpUGE,
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

    def createFunctionPrototype(self, name: str, args:List[Tuple[str, Type, Type, int]], returnType: Type, addHwtHlsMeta=True):
        """
        :param args: tuples name, pointer type, element type, address width 
        """
        strCtx = self.strCtx
        _argTypes = VectorOfTypePtr()
        for _, t, _ , _ in args:
            _argTypes.push_back(t)

        FT = FunctionType.get(returnType, _argTypes, False)
        F = Function.Create(FT, Function.ExternalLinkage, strCtx.addTwine(name), self.module)

        for a, (aName, _, _, _) in zip(F.args(), args):
            a.setName(strCtx.addTwine(aName))

        if addHwtHlsMeta:
            argAddrWidths = self.mdGetTuple([self.mdGetUInt32(addrWidth) for (_, _, _, addrWidth) in args], False)
            F.setMetadata(self.strCtx.addStringRef("hwtHls.param_addr_width"),
                           self.mdGetTuple([argAddrWidths, ], True))
        return F

    def _formatVarName(self, name):
        return name.replace("%", "")

    def _translateType(self, hdlType: HdlType):
        if isinstance(hdlType, (HBits, HStruct)):
            return Type.getIntNTy(self.ctx, hdlType.bit_length())
        else:
            raise NotImplementedError(hdlType)

    def _translatePtrType(self, hdlType: HdlType, addressSpace: int):
        if isinstance(hdlType, (HBits, HStruct)):
            return Type.getPointerTo(self.ctx, addressSpace)
        else:
            raise NotImplementedError(hdlType)

    def _translateArrayType(self, hdlType: HArray):
        elemType = self._translateType(hdlType.element_t)
        return ArrayType.get(elemType, int(hdlType.size))

    def _translateExprInt(self, v: int, t: Type):
        if v < 0:
            raise NotImplementedError()

        _v = APInt(t.getBitWidth(), self.strCtx.addStringRef(f"{v:x}"), 16)
        # t = self._translateType(HBits(v), ptr=False)
        return ConstantInt.get(t, _v)

    def _translateExprHConst(self, v: HConst):
        if isinstance(v, HBitsConst):
            if v._is_full_valid():
                t = self._translateType(v._dtype)
                _v = APInt(v._dtype.bit_length(), self.strCtx.addStringRef(f"{v.val:x}"), 16)
                return ConstantInt.get(t, _v)
            elif v.vld_mask == 0:
                t = self._translateType(v._dtype)
                return UndefValue.get(t)
            else:
                concatMembers = []
                offset = 0
                for (bVal, width) in iter_bits_sequences(v.vld_mask, v._dtype.bit_length()):
                    t = Type.getIntNTy(self.ctx, width)
                    if bVal == 0:
                        m = UndefValue.get(t)
                    elif bVal == 1:
                        _v = get_bit_range(v.val, offset, offset + width)
                        _v = APInt(width, self.strCtx.addStringRef(f"{_v:x}"), 16)
                        m = ConstantInt.get(t, _v)
                    else:
                        raise ValueError(bVal)
                    concatMembers.append(m)
                    offset += width
                return self.b.CreateBitConcat(concatMembers)

        elif isinstance(v, HFunctionConst):
            assert isinstance(v, HardBlockHwModule)
            v: HardBlockHwModule
            if v.placeholderObjectId is not None:
                cur, curV = self.placeholderObjectSlots[v.placeholderObjectId]
                assert cur is v, (cur, v)
                return curV

            params = [("id", Type.getIntNTy(self.ctx, 32), None, 0)]
            if v.hasManyInputs:
                if isinstance(v.hwInputT, HStruct):
                    params.extend((f.name, self._translateType(f._dtype), None, 0) for f in v.hwInputT._fields)
                else:
                    raise NotImplementedError(v.hwInputT)
            else:
                params.append(("arg0", self._translateType(v.hwInputT), None, 0))

            if v.hasManyOutputs:
                raise NotImplementedError()
            else:
                if isinstance(v.hwOutputT, _HVoidOrdering):
                    resTy = Type.getVoidTy(self.ctx)
                else:
                    resTy = self._translateType(v.hwOutputT)

            v.placeholderObjectId = len(self.placeholderObjectSlots)
            fn = self.createFunctionPrototype(f"hwtHls.pyObjectPlaceholder.{v.placeholderObjectId:d}.{v.val:s}",
                                              params, resTy, addHwtHlsMeta=False)
            self.placeholderObjectSlots.append((v, fn))
            return fn
        else:
            raise NotImplementedError(v)

    def _translateExpr(self, v: Union[SsaInstr, HConst]):
        if isinstance(v, HConst):
            c = self.varMap.get(v, None)
            if c is None:
                c = self._translateExprHConst(v)
                self.varMap[v] = c

            return c
        else:
            return self.varMap[v]  # if variable was defined it must be there

    def _translateExprOperand(self, operator: HOperatorDef, resTy: HdlType,
                              operands: Tuple[Union[SsaInstr, HConst]],
                              instrName: str, instrForDebug):
        b = self.b
        if operator == HwtOps.CONCAT and isinstance(resTy, HBits):
            ops = [self._translateExpr(op) for op in operands]
            return b.CreateBitConcat(ops)

        elif operator == HwtOps.INDEX and isinstance(operands[0]._dtype, HBits):
            op0, op1 = operands
            op0 = self._translateExpr(op0)
            if isinstance(op1._dtype, HSlice):
                op1 = int(op1.val.stop)
            else:
                op1 = int(op1)

            return b.CreateBitRangeGetConst(op0, op1, resTy.bit_length())

        else:
            args = (self._translateExpr(a) for a in operands)
            if operator in (HwtOps.BitsAsSigned, HwtOps.BitsAsUnsigned, HwtOps.BitsAsVec):
                op0, = args
                # LLVM uses sign/unsigned variants of instructions and does not have signed/unsigned as a part of type or variable
                return op0

            name = self.strCtx.addTwine(self._formatVarName(instrName) if instrName else "")
            if operator == HwtOps.NOT:
                op0, = args
                # op0 xor -1
                mask = APInt.getAllOnes(resTy.bit_length())
                return b.CreateXor(op0, ConstantInt.get(TypeToIntegerType(op0.getType()), mask), name)

            elif operator == HwtOps.MINUS_UNARY:
                op0, = args
                return b.CreateNeg(op0, name, False, False)
            elif operator == OP_ZEXT:
                op0, = args
                return b.CreateZExt(op0, self._translateType(resTy), name)
            elif operator == OP_SEXT:
                op0, = args
                return b.CreateSExt(op0, self._translateType(resTy), name)
            elif operator == HwtOps.TERNARY:
                opC, opTrue, opFalse = args
                return b.CreateSelect(opC, opTrue, opFalse, name, None)
            elif operator == HwtOps.CALL:
                args = tuple(args)
                fn = operands[0]
                isHardblock = isinstance(fn, HardBlockHwModule)
                if isHardblock:
                    _args = [self._translateExprInt(fn.placeholderObjectId, Type.getIntNTy(self.ctx, 32))]
                    _args.extend(args[1:])
                else:
                    _args = list(args[1:])
                res = b.CreateCall(FunctionCallee(args[0]), _args)
                if isHardblock:
                    res = fn.translateCallAttributesToLlvm(self, res)

                return res

            intrinsic = self._opIntrinsic.get(operator)
            if intrinsic is not None:
                sliceOut = None
                if operator in (OP_CTLZ, OP_CTTZ, OP_CTPOP):
                    op0, _ = operands
                    sliceOut = resTy.bit_length()
                    resTy = op0._dtype
                elif operator == OP_BITREVERSE:
                    op0, = operands
                    resTy = op0._dtype
                elif operator in (OP_UMIN, OP_UMAX, OP_SMIN, OP_SMAX,):
                    assert len(operands) == 2
                    resTy = operands[0]._dtype
                elif operator in (OP_FSHL, OP_FSHR):
                    assert len(operands) == 3
                    resTy = operands[0]._dtype
                else:
                    raise NotImplementedError(operator)

                resTy = self._translateType(resTy)
                res = b.CreateIntrinsic(resTy, intrinsic.value, list(args), Name=name)
                if sliceOut is None:
                    return res
                else:
                    return b.CreateBitRangeGetConst(res, 0, sliceOut)

            constructor_fn = self._opConstructorMap.get(operator, None)
            if constructor_fn is not None:
                return constructor_fn(*args, name)
            else:
                assert len(operands) == 2, instrForDebug
                _opConstructorMap2 = self._opConstructorMapCmp

                return _opConstructorMap2[operator](*args, name)

    def _translateInstr(self, instr: SsaInstr):
        if isinstance(instr, (HlsRead, HlsWrite)):
            res = instr._translateToLlvm(self)
        else:
            res = self._translateExprOperand(
                instr.operator, instr._dtype, instr.operands, instr._name, instr)
        if instr.metadata:
            for m in instr.metadata:
                m.toLlvm(self, instr, res)
        return res

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

    def _getInterfaceTypeForFnArg(self, i: Union[HwIO, MultiPortGroup, BankedPortGroup, RtlSignalBase], ioIndex: int,
                                  reads: List[HlsRead], writes: List[HlsWrite]) -> Tuple[Type, Type]:
        wordType = None
        if reads:
            wordType = reads[0]._getNativeInterfaceWordType()
            if not reads[0]._isBlocking:
                wordType = HBits(wordType.bit_length() + 1)
            elif not isinstance(wordType, HBits):
                wordType = HBits(wordType.bit_length())

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
        i = getFirstInterfaceInstance(i)
        if isinstance(i, (HwIOBramPort_noClk, Axi4Lite)):
            addrWidth = i.ADDR_WIDTH
            arrTy = wordType[int(2 ** i.ADDR_WIDTH)]
            elmT = self._translateArrayType(arrTy)
        else:
            elmT = self._translateType(wordType)
            addrWidth = 0

        return ptrT, elmT, addrWidth

    def translate(self, start_bb: SsaBasicBlock, fnPragma: List["_PyBytecodePragma"]):
        # create a function where we place the code and the arguments for a io interfaces
        ioTuplesWithName = [
            (HwIO_getName(self.parentHwModule, io[0] if isinstance(io, (MultiPortGroup, BankedPortGroup)) else io), io, ioOps)
            for io, ioOps in self.topIo.items()
        ]
        ioSorted = self.ioSorted = sorted(ioTuplesWithName, key=lambda x: self.splitStrToStrsAndInts(x[0]))
        # name, pointer type, element type, address width
        params: List[Tuple[str, Type, Type, int]] = [
            (name,
             *self._getInterfaceTypeForFnArg(hwIO[0]
                                           if isinstance(hwIO, tuple)
                                           else hwIO,
                                            ioIndex, reads, writes))
            for ioIndex, (name, hwIO, (reads, writes)) in enumerate(ioSorted)]
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

        for meta in fnPragma:
            meta:"_PyBytecodePragma"
            meta.toLlvm(self, main)

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

    def __init__(self, hls: "HlsScope", llvmCliArgs: List[Tuple[str, int, str, str]]=[]):
        self.hls = hls
        self.llvmCliArgs = llvmCliArgs

    @override
    def runOnSsaModuleImpl(self, toSsa: HlsAstToSsa):
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

        toLlvm = ToLlvmIrTranslator(toSsa.label, ioDict, self.hls.parentHwModule)
        for (optionName, position, argName, argValue) in self.llvmCliArgs:
            toLlvm.llvm.addLlvmCliArgOccurence(optionName, position, argName, argValue)
        toLlvm.translate(toSsa.start, toSsa.pragma)
        toSsa.resolveIoNetlistConstructors(ioDict)
        toSsa.start = toLlvm
