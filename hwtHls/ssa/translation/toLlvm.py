from _io import StringIO
from pathlib import Path
from typing import List, Tuple, Dict, Union, Sequence, Callable, Optional, Set

from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.portItem import HdlPortItem
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.array import HArray
from hwt.hdl.types.arrayConst import HArrayRtlSignal, HArrayConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.function import HFunctionConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.slice import HSlice
from hwt.hdl.types.sliceConst import HSliceConst
from hwt.hdl.types.struct import HStruct
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.std import HwIOSignal
from hwt.hwModule import HwModule
from hwt.pyUtils.arrayQuery import grouper, flatten
from hwt.synthesizer.interfaceLevel.utils import HwIO_pack
from hwt.synthesizer.rtlLevel.exceptions import SignalDriverErr
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.hOperatorDefLlvm import HOperatorDefLlvm
from hwtHls.frontend.hardBlock import HardBlockHwModule
from hwtHls.frontend.pyBytecode.pragma import _PyBytecodeIntrinsic
from hwtHls.llvm.llvmIr import Value, Type, FunctionType, Function, VectorOfTypePtr, BasicBlock, \
    ConstantInt, ConstantArray, APInt, TypeToIntegerType, \
    LlvmCompilationBundle, LLVMContext, LLVMStringContext, ArrayType, MDString, \
    ConstantAsMetadata, MDNode, Module, IRBuilder, UndefValue, PoisonValue, \
    GlobalVariable, GlobalValue, Align, AllocaInst, ValueToInstruction, ValueToAllocaInst, \
    TypeToArrayType, MaybeAlign, ValueToGlobalValue
from hwtHls.netlist.hdlTypeVoid import _HVoidOrdering, HdlType_isVoid
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.ssa.translation.toLlvmUtils import addHwtHlsFunctionMetadata, \
    ToLlvmIrTranslator_createOperatorConstructorDictionaries, \
    llvmFunctionSortArgsByName, ToLlvmIoRecordTuple, applyLateLoopPragma
from hwtLib.types.ctypes import uint32_t
from pyMathBitPrecise.bit_utils import iter_bits_sequences, get_bit_range


class ToLlvmIrTranslator():
    """
    A container class which contains all necessary objects for LLVM.
    It can also translate between hwtHls SSA and LLVM SSA (in booth directions).

    While converting there are several issues:
    1. LLVM does not have multi-level logic type like VHDL STD_LOGIC_VECTOR or Verilog wire/logic.
      * all x/z/u are replaced with 0 or with UndefValue if value is fully undefined
    2. LLVM does not have bit slicing and concatenation operators.
      * all replaced with zext, sext, trunc, hwtHls.bitrangeGet/hwtHls.bitConcat
    
    :ivar currentDef: dictionary mapping a value for each variable in each block
    :ivar ioNodeConstructors: dictionary of read/write statements associated with io used to construct HlsNetlist node later
    :ivar _variableInBlock: A dictionary holding a variable which currently
        contains an expression for each expression in each block.
        This dictionary is used to use already translated variable currently storing
        the expression instead of translating whole expression again.
    :ivar _allocaForVariable: an AllocaInst which represents memory for variable
    :ivar _initializedAllocaVariables: after AllocaInst is created it is not initialized
        after it is first written it is appears in this set, this is required for handling
        of the case where HlsRead output signal has been accessed before HlsRead itself was seen
        and thus variable was not initialized yet

    :note: Information about IO are stored in function attributes
    """

    def __init__(self, parentHwModule: HwModule,
                 dbgLogPassExec:Optional[StringIO],
                 llvmCliOptions:list[LlvmCliArgTuple],
                 llvmModuleName:str="hwtHlsModule"):
        self.llvm = LlvmCompilationBundle(llvmModuleName, llvmCliOptions)
        self.ctx: LLVMContext = self.llvm.ctx
        self.strCtx: LLVMStringContext = self.llvm.strCtx
        self.module: Module = self.llvm.module
        self.b: IRBuilder = self.llvm.builder
        self.parentHwModule = parentHwModule

        # :note: can not store Argument itself because it may reallocate if function type is mutated
        self.ioToArgIndex: Dict[HwIO, int] = {}
        # order of items in ioSorted corresponds to arguments of main function
        self.ioSorted: List[ToLlvmIoRecordTuple] = []

        self._afterTranslation: List[Callable[[ToLlvmIrTranslator], None]] = [
            llvmFunctionSortArgsByName,
            addHwtHlsFunctionMetadata,
            applyLateLoopPragma,
        ]
        self.placeholderObjectSlots = []
        self._lateLoopPragmaToApply: List[Tuple[BasicBlock, List["_PyBytecodeLoopPragma", ]]] = []

        self._allocaForVariable: Dict[RtlSignal, AllocaInst] = {}
        self._initializedAllocaVariables: Set[RtlSignal] = set()
        self._variableInBlock: Dict[BasicBlock, Dict[RtlSignal, Value]] = {}

        self._loop_stack: List[Tuple[BasicBlock, List[BasicBlock]]] = []
        self._dbgLogPassExec:Optional[StringIO] = dbgLogPassExec
        self._opConstructorMap, self._opConstructorMapCmp = ToLlvmIrTranslator_createOperatorConstructorDictionaries(self.b)
        self._dbgRootDir: Optional[Path] = None
        self._dbgSubDir: Optional[Path] = None
        

    def _getOrCreateAllocaForTmpVariable(self, var: RtlSignal,
                                         allocaKnownToBeMissing: bool):
        assert isinstance(var, RtlSignal), var
        alloca = None if allocaKnownToBeMissing else self._allocaForVariable.get(var)
        builder: IRBuilder = self.b
        if alloca is None:
            # ip = builder.saveIP()
            # entryBB: BasicBlock = next(iter(self.llvm.main))
            # term = entryBB.getTerminator()
            # if term is None:
            #    builder.SetInsertPoint(entryBB)
            # else:
            #    builder.SetInsertPoint(entryBB, entryBB.getTerminator())

            typeToLlvm = getattr(var._dtype, "toLlvm", None)
            if typeToLlvm is not None:
                Ty = typeToLlvm(self)
            else:
                # :attentino: variables on stack (alloca) must have minimum aligment of 1B otherwise
                #     load/store to different allocas would interfere with each other
                #     this allocates type as is and then it relies on TmpAllocaLoweringPass to
                #     widen it to handle problems with alignment
                Ty = self._translateType(var._dtype)

            alloca = builder.CreateAlloca(Ty, None, self.strCtx.addTwine(var._name))
            allocaInst = ValueToInstruction(alloca)
            allocaInst.setMetadata(
                self.strCtx.addStringRef("hwtHls.tmp.alloca"),
                self.mdGetTuple([], False))

            self._allocaForVariable[var] = alloca
            builder.CreateStore(UndefValue.get(Ty), alloca)  # initialize to undef to always have def before use
            # builder.restoreIP(ip)

        return alloca

    def _variableInBlock_insertNoRedef(self, block: BasicBlock, var: Union[RtlSignal, HConst], newVal: Union[Value, HConst], createAlloca: bool=False)\
            ->Tuple[BasicBlock, Union[Value, HConst]]:
        if not isinstance(var, HConst):
            varDict = self._variableInBlock.get(block, None)
            if varDict is None:
                # check for case that expression was already translated in this block
                varDict = self._variableInBlock[block] = {}
            varDict[var] = newVal

        if createAlloca:
            alloca = self._getOrCreateAllocaForTmpVariable(var, False)
            builder: IRBuilder = self.b
            builder.CreateStore(newVal, alloca, False)
            self._initializedAllocaVariables.add(var)

        return block, newVal

    def _variableInBlock_insertRedef(self,
                                     block: BasicBlock,
                                     var: RtlSignal,
                                     indexes: Optional[List[Union[RtlSignal, HConst]]],
                                     newVal: Union[Value, HConst]):
        """
        Handle store to variable and update current definitions
        """
        block, _newVal = self._handleVariableStore(var, indexes, block, newVal)

        varDict = self._variableInBlock.get(block, None)
        if varDict is None:
            varDict = self._variableInBlock[block] = {}
            wasDefined = False
        else:
            wasDefined = varDict.pop(var, None) is not None

        # transitively remove all users which were already defined because value of this variable was just changed
        if wasDefined:
            toRm = [*var.endpoints]
            while toRm:
                op = toRm.pop()
                if isinstance(op, HOperatorNode):
                    _wasDefined = varDict.pop(op.result, None) is not None
                    if _wasDefined:
                        toRm.extend(op.result.endpoints)

        if indexes:
            pass
        else:
            varDict[var] = _newVal

    def _handleVariableStoreBitVectorSlice(self, block: BasicBlock, var: RtlSignal, indexes: Union[HConst, Value], value: Value):
        assert isinstance(var._dtype, HBits), (var, var._dtype)
        _hwIO, _indexes, _sign_cast_seen = var._getIndexCascade()
        assert not _indexes, (var, "Must not be a slice of signal")
        if len(indexes) != 1 or not isinstance(var._dtype, HBits):
            raise NotImplementedError(block, var, indexes, value)

        i = indexes[0]
        if isinstance(i, Value):
            raise NotImplementedError("indexing using address variable, we need to use getelementptr/extractelement/insertelement etc.")

        else:
            assert isinstance(i, HConst), (block, var, indexes, value)
            if isinstance(i, HBitsConst):
                assert value.getType().isIntegerTy() and value.getType().getIntegerBitWidth() == 1, value
                low = int(i)
                high = low + 1

            else:
                assert isinstance(i, HSliceConst), (block, var, indexes, value)
                assert int(i.val.step) == -1, (block, var, indexes, value)
                low = int(i.val.stop)
                high = int(i.val.start)

            assert isinstance(var, RtlSignal), var
            width = var._dtype.bit_length()
            parts: List[Value] = []  # high first

            # append unmodified lower bits
            if low > 0:
                new_bb, new_var = self._translateExprToLlvm(block, var[low:0])
                parts.append(new_var)

            # append modified bits
            # if isinstance(value, HlsRead):
            #    parts.append(value._sig[value._dtype.bit_length():])

            # el
            if isinstance(value, Value):
                # assert value.origin is not None, value
                # assert isinstance(value.origin, RtlSignal), (value, value.origin)
                parts.append(value)

            else:
                new_bb, new_var = self._translateExprToLlvm(block, value)
                parts.append(new_var)

            if high < width:
                # append unmodified upper bits
                new_bb, new_var = self._translateExprToLlvm(block, var[width:high])
                parts.append(new_var)

            value = self.b.CreateBitConcat(parts)
        return new_bb, value

    def _handleVariableStore(self,
                      var: RtlSignal,
                      indexes: Tuple[Union[Value, HBitsConst, HSliceConst], ...],
                      block: BasicBlock,
                      value: Value) -> int:
        """
        :param variable: A variable which is being written to.
        :param indexes: A list of indexes where in the variable is written.
        :param block: A block where this is taking place.
        :param value: A value which is being written.

        :return: unique index of tmp variable for PHI function
        """
        assert isinstance(var, RtlSignal), var
        assert isinstance(block, BasicBlock), block
        assert isinstance(value, Value), value
        alloca = self._getOrCreateAllocaForTmpVariable(var, False)
        new_bb = block
        builder: IRBuilder = self.b

        storeCreated = False
        if indexes:
            if isinstance(var._dtype, HArray):
                assert len(indexes) == 1
                new_bb, alloca = self._translateExprSubscriptGEP(block, alloca, indexes[0])

            else:
                new_bb, value = self._handleVariableStoreBitVectorSlice(block, var, indexes, value)
        else:
            t: Type = value.getType()
            if t.isDoubleTy():
                pass
            elif t.isPointerTy():
                # copy content of value to alloca memory
                arrTy = TypeToArrayType(alloca.getAllocatedType())
                assert arrTy is not None, alloca
                elementWidth = arrTy.getElementType().getIntegerBitWidth()
                elementSize = elementWidth // 8
                if elementSize * 8 < elementWidth:
                    elementSize += 1
                size = arrTy.getNumElements() * elementSize  # :note: if size is not correct the DSEPass will remove memcopy
                builder.CreateMemCpy(alloca, MaybeAlign(1), value, MaybeAlign(1), size)
                storeCreated = True
            else:
                assert t.getScalarSizeInBits() == var._dtype.bit_length(), (var, t, var._dtype)

        if not storeCreated:
            builder.CreateStore(value, alloca, False)

        if not var.hasGenericName and isinstance(value, RtlSignal) and value.hasGenericName:
            # inherit name
            value.setName(self.strCtx.addTwine(var.name))
        self._initializedAllocaVariables.add(var)

        return new_bb, value

    def visit_Assignment(self, block: BasicBlock, o: HdlAssignmentContainer) -> BasicBlock:
        block, src = self._translateExprToLlvm(block, o.src)
        # this may result in:
        # * store instruction
        # * just the registration of the variable for the symbol
        #   * only a segment in bit vector can be assigned, this result in the assignment of the concatenation of previous and new value
        self._variableInBlock_insertRedef(block, o.dst, o.indexes, src)

        return block

    def visit_Assignments(self, block: BasicBlock, stm: Union[HdlAssignmentContainer, Sequence[HdlAssignmentContainer]]) -> BasicBlock:
        for _stm in flatten(stm):
            block = self.visit_Assignment(block, _stm)
        return block

    def visit_Write(self, block: BasicBlock, o: HlsWrite) -> BasicBlock:
        builder = self.b
        builder.SetInsertPoint(block)
        o._translateToLlvm(self, block)
        return block

    def visit_Read(self, block, r: HlsRead) -> Union[BasicBlock, Value]:
        if r._sig is not None and r._sig in self._initializedAllocaVariables:
            # already existing HlsRead was found, reuse existing value
            return self._translateExprToLlvm(block, r._sig)

        block, newVar = r._translateToLlvm(self, block)
        # HlsRead is a SsaValue and thus represents "variable"
        if r._sig is not None:
            # :note: it is None for reads of void
            return self._variableInBlock_insertNoRedef(block, r._sig, newVar, True)
        else:
            assert r._isBlocking and HdlType_isVoid(r._dtype), r
            return block, newVar

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

    def createFunctionPrototype(self, name: str, args:List[Tuple[str, Type, Type, int]], returnType: Type):
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

        return F

    def _translateType(self, hdlType: HdlType) -> Type:
        toLlvm = getattr(hdlType, "toLlvm", None)
        if toLlvm is not None:
            return toLlvm(self)
        elif isinstance(hdlType, (HBits, HStruct)):
            return Type.getIntNTy(self.ctx, hdlType.bit_length())
        elif HdlType_isVoid(hdlType):
            return Type.getVoidTy(self.ctx)
        elif isinstance(hdlType, HArray):
            return self._translateArrayType(hdlType)
        else:
            raise NotImplementedError(hdlType)

    def _translatePtrType(self, hdlType: HdlType, addressSpace: int) -> Type:
        if isinstance(hdlType, (HBits, HStruct)):
            return Type.getPointerTo(self.ctx, addressSpace)
        else:
            raise NotImplementedError(hdlType)

    def _translateArrayType(self, hdlType: HArray):
        elemType = self._translateType(hdlType.element_t)
        return ArrayType.get(elemType, int(hdlType.size))

    def _translateExprInt(self, v: int, t: HdlType):
        if v < 0:
            raise NotImplementedError()

        _v = APInt(t.getBitWidth(), self.strCtx.addStringRef(f"{v:x}"), 16)
        return ConstantInt.get(t, _v)

    def _translateExprIntLlvmTy(self, v: int, t: Type):
        if v < 0:
            raise NotImplementedError()

        _v = APInt(t.getIntegerBitWidth(), self.strCtx.addStringRef(f"{v:x}"), 16)
        return ConstantInt.get(t, _v)

    def _translateExprHConst(self, block: BasicBlock, v: HConst) -> Value:
        toLlvm = getattr(v, "toLlvm", None)
        if toLlvm is not None:
            return toLlvm(self)

        elif isinstance(v, HBitsConst):
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
            assert isinstance(v, _PyBytecodeIntrinsic)
            if isinstance(v, HardBlockHwModule):
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
            else:
                fn = v
            return fn

        elif HdlType_isVoid(v._dtype):
            return ConstantInt.get(Type.getIntNTy(self.ctx, 1), APInt(1, self.strCtx.addStringRef(f"1"), 16))

        elif isinstance(v._dtype, HArray):
            # :see: CreateGlobalDataWithGEP
            arrayTy = self._translateArrayType(v._dtype)
            _block, items = self._translateExprsToLlvm(block, v)
            assert _block is block, ("During translation of constants there was no reason to new block to appear", _block, block)
            newCRom = ConstantArray.get(arrayTy, items)
            isConstant = True
            newArray = GlobalVariable(self.module, arrayTy,
                                      isConstant, GlobalVariable.PrivateLinkage,
                                      newCRom)
            newArray.setUnnamedAddr(GlobalValue.UnnamedAddr.Global)
            newArray.setAlignment(Align(1))
            return newArray

        else:
            raise NotImplementedError(v)

    def _translateExprsToLlvm(self, block: BasicBlock, variables: Sequence[Union[RtlSignal, Value, HConst]]):
        results = []
        for v in variables:
            block, _v = self._translateExprToLlvm(block, v)
            results.append(_v)
        return block, results

    def _createLoadFromTmpAllocaIfExists(self, builder: IRBuilder, block: BasicBlock, var: RtlSignal):
        alloca = self._allocaForVariable.get(var)
        if alloca is not None:
            if var not in self._initializedAllocaVariables:
                if var.drivers:
                    d = var.singleDriver()
                    if isinstance(d, HlsRead):
                        self.visit_Read(block, d)
                    else:
                        raise NotImplementedError("This was supposed to be the case only for tmp variables for HlsRead results", var, d)

                    self._initializedAllocaVariables.add(var)

            # this is known variable, create load from it
            name = self.strCtx.addTwine(var._name)
            if isinstance(var._dtype, HArray):
                llvmValue = alloca
            else:
                allocatedTy = self._translateType(var._dtype)
                llvmValue = builder.CreateLoad(allocatedTy, alloca, False, name)
            return self._variableInBlock_insertNoRedef(block, var, llvmValue)
        else:
            return None

    def _setInsertPointBeforeTerminator(self, block: BasicBlock):
        builder = self.b
        term = block.getTerminator()
        if term is not None:
            builder.SetInsertPoint(block, term)
        else:
            builder.SetInsertPoint(block)

    def _translateExprToLlvm(self, block: BasicBlock, var: Union[RtlSignal, Value, HConst], allowHConst:bool=False) -> Tuple[BasicBlock, Union[Value, HConst]]:
        """
        Translate RtlSignal expression to SSA with constant propagation and expression cache
        """
        if isinstance(var, Value):
            return block, var

        if isinstance(var, HwIOSignal):
            var = var._sig  # normalize to use RtlSignal only

        varDict = self._variableInBlock.get(block, None)
        if varDict is not None:
            # check for case that expression was already translated in this block
            cur = varDict.get(var, None)
            if cur is not None:
                return block, cur

        builder = self.b

        allocaLoad = self._createLoadFromTmpAllocaIfExists(builder, block, var)
        if allocaLoad is not None:
            return allocaLoad

        if isinstance(var, RtlSignal):
            try:
                op = var.singleDriver()
            except SignalDriverErr:
                op = None

            if op is None or not isinstance(op, HOperatorNode):
                if op is None:
                    # initial set
                    llvmValue = self._translateExprHConst(block, var._dtype.from_py(None))
                    return self._variableInBlock_insertNoRedef(block, var, llvmValue)
                elif isinstance(op, HdlPortItem):
                    raise NotImplementedError(op)
                elif isinstance(op, HlsRead):
                    # raise AssertionError("Result of HlsRead should already have tmp alloca created in constructor and this code should never been reached", op)
                    assert var is op._sig, (var, op._sig)
                    return self.visit_Read(block, op)
                else:
                    raise NotImplementedError(op)

            if op.operator in (HwtOps.BitsAsVec, HwtOps.BitsAsUnsigned) and not var._dtype.signed and not op.operands[0]._dtype.signed:
                # skip implicit conversions between vec without sign and unsigned
                assert len(op.operands) == 1
                return self._translateExprToLlvm(block, op.operands[0])

            elif (op.operator == HwtOps.INDEX
                and var._dtype.bit_length() == 1
                and len(op.operands) == 2
                and isinstance(op.operands[1], HBitsConst)
                and int(op.operands[1]) == 0
                and op.operands[0]._dtype.bit_length() == 1):
                # skip indexing on 1b vectors/ 1b bits
                return self._translateExprToLlvm(block, op.operands[0])

            ops: List[Union[Value, HConst]] = []

            precompute = var._dtype._PRECOMPUTE_CONSTANT_SIGNALS
            for o in op.operands:
                precompute &= o._dtype._PRECOMPUTE_CONSTANT_SIGNALS
                block, _o = self._translateExprToLlvm(block, o, allowHConst=True)
                ops.append(_o)
                if precompute and not isinstance(_o, HConst):
                    precompute = False

            sig = var
            if precompute:
                var = op.operator._evalFn(*ops)
            else:
                if op.operator == HwtOps.CONCAT:
                    ops = list(reversed(ops))
                elif op.operator == HwtOps.TERNARY:
                    cond, trueVal, falseVal = ops
                    ops = (trueVal, cond, falseVal)

                block, var = self._translateExprOperator(block, op, op.operator, var._dtype, ops, var._name)

            # we know for sure that this in in this block that is why we do not need to use readVariable
            return self._variableInBlock_insertNoRedef(block, sig, var)

        elif isinstance(var, HConst):
            if allowHConst:
                return block, var
            else:
                return block, self._translateExprHConst(block, var)

        elif isinstance(var, HwIOStruct):
                var = HwIO_pack(var)
                return self._translateExprToLlvm(block, var)
        elif isinstance(var, HlsRead):
            return self.visit_Read(block, var)

        raise NotImplementedError(var)

    def _translateExprSubscriptGEP(self, block: BasicBlock, arr: Union[Value, HArrayRtlSignal, HArrayConst],
                                    index0: Union[Value, HConst],):
        block, index0 = self._translateExprToLlvm(block, index0)
        index_t = index0.getType()
        indexes = [self._translateExprIntLlvmTy(0, index_t), ]
        indexes.append(index0)
        # if isinstance(arr, Value):
        alloca: AllocaInst = ValueToAllocaInst(arr)
        if alloca is not None:
            arrTy = alloca.getAllocatedType()
        else:
            globalValue = ValueToGlobalValue(arr)
            assert globalValue is not None, arr
            assert globalValue.getType().isPointerTy(), globalValue
            data = globalValue.getOperand(0)
            arrTy = data.getType()

        arrTy = TypeToArrayType(arrTy)
        assert arrTy is not None, ("index operator only on array arrays", alloca)

        # else:
        #    arrTy: ArrayType = self._translateArrayType(arr._dtype)
        #    assert arrTy is not None, ("index operator only on array arrays", arr._dtype)
        #    block, arr = self._translateExprToLlvm(block, arr)

        # elmT = arrTy.getElementType()
        ptr = self.b.CreateGEP(arrTy, arr, indexes)
        return block, ptr  # , elmT

    def _translateExprSubscript(self, block: BasicBlock, op0: Value, op1: Union[Value, HConst],
                                instrName: str, resTy: HdlType):
        b: IRBuilder = self.b
        block, op0 = self._translateExprToLlvm(block, op0)
        op0t = op0.getType()
        if op0t.isIntegerTy():
            # bitvector slice
            assert isinstance(op1, HConst), op1
            if isinstance(op1._dtype, HSlice):
                op1 = int(op1.val.stop)
            else:
                op1 = int(op1)

            return block, b.CreateBitRangeGetConst(op0, op1, resTy.bit_length())

        elif op0t.isPointerTy():
            # load from array
            elmT = resTy
            if isinstance(elmT, HdlType):
                assert isinstance(elmT, HBits)
                elmT = self._translateType(elmT)

            volatile = not isinstance(op0, (GlobalVariable, GlobalValue))
            block, ptr = self._translateExprSubscriptGEP(block, op0, op1)
            name = self.strCtx.addTwine(instrName)
            return block, b.CreateLoad(elmT, ptr, volatile, name)

        else:
            raise NotImplementedError("operator[]", op0, op1)

    def _translateExprOperator(self, block: BasicBlock, instr: HlsNetNodeOperator, operator: HOperatorDef, resTy: HdlType,
                              operands: Tuple[Union[Value, HConst]],
                              instrName: str) -> Tuple[BasicBlock, Value]:
        b = self.b
        if operator == HwtOps.CONCAT and isinstance(resTy, HBits):
            block, ops = self._translateExprsToLlvm(block, operands)
            return block, b.CreateBitConcat(ops)

        elif operator == HwtOps.INDEX:
            op0, op1 = operands
            return self._translateExprSubscript(block, op0, op1, instrName, resTy)

        else:
            block, args = self._translateExprsToLlvm(block, operands)
            if operator in (HwtOps.BitsAsSigned, HwtOps.BitsAsUnsigned, HwtOps.BitsAsVec):
                op0, = args
                # LLVM uses sign/unsigned variants of instructions and does not have signed/unsigned as a part of type or variable
                return block, op0

            name = self.strCtx.addTwine(instrName if instrName else "")
            if operator == HwtOps.NOT:
                op0, = args
                # op0 xor -1
                mask = APInt.getAllOnes(resTy.bit_length())
                return block, b.CreateXor(op0, ConstantInt.get(TypeToIntegerType(op0.getType()), mask), name)

            elif operator == HwtOps.MINUS_UNARY:
                op0, = args
                return block, b.CreateNeg(op0, name, False, False)
            elif operator == HwtOps.TERNARY:
                if len(operands) == 1:
                    return self._translateExprToLlvm(block, args[0])
                else:
                    # :see: :meth:`HlsNetlistToAbcAig._translate`
                    if len(operands) == 3:
                        opTrue, opC, opFalse = args
                        assert opC.getType().getIntegerBitWidth() == 1, opC
                        assert opTrue.getType() == opFalse.getType(), (opTrue, opFalse)
                        return block, b.CreateSelect(opC, opTrue, opFalse, name, None)
                    else:
                        assert len(operands) % 2 == 1, operands
                        prevVal = None
                        # mux must be build from end so first condition ends up at the top of expression (bottom of code)
                        for v, c in reversed(tuple(grouper(2, args))):
                            if prevVal is None:
                                assert c is None
                                prevVal = v
                            else:
                                assert c.getType().getIntegerBitWidth() == 1, c
                                prevVal = b.CreateSelect(c, v, prevVal, name, None)

                        return block, prevVal

            elif operator == HwtOps.CALL:
                args = tuple(args)
                fn = operands[0]

                isHardblock = isinstance(fn, HardBlockHwModule)
                if isHardblock:
                    _args = [self._translateExprInt(fn.placeholderObjectId, Type.getIntNTy(self.ctx, 32))]
                    _args.extend(args[1:])
                else:
                    _args = list(args[1:])
                res = fn.translateToLlvm(b, _args)

                return block, res

            elif isinstance(operator, HOperatorDefLlvm):
                return block, operator.llvmOperatorConstructor(b, instr, *args, name)
            else:
                constructor_fn = self._opConstructorMap.get(operator, None)
                if constructor_fn is not None:
                    return block, constructor_fn(*args, name)
                else:
                    assert len(operands) == 2, instr
                    _opConstructorMap2 = self._opConstructorMapCmp
                    return block, _opConstructorMap2[operator](*args, name)
