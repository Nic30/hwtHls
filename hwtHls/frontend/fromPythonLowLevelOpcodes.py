import builtins
from dis import Instruction, dis
from inspect import ismethod
import operator
from types import FunctionType, CellType, MethodType
from typing import Callable, Dict, Union, Optional, Sequence

from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.sliceUtils import slice_to_HSlice
from hwt.hdl.types.typeCast import toHVal
from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStruct
from hwt.hwIOs.std import HwIOSignal
from hwt.mainBases import HwIOBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.frame import PyBytecodeFrame
from hwtHls.frontend.hObjListUtils import HwIOArray_getHdlType
from hwtHls.frontend.hwIterator import HwIterator
from hwtHls.frontend.indexExpansion import expandBeforeUse, \
    PyObjectHwSubscriptRef, expandBeforeUseSequence
from hwtHls.frontend.instructions import CMP_OPS, BINARY_OPS, UN_OPS, BUILD_OPS, BINARY_OP, NOP, \
    POP_TOP, COPY, SWAP, LOAD_DEREF, LOAD_ATTR, LOAD_FAST, LOAD_SUPER_ATTR, LOAD_CONST, LOAD_GLOBAL, \
    LOAD_METHOD, LOAD_CLOSURE, STORE_ATTR, STORE_FAST, STORE_DEREF, CALL, CALL_FUNCTION_EX, CALL_INTRINSIC_1, \
    COMPARE_OP, GET_ITER, UNPACK_SEQUENCE, MAKE_FUNCTION, STORE_SUBSCR, EXTENDED_ARG, DELETE_DEREF, DELETE_FAST, \
    LOAD_FAST_LOAD_FAST, STORE_FAST_STORE_FAST, IS_OP, RAISE_VARARGS, LOAD_ASSERTION_ERROR, \
    RESUME, MAKE_CELL, NULL, PUSH_NULL, BINARY_SUBSCR, COPY_FREE_VARS, \
    CONTAINS_OP, INPLACE_UPDATE_OPS, LOAD_BUILD_CLASS, BINARY_SLICE, STORE_SLICE, \
    LOAD_FAST_CHECK, LOAD_FAST_AND_CLEAR, END_FOR, CALL_INTRINSIC_1_FUNCTIONS, \
    CONVERT_VALUE, FORMAT_SIMPLE, STORE_FAST_LOAD_FAST, CALL_KW, \
    SET_FUNCTION_ATTRIBUTE, FORMAT_WITH_SPEC, TO_BOOL
from hwtHls.frontend.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pragmaPreproc import PyBytecodeInPreproc, \
    PyBytecodeInline, _PyBytecodePragma, PyBytecodePreprocHwCopy
from hwtHls.frontend.pyBytecodeUtils import ObjectWithHlsStoreOverride
from hwtHls.frontend.statementsRead import HlsRead
from hwtHls.frontend.statementsWrite import HlsWrite
from hwtHls.llvm.llvmIr import Value, BasicBlock, IRBuilder
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


def _isSameOrIsSameTuple(a, b):
    if a is b:
        return True
    elif isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b):
        for ai, bi in zip(a, b):
            if not _isSameOrIsSameTuple(ai, bi):
                return False
        return True
    return  False


class PyBytecodeToSsaLowLevelOpcodes():
    """
    https://docs.python.org/3/library/dis.html
    https://github.com/zrax/pycdc
    """
    ANY_HWVALUE_CLASS = (HConst, RtlSignal, HwIO, Value, ObjectWithHlsStoreOverride)
    ANY_HWSTATEMENT_CLASS = (HlsWrite, HlsRead, HdlAssignmentContainer, _PyBytecodePragma)

    def __init__(self):
        self.opcodeDispatch: Dict[int, Callable[[], BasicBlock]] = {
            NOP: self.opcode_NOP,
            POP_TOP: self.opcode_POP_TOP,
            END_FOR: self.opcode_END_FOR,
            COPY: self.opcode_COPY,
            SWAP: self.opcode_SWAP,

            BINARY_OP: self.opcode_BINARY_OP,
            CONTAINS_OP: self.opcode_CONTAINS_OP,
            BINARY_SUBSCR: self.opcode_BINARY_SUBSCR,
            BINARY_SLICE: self.opcode_BINARY_SLICE,
            DELETE_FAST: self.opcode_DELETE_FAST,
            DELETE_DEREF: self.opcode_DELETE_DEREF,
            LOAD_CLOSURE: self.opcode_LOAD_CLOSURE,
            LOAD_DEREF: self.opcode_LOAD_DEREF,
            STORE_DEREF: self.opcode_STORE_DEREF,
            LOAD_ATTR: self.opcode_LOAD_ATTR,
            LOAD_FAST: self.opcode_LOAD_FAST,
            LOAD_FAST_CHECK: self.opcode_LOAD_FAST_CHECK,
            LOAD_FAST_AND_CLEAR: self.opcode_LOAD_FAST_AND_CLEAR,
            LOAD_FAST_LOAD_FAST: self.opcode_LOAD_FAST_LOAD_FAST,
            LOAD_CONST: self.opcode_LOAD_CONST,
            LOAD_GLOBAL: self.opcode_LOAD_GLOBAL,
            LOAD_METHOD: self.opcode_LOAD_METHOD,
            LOAD_SUPER_ATTR: self.opcode_LOAD_SUPER_ATTR,
            STORE_ATTR: self.opcode_STORE_ATTR,
            STORE_FAST: self.opcode_STORE_FAST,
            STORE_FAST_STORE_FAST: self.opcode_STORE_FAST_STORE_FAST,
            STORE_FAST_LOAD_FAST: self.opcode_STORE_FAST_LOAD_FAST,
            COPY_FREE_VARS: self.opcode_COPY_FREE_VARS,
            RESUME: self.opcode_RESUME,
            CALL: self.opcode_CALL,
            CALL_KW: self.opcode_CALL_KW,
            CALL_FUNCTION_EX: self.opcode_CALL_FUNCTION_EX,
            CALL_INTRINSIC_1: self.opcode_CALL_INTRINSIC_1,
            COMPARE_OP: self.opcode_COMPARE_OP,
            GET_ITER: self.opcode_GET_ITER,
            EXTENDED_ARG: self.opcode_EXTENDED_ARG,
            UNPACK_SEQUENCE: self.opcode_UNPACK_SEQUENCE,
            MAKE_FUNCTION: self.opcode_MAKE_FUNCTION,
            SET_FUNCTION_ATTRIBUTE: self.opcode_SET_FUNCTION_ATTRIBUTE,
            STORE_SUBSCR: self.opcode_STORE_SUBSCR,
            STORE_SLICE: self.opcode_STORE_SLICE,
            CONVERT_VALUE: self.opcode_CONVERT_VALUE,
            FORMAT_SIMPLE: self.opcode_FORMAT_SIMPLE,
            FORMAT_WITH_SPEC: self.opcode_FORMAT_WITH_SPEC,
            IS_OP: self.opcode_IS_OP,
            RAISE_VARARGS: self.opcode_RAISE_VARARGS,
            PUSH_NULL: self.opcode_PUSH_NULL,
            LOAD_ASSERTION_ERROR: self.opcode_LOAD_ASSERTION_ERROR,
            LOAD_BUILD_CLASS: self.opcode_LOAD_BUILD_CLASS,
            MAKE_CELL: self.opcode_MAKE_CELL,
            TO_BOOL: self.opcode_TO_BOOL,
        }
        opD = self.opcodeDispatch
        for createFn, opcodes in [
                (self.opcodeMakeUnaryOp, UN_OPS),
                (self.opcodeMakeBuildOp, BUILD_OPS),
                (self.opcodeMakeInplaceUpdate, INPLACE_UPDATE_OPS),
            ]:
            for opcode, op in opcodes.items():
                opD[opcode] = createFn(op)

    def _stackIndex(self, stack: list, index: int):
        # in C:
        # TOP    = stack_pointer[-1]
        # SECOND = stack_pointer[-2]
        # here in python:
        # TOP    = stack[-1] = stack[len(stack)-1] = item0
        # SECOND = stack[-2] = stack[len(stack)-2] = item1
        return len(stack) - index

    def opcode_NOP(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        # Do nothing code. Used as a placeholder by the bytecode optimizer.
        return curBlock

    @staticmethod
    def _isHwtCall(obj):
        if not isinstance(obj, RtlSignal):
            return False
        try:
            d = obj.singleDriver()
        except:
            return False
        return isinstance(d, HOperatorNode) and d.operator == HwtOps.CALL

    def _visit_HlsRead_HlsWrite_PyBytecodePragma(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, res):
        toLlvm = self.toLlvm
        if isinstance(res, HlsWrite):
            curBlock = toLlvm.visit_Write(curBlock, res)
        elif isinstance(res, HlsRead):
            curBlock, _ = toLlvm.visit_Read(curBlock, res)
        elif isinstance(res, HdlAssignmentContainer):
            curBlock = toLlvm.visit_Assignment(curBlock, res)
        elif self._isHwtCall(res):
            curBlock, _ = toLlvm._translateExprToLlvm(curBlock, res)
        elif isinstance(res, _PyBytecodePragma):
            res.apply(self, frame, curBlock, instr)
        elif isinstance(res, (list, tuple)) and len(res) > 0 and isinstance(res[0], self.ANY_HWSTATEMENT_CLASS):
            # if this a list or tuple of objects left on stack try if objects inside should be translated to ssa
            for _res in res:
                curBlock = self._visit_HlsRead_HlsWrite_PyBytecodePragma(frame, curBlock, instr, _res)

        return curBlock

    def opcode_POP_TOP(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        res = frame.stack.pop()
        curBlock, res = expandBeforeUse(self, instr.offset, frame, res, curBlock)
        if isinstance(res, HlsWrite):
            res: HlsWrite
            dst = res.dst
            if isinstance(dst, PyObjectHwSubscriptRef):
                hls = self.hls
                if isinstance(dst.sequence, IoProxyAddressed):
                    raise AssertionError(dst, "This should already been expanded when HlsWrite was generated")
                return dst.expandSetitemAsSwitchCase(self, instr.offset, frame, curBlock,
                                                     lambda i, _dst: hls.write(res.src, _dst))

        curBlock = self._visit_HlsRead_HlsWrite_PyBytecodePragma(frame, curBlock, instr, res)

        return curBlock

    def opcode_END_FOR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Removes the top two values from the stack.
        Equivalent to POP_TOP; POP_TOP. Used to clean up at the end of loops, hence the name.
        Added in version 3.12.
        """
        curBlock = self.opcode_POP_TOP(frame, curBlock, instr)
        # https://github.com/python/cpython/issues/121399
        return curBlock

    def opcode_COPY(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Push the i-th item to the top of the stack. The item is not removed from its original location.
        New in version 3.11.
        """
        stack = frame.stack
        stack.append(stack[self._stackIndex(stack, instr.arg)])
        return curBlock

    def opcode_SWAP(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Swap TOS with the item at position i.
        New in version 3.11.
        """
        stack = frame.stack
        i = self._stackIndex(stack, instr.arg)
        iItem = stack[i]
        TOS = stack[-1]
        stack[i] = TOS
        stack[-1] = iItem
        return curBlock

    def opcode_BINARY_SUBSCR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, key=NULL) -> BasicBlock:
        """
        Implements:

        key = STACK.pop()
        container = STACK.pop()
        STACK.append(container[key])
        """
        stack = frame.stack

        if key is NULL:
            key = stack.pop()
        container = stack.pop()
        curBlock, container = expandBeforeUse(self, instr.offset, frame, container, curBlock)
        curBlock, key = expandBeforeUse(self, instr.offset, frame, key, curBlock)
        if (isinstance(key, (RtlSignal, HwIO, Value)) and
            not isinstance(container, (RtlSignal, Value, HConst))):
            # if this is indexing using hw value on non hw object we need to expand it to a switch-case on individual cases
            # must generate blocks for switch cases,
            # for this we need container to keep track of start/end for each block because we do not have this newly generated blocks in original CFG
            o = PyObjectHwSubscriptRef(instr.offset, container, key)
            stack.append(o)
            return curBlock

        stack.append(container[key])

        return curBlock

    def _popSliceFromStack(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        stack = frame.stack
        end = stack.pop()
        start = stack.pop()

        curBlock, end = expandBeforeUse(self, instr.offset, frame, end, curBlock)
        curBlock, start = expandBeforeUse(self, instr.offset, frame, start, curBlock)
        key = slice(start, end)
        return key, curBlock

    def opcode_BINARY_SLICE(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Implements:
     
        end = STACK.pop()
        start = STACK.pop()
        container = STACK.pop()
        STACK.append(container[start:end])
        
        Added in version 3.12.
        """
        key, curBlock = self._popSliceFromStack(frame, curBlock, instr)
        return self.opcode_BINARY_SUBSCR(frame, curBlock, instr, key=key)

    def opcode_CONTAINS_OP(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        CONTAINS_OP(invert)
        Performs in comparison, or not in if invert is 1.
        New in version 3.9.
        """
        stack = frame.stack
        b = stack.pop()
        a = stack.pop()
        curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        curBlock, b = expandBeforeUse(self, instr.offset, frame, b, curBlock)
        invert = instr.argval
        if invert:
            res = a not in b
        else:
            res = a in b
        stack.append(res)
        return curBlock

    def opcode_BINARY_OP(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        stack = frame.stack
        isInplace, binOp = BINARY_OPS[instr.arg]

        b = stack.pop()
        if isInplace:
            curBlock, b = expandBeforeUse(self, instr.offset, frame, b, curBlock)
            a = stack.pop()
            # we expand as a regular bin op, and store later in store_subscript
            curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        else:
            a = stack.pop()
            curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
            curBlock, b = expandBeforeUse(self, instr.offset, frame, b, curBlock)

        stack.append(binOp(a, b))
        return curBlock

    def opcode_DELETE_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        localsplus = frame.localsplus
        v = localsplus[instr.arg]
        assert v is not NULL, "Delete of uninitalized"
        localsplus[instr.arg] = NULL
        return curBlock

    def opcode_DELETE_DEREF(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        v = frame.localsplus[instr.arg]
        assert v.get() is not NULL, "Delete of uninitalized"
        v.set(NULL)
        return curBlock

    def opcode_LOAD_CLOSURE(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        # nested scopes: access the cell object
        # Pushes a reference to the cell contained in slot i of the cell and free variable storage.
        # The name of the variable is co_cellvars[i] if i is less than the length of co_cellvars.
        # Otherwise it is co_freevars[i - len(co_cellvars)].
        v = frame.localsplus[instr.arg]
        assert isinstance(v, CellType), v
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_DEREF(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        # nested scopes: access a variable through its cell object
        v = frame.localsplus[instr.arg]
        assert isinstance(v, CellType), (v, "LOAD_DEREF should be used only with Cell instances")
        _v = v.cell_contents
        assert _v is not NULL, (instr.argval, "used before defined")
        frame.stack.append(_v)
        return curBlock

    def opcode_STORE_DEREF(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        # nested scopes: access a variable through its cell object
        vVal = frame.stack.pop()
        curBlock, vVal = expandBeforeUse(self, instr.offset, frame, vVal, curBlock)
        v: CellType = frame.localsplus[instr.arg]
        assert isinstance(v, CellType), v
        _v = v.cell_contents
        preprocVarKey = instr.arg
        if preprocVarKey not in frame.preprocVars:
            if _v is NULL and isinstance(vVal, self.ANY_HWVALUE_CLASS):
                # only if it is a value which generates HW variable
                _v = self._initializeStorageCellForHwSignal(instr.argval, vVal)

            if isinstance(_v, (RtlSignal, HwIO, ObjectWithHlsStoreOverride)):
                # only if it is a hw variable, create assignment to HW variable
                v.cell_contents = _v
                return self._storeToHwSignal(curBlock, _v, vVal)

        if isinstance(vVal, PyBytecodeInPreproc):
            vVal = vVal.ref
            frame.preprocVars.add(preprocVarKey)

        v.cell_contents = vVal
        return curBlock

    def opcode_LOAD_ATTR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        LOAD_ATTR(namei)

        If the low bit of namei is not set, this replaces STACK[-1] with getattr(STACK[-1], co_names[namei>>1]).

        If the low bit of namei is set, this will attempt to load a method named co_names[namei>>1] from the STACK[-1] object.
        STACK[-1] is popped. This bytecode distinguishes two cases: if STACK[-1] has a method with the correct name,
        the bytecode pushes the unbound method and STACK[-1]. STACK[-1] will be used as the first argument (self) by
        CALL or CALL_KW when calling the unbound method. Otherwise, the object returned by the attribute lookup and NULL are pushed (in that order).
        
        Changed in version 3.13: The push order changed to keep the callable at a fixed stack position for CALL:
        the attribute or unbound method is now pushed before the NULL/self marker (previously the marker was pushed first).
         """
        stack = frame.stack
        pushSelfOrNull = instr.arg & 1
        v = stack[-1]
        v = getattr(v, instr.argval)
        if pushSelfOrNull:
            if ismethod(v):
                stack[-1] = v.__func__
                stack.append(v.__self__)
            else:
                call = getattr(v, "__call__", None)
                if call and ismethod(call):
                    # handle the case for callable object
                    stack[-1] = call.__func__
                    stack.append(call.__self__)
                else:
                    # case for normal function without self
                    stack[-1] = v
                    stack.append(NULL)
        else:
            stack[-1] = v

        return curBlock

    def _LOAD_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, arg: int, argval:str, check=False, clear=False) -> BasicBlock:
        v = frame.localsplus[arg]
        if check:
            if v is NULL:
                raise UnboundLocalError(argval, "used before defined")
        if clear:
            frame.localsplus[arg] = NULL
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, check=False, clear=False) -> BasicBlock:
        """
        Pushes a reference to the local co_varnames[var_num] onto the stack.

        Changed in version 3.12: This opcode is now only used in situations where the local variable is guaranteed
        to be initialized. It cannot raise UnboundLocalError.

        """
        return self._LOAD_FAST(frame, curBlock, instr.arg, instr.argval, check, clear)

    def opcode_LOAD_FAST_LOAD_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, check=False, clear=False) -> BasicBlock:
        """
        Pushes references to co_varnames[var_nums >> 4] and co_varnames[var_nums & 15] onto the stack.

        Added in version 3.13.
        :note: TOS is the first argument
        """
        curBlock = self._LOAD_FAST(frame, curBlock, instr.arg >> 4, instr.argval[1], check, clear)
        curBlock = self._LOAD_FAST(frame, curBlock, instr.arg & 0xF, instr.argval[0], check, clear)
        return curBlock

    def opcode_LOAD_FAST_CHECK(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        return self.opcode_LOAD_FAST(frame, curBlock, instr, check=True)

    def opcode_LOAD_FAST_AND_CLEAR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        return self.opcode_LOAD_FAST(frame, curBlock, instr, clear=True)

    def opcode_LOAD_CONST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        frame.stack.append(instr.argval)
        return curBlock

    def opcode_LOAD_GLOBAL(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Loads the global named co_names[namei>>1] onto the stack.
        Changed in version 3.13: The push order changed to keep the callable at a fixed stack position for CALL: 
        the global is now pushed before the NULL marker (previously the marker was pushed first).
        """

        if instr.argval in frame.fn.__globals__:
            v = frame.fn.__globals__[instr.argval]
        else:
            # assert instr.argval in builtins.__dict__, instr.argval
            v = builtins.__dict__[instr.argval]

        assert v is not NULL, (instr.argval, "used before defined")
        frame.stack.append(v)
        if instr.arg & 0b1:
            frame.stack.append(NULL)

        return curBlock

    def opcode_LOAD_METHOD(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Loads a method named co_names[namei] from the TOS object. TOS is popped. 
        This bytecode distinguishes two cases: if TOS has a method with the correct name,
        the bytecode pushes the unbound method and TOS. TOS will be used as
        the first argument (self) by CALL when calling the unbound method.
        Otherwise, NULL and the object return by the attribute lookup are pushed.
        New in version 3.7.
        """
        stack = frame.stack
        TOS = stack[-1]
        m = getattr(TOS, instr.argval)
        if isinstance(m, MethodType) and m.__self__ is None:
            # is unbound method
            stack.append(TOS)
        else:
            stack.append(NULL)

        return curBlock

    def opcode_LOAD_SUPER_ATTR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        
        LOAD_SUPER_ATTR(namei)
    
        This opcode implements super(), both in its zero-argument and two-argument forms (e.g. super().method(), super().attr and
        super(cls, self).method(), super(cls, self).attr).
    
        It pops three values from the stack (from top of stack down):
    
            self: the first argument to the current method
            cls: the class within which the current method was defined
                the global super
    
        With respect to its argument, it works similarly to LOAD_ATTR, except that namei is shifted left by 2 bits instead of 1.
        The low bit of namei signals to attempt a method load, as with LOAD_ATTR, which results in pushing the loaded method and
        NULL (in that order). When it is unset a single value is pushed to the stack.
        The second-low bit of namei, if set, means that this was a two-argument call to super() (unset means zero-argument).
    
        Added in version 3.12.
    
        Changed in version 3.13: The push order for method loads changed to keep the callable at a fixed stack position for CALL:
        the loaded method is now pushed before the NULL marker (previously the marker was pushed first).
        """
        raise NotImplementedError(instr)

    def _initializeStorageCellForHwSignal(self, name: Optional[str],
                                          vVal: Union[RtlSignal, HwIOBase,
                                                      HConst, Value,
                                                      ObjectWithHlsStoreOverride]):
        """
        :returns: hls variable (RtlSignal which will be used to represent this variable)
        
        :param vVal: value to be stored
        """
        # only if it is a value which generates HW variable
        if isinstance(vVal, Value):
            _t = vVal.getType()
            if _t.isDoubleTy():
                t = self._getHFloatType()
            else:
                t = HBits(_t.getScalarSizeInBits())
        elif isinstance(vVal, ObjectWithHlsStoreOverride):
            return vVal.hlsOverrideInitializeStorageCell(self, name)
        elif isinstance(vVal, HwIOArray):
            # construct variable for every item and return new HwIOArray which will be
            # the container of ev values
            v = HwIOArray(
                self._initializeStorageCellForHwSignal(f"{name:s}[{i:d}]", vItem)
                for i, vItem in enumerate(vVal)
            )
            v._dtype = HwIOArray_getHdlType(vVal)
            v._name = name
            return v
        else:
            t = HwIOArray_getHdlType(vVal)

        if isinstance(vVal, RtlSignal) and vVal._hasGenericName:
            # add name also to right side of assignment because this is likely a variable definition and we want
            # to name the defined value
            vVal._name = name
            vVal._hasGenericName = False

        v = self.hls.var(name, t)
        return v

    def _storeToHwSignalArrayLoad(self, curBlock: BasicBlock, src: Sequence):
        toLlvm = self.toLlvm
        loadedSrcs: HwIOArray[Value] = HwIOArray()
        for srcItem in src:
            if isinstance(srcItem, HwIOArray):
                block, srcItem = self._storeToHwSignalArrayLoad(curBlock, srcItem)
            else:
                block, srcItem = toLlvm._translateExprToLlvm(curBlock, srcItem)
            loadedSrcs.append(srcItem)
        return block, loadedSrcs

    def _storeToHwSignalArrayStore(self, block: BasicBlock,
                                   dst: HwIOArray[Union[RtlSignal, HwIOBase, ObjectWithHlsStoreOverride]],
                                   src: HwIOArray[Union[Value], HwIOArray]):
        assert isinstance(dst, HwIOArray), dst
        assert len(dst) == len(src), (len(dst), len(src))
        # toLlvm = self.toLlvm
        for dstElm, srcElm in zip(dst, src):
            if isinstance(dstElm, HwIOArray):
                self._storeToHwSignalArrayStore(block, dstElm, srcElm)
            else:
                self._storeToHwSignal(block, dstElm, srcElm)
                # toLlvm._variableInBlock_insertRedef(block, dstElm, [], srcElm)

    def _storeToHwSignal(self, curBlock: BasicBlock, dst: Union[RtlSignal, HwIOBase, ObjectWithHlsStoreOverride], src):
        if isinstance(dst, ObjectWithHlsStoreOverride):
            return dst.hlsStoreOverride(self, curBlock, src)
        toLlvm = self.toLlvm
        srcIsRead = isinstance(src, HlsRead)
        if isinstance(src, Value) and not srcIsRead:
            if isinstance(dst, HwIOBase):
                if isinstance(dst, HwIOStruct):
                    # HwIOStruct is special case because it may be stored as a flat vector and interpreted as structured type only in frontend
                    w = src.getType().getIntegerBitWidth()
                    assert w == dst._dtype.bit_length(), (src, dst, w, dst._dtype.bit_length(), dst._dtype)
                    off = 0
                    b: IRBuilder = toLlvm.b
                    for memberHwIo in dst._hwIOs:
                        w = memberHwIo._dtype.bit_length()
                        memberSrc = b.CreateBitRangeGetConst(src, off, w)
                        curBlock = self._storeToHwSignal(curBlock, memberHwIo, memberSrc)
                        off += w
                    return curBlock

                dst = dst._sig

            toLlvm._variableInBlock_insertRedef(curBlock, dst, (), src)
            return curBlock
        else:
            _src = src.data if srcIsRead else src
            # inlined part of visit_Assignment
            # src is now of scalar type
            # this may result in:
            # * store instruction
            # * just the registration of the variable for the symbol
            #   * only a segment in bit vector can be assigned, this result in the assignment of the concatenation of previous and new value
            if isinstance(dst, HwIOArray):
                # this is assing of array to array
                # in this case we have to first load all values from src
                # and then store it to dst
                # because the dst may contain refernces used in src and we have to perform the store atomically
                # with original values, not the partially updated src because of src references in dst
                block, src = self._storeToHwSignalArrayLoad(curBlock, src)
                self._storeToHwSignalArrayStore(block, dst, src)
                return block
            elif isinstance(dst._dtype, HArray):
                # this is assign of array which is represented by scalar
                block, src = toLlvm._translateExprToLlvm(curBlock, src)
                toLlvm._variableInBlock_insertRedef(curBlock, dst, (), src)
                return block
            else:
                stm = dst(_src)
                return toLlvm.visit_Assignments(curBlock, stm)

    def opcode_STORE_ATTR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        stack = frame.stack
        dstParent = stack.pop()
        dst = getattr(dstParent, instr.argval, None)
        src = stack.pop()
        curBlock, src = expandBeforeUse(self, instr.offset, frame, src, curBlock)
        if isinstance(src, HlsRead):
            self.toLlvm.visit_Read(curBlock, src)

        if isinstance(dst, (RtlSignal, HwIO, ObjectWithHlsStoreOverride)):
            # stm = self.hls.write(src, dst)
            return self._storeToHwSignal(curBlock, dst, src)
        else:
            setattr(dstParent, instr.argval, src)
            return curBlock
    
    def _shareNameWithRtlSignal(self, v:Union[RtlSignal, HwIO] , name:str):
        # only if it is a hw variable, create assignment to HW variable
        if isinstance(v, RtlSignal) and v._hasGenericName:
            v._name = name
            v._hasGenericName = False
        elif isinstance(v, HwIO) and v._name is None:
            v._name = name

    def _STORE_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, arg: int, argval: str) -> BasicBlock:
        stack = frame.stack
        localsplus = frame.localsplus
        vVal = stack.pop()
        curBlock, vVal = expandBeforeUse(self, instr.offset, frame, vVal, curBlock)
        varIndex = arg
        v = localsplus[varIndex]
        if varIndex not in frame.preprocVars:
            # if it is new definition of HW variable
            if v is NULL:
                if isinstance(vVal, self.ANY_HWVALUE_CLASS):
                    # check for initial store of HW variable to a python localsplus
                    isInitialStore = isinstance(vVal, RtlSignal) and vVal._rtlCtx is self.hls._rtlCtx and not vVal._rtlDrivers
                    # :note: for initial stores of already generated variables we ommit create of new variable and use original
                    #     variable directly to represent this variable
                    if not isInitialStore:
                        # only if it is a value which generates HW variable
                        v = self._initializeStorageCellForHwSignal(argval, vVal)
                        localsplus[varIndex] = v

                        
            if isinstance(v, (RtlSignal, HwIO, ObjectWithHlsStoreOverride)):
                self._shareNameWithRtlSignal(v, argval)
                return self._storeToHwSignal(curBlock, v, vVal)

        if isinstance(vVal, PyBytecodeInPreproc):
            vVal = vVal.ref
            frame.preprocVars.add(varIndex)

        if isinstance(vVal, HlsRead):
            self.toLlvm.visit_Read(curBlock, vVal)

        localsplus[varIndex] = vVal
        return curBlock

    def opcode_STORE_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Stores STACK.pop() into the local co_varnames[var_num].
        """
        return self._STORE_FAST(frame, curBlock, instr, instr.arg, instr.argval)

    def opcode_STORE_FAST_STORE_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Stores STACK[-1] into co_varnames[var_nums >> 4] and STACK[-2] into co_varnames[var_nums & 15].

        Added in version 3.13.
        """
        curBlock = self._STORE_FAST(frame, curBlock, instr, instr.arg >> 4, instr.argval[0])
        curBlock = self._STORE_FAST(frame, curBlock, instr, instr.arg & 0xF, instr.argval[1])
        return curBlock

    def opcode_STORE_FAST_LOAD_FAST(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Stores STACK.pop() into the local co_varnames[var_nums >> 4] and pushes a reference to the local co_varnames[var_nums & 15] onto the stack.

        Added in version 3.13.
        """
        curBlock = self._STORE_FAST(frame, curBlock, instr, instr.arg >> 4, instr.argval[0])
        curBlock = self._LOAD_FAST(frame, curBlock, instr.arg & 0xF, instr.argval[1])
        return curBlock

    def opcode_COPY_FREE_VARS(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        # Copy closure variables to free variables
        # co = frame.fn.__code__
        closure = frame.fn.__closure__
        assert len(closure) == instr.arg, (len(closure), instr.arg)
        offset = len(frame.localsplus) - len(closure)
        assert offset >= 0, offset
        # assert instr.arg == co.co_nfreevars
        for i, o in enumerate(closure):
            frame.localsplus[offset + i] = o
        return curBlock

    def _translateCallInlined(self, frame: PyBytecodeFrame, curBlock: BasicBlock,
                              fn: FunctionType, callSiteAddress: int, fnArgs: list, fnKwargs: dict):
        # create function entry point block, assign to all function parameters and prepare frame where we initialize preproc/hw variable meta
        # for variables from arguments
        fnName = getattr(fn, "__qualname__", fn.__name__)
        toLlvm = self.toLlvm
        with self.dbgTracer.scoped("inlining", fnName):
            if self.debugBytecode:
                d = toLlvm._dbgRootDir / toLlvm._dbgSubDir
                d.mkdir(exist_ok=True)
                with open(d / f"00.bytecode.{fnName}.txt", "w") as f:
                    dis(fn, file=f)

            curBlockLabel = self.blockToLabel[curBlock]
            callFrame = PyBytecodeFrame.fromFunction(fn, curBlockLabel, callSiteAddress, fnArgs, fnKwargs, self.callStack)

            fnEntryBlockLabel = callFrame.blockTracker._getBlockLabel(0)
            # _fnEntryBlockLabel = fnEntryBlockLabel
            fnEntryBlock, fnEntryBlockIsNew = self._getOrCreateBasicBlock(fnEntryBlockLabel)
            assert fnEntryBlockIsNew, "Must not reuse other existing block because every inline should generate new blocks only"
            builder: IRBuilder = toLlvm.b
            assert curBlock.getTerminator() is None, curBlock
            builder.SetInsertPoint(curBlock)
            builder.CreateBr(fnEntryBlock)
            builder.SetInsertPoint(fnEntryBlock)

            if self.debugCfgGen:
                self._debugDump(callFrame, label=callFrame.fn.__name__)
            try:
                self._translateBytecodeBlock(callFrame, callFrame.bytecodeBlocks[0], fnEntryBlock)
            finally:
                if self.debugCfgGen:
                    self._debugDump(callFrame, label=callFrame.fn.__name__)

            curBlockAfterCall = BasicBlock.Create(toLlvm.ctx, toLlvm.strCtx.addTwine(f"{curBlock.getName().str():s}_afterCall"), toLlvm.llvm.main, None)
            self.labelToBlock[curBlockLabel].end = curBlockAfterCall
            self.blockToLabel[curBlockAfterCall] = curBlockLabel
            # iterate return points in frame and jump to curBlockAfterCall
            finalRetVal = None
            first = True
            for (_, retBlock, retVal) in callFrame.returnPoints:
                if first:
                    first = False
                elif not _isSameOrIsSameTuple(finalRetVal, retVal):
                    raise NotImplementedError("Currently function can return only a single instance from any return.", callFrame.returnPoints)

                if retVal is not None:
                    finalRetVal = retVal

                assert retBlock.getTerminator() is None, curBlock
                builder.SetInsertPoint(retBlock)
                builder.CreateBr(curBlockAfterCall)

            self.dbgTracer.log(("inlining return from", fnName, finalRetVal))
            # retTy = fn.__annotations__.get("return")

            frame.stack.append(finalRetVal)
            # todo process return points and connected to curBlockAfterCall block in cfg
            self.callStack.pop()
            builder.SetInsertPoint(curBlockAfterCall)

            return curBlockAfterCall

    def opcode_IS_OP(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Performs is comparison, or is not if invert is 1.
        New in version 3.9.
        """
        stack = frame.stack
        v1 = stack.pop()
        v0 = stack.pop()
        invert = instr.argval
        if invert:
            res = v0 is not v1
        else:
            res = v0 is v1
        stack.append(res)
        return curBlock

    def opcode_RESUME(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        A no-op. Performs internal tracing, debugging and optimization checks.
        The context oparand consists of two parts. The lowest two bits indicate where the RESUME occurs:
    
            0 The start of a function, which is neither a generator, coroutine nor an async generator
            1 After a yield expression
            2 After a yield from expression
            3 After an await expression
    
        The next bit is 1 if the RESUME is at except-depth 1, and 0 otherwise.
        Changed in version 3.13: The oparg value changed to include information about except-depth
        """
        if instr.arg != 0:
            raise NotImplementedError(instr.arg)
        return curBlock

    def _CALL(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, kwnames: Optional[tuple[str]]) -> BasicBlock:
        stack = frame.stack
        argCnt = instr.arg
        if argCnt == 0:
            args = []
        else:
            args = stack[-argCnt:]
            for _ in range(argCnt):
                stack.pop()

        _self = stack.pop()
        callableV = stack.pop()
        assert callableV is not NULL, instr

        kwargs = {}
        if kwnames is not None:
            expandArgs = self._shouldExpandArgsOfFn(callableV)
            kwArgCnt = len(kwnames)  # kwargs are stored behind args
            for kwName, a in zip(kwnames, args[-kwArgCnt:]):
                if expandArgs:
                    curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
                kwargs[kwName] = a
            del args[-kwArgCnt:]

        elif callableV is setattr and isinstance(getattr(args[0], args[1], None), self.ANY_HWVALUE_CLASS):
            # instead of call of setattr store to variable on llvm level
            assert len(args) == 3, args
            assert len(kwargs) == 0, kwargs
            curValue = getattr(args[0], args[1])
            if isinstance(curValue, HwIOSignal):
                curValue = curValue._sig
            value = args[2]

            if not isinstance(value, (RtlSignal, Value, HwIOSignal, HConst)):
                value = toHVal(value, suggestedType=curValue._dtype)

            toLlvm = self.toLlvm
            curBlock, src = toLlvm._translateExprToLlvm(curBlock, value)
            toLlvm._variableInBlock_insertRedef(curBlock, curValue, (), src)
            res = None

        if isinstance(_self, PyBytecodeInline) and callableV == _self.__call__.__func__:
            return self._translateCallInlined(frame, curBlock, _self.ref, instr.offset, args, kwargs)
        elif isinstance(callableV, PyBytecodeInline):
            return self._translateCallInlined(frame, curBlock, callableV.ref, instr.offset, args, kwargs)
        elif callableV is PyBytecodePreprocHwCopy:
            assert len(args) == 1, args
            curBlock, res = self.toLlvm._translateExprToLlvm(curBlock, args[0])

        else:
            hlsCallOverride = getattr(callableV, "hlsCallOverride", None)
            if getattr(callableV, "__hlsIsLowLevelFn", False):
                if hlsCallOverride is not None:
                    # call override function instead original method
                    res = hlsCallOverride(self, frame, curBlock, instr, _self, callableV, args, kwargs)
                else:
                    # low level function will get raw arguments with any expansion
                    if _self is NULL:
                        res = callableV(*args, **kwargs)
                    else:
                        res = callableV(_self, *args, **kwargs)
            else:
                curBlock, expandedArgs = expandBeforeUseSequence(self, instr.offset, frame, args, curBlock)
                if hlsCallOverride is not None:
                    # call override function instead original method
                    res = hlsCallOverride(self, frame, curBlock, instr, _self, callableV, expandedArgs, kwargs)
                else:
                    # call function with args expanded
                    if _self is NULL:
                        res = callableV(*expandedArgs, **kwargs)
                    else:
                        res = callableV(_self, *expandedArgs, **kwargs)

        stack.append(res)
        return curBlock

    def opcode_CALL(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Calls a callable object with the number of arguments specified by argc. On the stack are (in ascending order):
    
            The callable
            self or NULL
            The remaining positional arguments
    
        argc is the total of the positional arguments, excluding self.
        CALL pops all arguments and the callable object off the stack, calls the callable object with those arguments,
        and pushes the return value returned by the callable object.
        Changed in version 3.13: The callable now always appears at the same position on the stack.
        Changed in version 3.13: Calls with keyword arguments are now handled by CALL_KW.

        """
        return self._CALL(frame, curBlock, instr, None)

    def opcode_CALL_KW(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Calls a callable object with the number of arguments specified by argc, including one or more named arguments.
        On the stack are (in ascending order):
    
            The callable
            self or NULL
            The remaining positional arguments
            The named arguments
            A tuple of keyword argument names
    
        argc is the total of the positional and named arguments, excluding self. The length of
        the tuple of keyword argument names is the number of named arguments.
    
        CALL_KW pops all arguments, the keyword names, and the callable object off the stack,
        calls the callable object with those arguments, and pushes the return value returned by the callable object.
    
        Added in version 3.13.
        """
        kwnames = frame.stack.pop()
        return self._CALL(frame, curBlock, instr, kwnames)

    def opcode_CALL_FUNCTION_EX(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Calls a callable object with variable set of positional and keyword arguments. If the lowest bit of flags is set, 
        the top of the stack contains a mapping object containing additional keyword arguments. Before the callable is called,
        the mapping object and iterable object are each “unpacked” and their contents passed in as keyword and positional arguments
        respectively. CALL_FUNCTION_EX pops all arguments and the callable object off the stack, calls the callable object
        with those arguments, and pushes the return value returned by the callable object.

        New in version 3.6.

        """
        stack = frame.stack

        if instr.arg & 0b1:
            kwargs = stack.pop()
        else:
            kwargs = {}
        args = stack.pop()

        _self = stack.pop()
        m = stack.pop()
        assert m is not NULL, ("callable must be initialized")
        expandArgs = self._shouldExpandArgsOfFn(m)
        if expandArgs:
            curBlock, args = expandBeforeUseSequence(self, instr.offset, frame, args, curBlock)
            kwargs = {}
            for kwName, a in kwargs.items():
                curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
                kwargs[kwName] = a

        if isinstance(m, PyBytecodeInline):
            return self._translateCallInlined(frame, curBlock, m.ref, instr.offset, args, kwargs)
        elif m is PyBytecodePreprocHwCopy:
            assert len(args) == 1, args
            assert not kwargs, kwargs
            curBlock, res, = self.toLlvm._translateExprToLlvm(curBlock, args[0])
        else:
            if _self is NULL:
                res = m(*args, **kwargs)
            else:
                res = m(_self, *args, **kwargs)

        stack.append(res)
        return curBlock

    def opcode_CALL_INTRINSIC_1(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        "v3.12"
        stack = frame.stack
        try:
            fn = CALL_INTRINSIC_1_FUNCTIONS[instr.argval]
        except KeyError:
            raise NotImplementedError(instr)

        a = stack.pop()
        stack.append(fn(a))
        return curBlock

    def _shouldExpandArgsOfFn(self, fn):
        return not isinstance(fn, PyBytecodeInline) and \
            fn is not PyBytecodePreprocHwCopy and \
            not getattr(fn, "__hlsIsLowLevelFn", False)

    def opcode_COMPARE_OP(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Performs a Boolean operation. The operation name can be found in cmp_op[opname >> 5].
        If the fifth-lowest bit of opname is set (opname & 16), the result should be coerced to bool.

        Changed in version 3.13: The fifth-lowest bit of the oparg now indicates a forced conversion to bool.
        """

        stack = frame.stack
        # https://github.com/python/cpython/issues/117270
        binOp = CMP_OPS[instr.arg >> 5]
        b = stack.pop()
        a = stack.pop()
        curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        curBlock, b = expandBeforeUse(self, instr.offset, frame, b, curBlock)
        res = binOp(a, b)
        toBool = instr.arg & 16
        if toBool and not isinstance(res, self.ANY_HWVALUE_CLASS):
            res = bool(res)
        stack.append(res)
        return curBlock

    def opcode_GET_ITER(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        stack = frame.stack
        a = stack.pop()
        curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        it = iter(a)
        stack.append(it)
        if isinstance(it, HwIterator):
            self.dbgTracer.log(("for loop hw iterator", curBlock.getName().str()))
            curBlock = it.hwInit(self, frame, curBlock)
        return curBlock

    def opcode_EXTENDED_ARG(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        return curBlock

    def opcode_UNPACK_SEQUENCE(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        stack = frame.stack
        seq = stack.pop()
        curBlock, seq = expandBeforeUse(self, instr.offset, frame, seq, curBlock)
        stack.extend(reversed(tuple(seq)))
        return curBlock

    def opcode_MAKE_FUNCTION(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        MAKE_FUNCTION
    
        Pushes a new function object on the stack built from the code object at STACK[-1].
    
        Changed in version 3.13: Extra function attributes on the stack, signaled by oparg flags, were removed.
            They now use SET_FUNCTION_ATTRIBUTE.
        """
        stack = frame.stack
        code = stack.pop()

        if code.co_freevars:
            # https://github.com/python/cpython/blob/3.13/Objects/funcobject.c#L945
            closure = stack[-1]  # :attention: the closure is required for FunctionType() but doc does not specify how to get it
            # it seems that the check is deprecated,
            # for now assme that this instr is followed by SET_FUNCTION_ATTRIBUTE closure
            assert len(closure) == len(code.co_freevars) and isinstance(closure[0], CellType), (instr, closure)
        else:
            closure = None
        # https://github.com/keras-team/keras/blob/c2bc6cfcc79d958d2e5a9bc0c829486d5a7fd0ac/keras/src/utils/python_utils.py#L104
        # PyCodeObject *code, PyObject *globals,
        # PyObject *name, PyObject *defaults, PyObject *closure
        # https://github.com/python/cpython/blob/main/Objects/clinic/funcobject.c.h#L209
        # https://github.com/python/cpython/blob/00026d19c272d1cf3527027bd6f9de910ff45070/Objects/clinic/funcobject.c.h#L204
        newFn = FunctionType(code, frame.fn.__globals__, name=code.co_name, closure=closure)

        stack.append(newFn)
        return curBlock

    def opcode_SET_FUNCTION_ATTRIBUTE(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        SET_FUNCTION_ATTRIBUTE(flag)
    
        Sets an attribute on a function object. Expects the function at STACK[-1] and the attribute value to set at STACK[-2];
        consumes both and leaves the function at STACK[-1]. The flag determines which attribute to set:
    
            * 0x01 a tuple of default values for positional-only and positional-or-keyword parameters in positional order
            * 0x02 a dictionary of keyword-only parameters’ default values
            * 0x04 a tuple of strings containing parameters’ annotations
            * 0x08 a tuple containing cells for free variables, making a closure
    
        Added in version 3.13.
        """
        flag = instr.arg
        stack = frame.stack
        fn = stack.pop()
        attr = stack.pop()

        if flag & 1:
            # a tuple of default values for positional-only and positional-or-keyword parameters in positional order
            fn.__dict__["__defaults__"] = attr
        elif flag & 2:
            # a dictionary of keyword-only parameters’ default values
            fn.__dict__["__kwdefaults__"] = attr
        elif flag & 4:
            fn.__dict__["__closure__"] = attr
        elif flag & 8:
            # a tuple of strings containing parameters’ annotations
            # Changed in version 3.10: Flag value 0x04 is a tuple of strings instead of dictionary
            fn.__dict__["__annotations__"] = attr
        else:
            raise AssertionError(instr)

        stack.append(fn)
        return curBlock

    def opcode_STORE_SUBSCR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction, key=NULL) -> BasicBlock:
        """
        Implements:

        key = STACK.pop()
        container = STACK.pop()
        value = STACK.pop()
        container[key] = value
        """
        stack = frame.stack
        if key is NULL:
            key = stack.pop()
        container = stack.pop()
        value = stack.pop()
        curBlock, key = expandBeforeUse(self, instr.offset, frame, key, curBlock)
        curBlock, value = expandBeforeUse(self, instr.offset, frame, value, curBlock)

        if isinstance(key, (RtlSignal, Value, HwIOSignal)) and \
                not isinstance(container, (RtlSignal, Value, HwIOSignal)):
            if not isinstance(container, PyObjectHwSubscriptRef):
                container = PyObjectHwSubscriptRef(instr.offset, container, key)
            return container.expandSetitemAsSwitchCase(self, instr.offset, frame, curBlock,
                                                       lambda i, dst: dst(value))

        if isinstance(container, (RtlSignal, HwIOSignal)):
            if isinstance(container, HwIOSignal):
                container = container._sig
            toLlvm: ToLlvmIrTranslator = self.toLlvm
            if not isinstance(key, (RtlSignal, Value, HwIOSignal, HConst)):
                if isinstance(key, slice):
                    key = slice_to_HSlice(key, container._dtype.bit_length())
                else:
                    key = toHVal(key)

            if not isinstance(value, (RtlSignal, Value, HwIOSignal, HConst)):
                value = toHVal(value, suggestedType=container[0]._dtype)

            curBlock, src = toLlvm._translateExprToLlvm(curBlock, value)
            toLlvm._variableInBlock_insertRedef(curBlock, container, (key,), src)

            return curBlock

        elif isinstance(value, HlsRead):
            self.toLlvm.visit_Read(curBlock, value)

        elif isinstance(container, HwIOArray):
            curItem = container[key]
            return self._storeToHwSignal(curBlock, curItem, value)

        operator.setitem(container, key, value)
        # stack.append()
        return curBlock

    def opcode_STORE_SLICE(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Implements:
    
        end = STACK.pop()
        start = STACK.pop()
        container = STACK.pop()
        values = STACK.pop()
        container[start:end] = value
    
        Added in version 3.12.
        """
        key, curBlock = self._popSliceFromStack(frame, curBlock, instr)
        return self.opcode_STORE_SUBSCR(frame, curBlock, instr, key=key)

    def opcodeMakeInplaceUpdate(self, updateOp: Callable):
        if updateOp == dict.__setitem__:

            # MAP_ADD
            def opcodeInplaceUpdate_MAP_ADD(frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
                """
                Used to implement dict comprehensions.
                
                value = STACK.pop()
                key = STACK.pop()
                dict.__setitem__(STACK[-i], key, value)
                """
                stack = frame.stack
                value = stack.pop()
                key = stack.pop()
                TOS1_mI = stack[self._stackIndex(stack, instr.argval)]
                updateOp(TOS1_mI, key, value)
                return curBlock

            return opcodeInplaceUpdate_MAP_ADD
        else:

            def opcodeInplaceUpdate(frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
                """
                Calls updateOp(TOS1[-i], TOS)
                """
                stack = frame.stack
                TOS = stack.pop()
                TOS1_mI = stack[self._stackIndex(stack, instr.argval)]
                updateOp(TOS1_mI, TOS)
                return curBlock

            return opcodeInplaceUpdate

    def opcodeMakeUnaryOp(self, unOp: Callable):

        def opcode_UN_OP(frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
            stack = frame.stack
            a = stack.pop()
            curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
            stack.append(unOp(a))
            return curBlock

        return opcode_UN_OP

    def opcodeMakeBuildOp(self, buildOp: Callable[[Instruction, list], None]):

        def opcode_BUILD_OP(frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
            buildOp(instr, frame.stack)
            return curBlock

        return opcode_BUILD_OP

    def opcode_TO_BOOL(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        stack = frame.stack
        a = stack[-1]
        if not isinstance(a, self.ANY_HWVALUE_CLASS):
            a = stack.pop()
            curBlock, a = expandBeforeUse(self, instr.offset, frame, a, curBlock)
            stack.append(bool(a))
        return curBlock

    def opcode_CONVERT_VALUE(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Convert value to a string, depending on oparg:

        value = STACK.pop()
        result = func(value)
        STACK.append(result)
        
            oparg == 1: call str() on value
            oparg == 2: call repr() on value
            oparg == 3: call ascii() on value
        
        Used for implementing formatted string literals (f-strings).
        """
        oparg = instr.arg
        if oparg == 1:
            func = str
        elif oparg == 2:
            func = repr
        else:
            assert oparg == 3
            func = ascii
        value = frame.stack.pop()
        result = func(value)
        frame.stack.append(result)
        return curBlock

    def opcode_FORMAT_SIMPLE(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Formats the value on top of stack:
    
            value = STACK.pop()
            result = value.__format__("")
            STACK.append(result)
    
        Used for implementing formatted string literals (f-strings).
    
        Added in version 3.13.
        """
        v = frame.stack.pop()
        res = v.__format__("")
        frame.stack.append(res)
        return curBlock

    def opcode_FORMAT_WITH_SPEC(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        FORMAT_WITH_SPEC
    
        Formats the given value with the given format spec:
    
            spec = STACK.pop()
            value = STACK.pop()
            result = value.__format__(spec)
            STACK.append(result)
    
        Used for implementing formatted string literals (f-strings).
    
        Added in version 3.13.
        """
        spec = frame.stack.pop()
        v = frame.stack.pop()
        res = v.__format__(spec)
        frame.stack.append(res)
        return curBlock

    def opcode_RAISE_VARARGS(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Raises an exception using one of the 3 forms of the raise statement, depending on the value of argc:

        0: raise (re-raise previous exception)
        1: raise TOS (raise exception instance or type at TOS)
        2: raise TOS1 from TOS (raise exception instance or type at TOS1 with __cause__ set to TOS)
        """
        if instr.argval == 0:
            raise
        elif instr.argval == 1:
            raise frame.stack.pop()
        elif instr.argval == 2:
            TOS = frame.stack.pop()
            TOS1 = frame.stack.pop()
            raise TOS1 from TOS
        else:
            raise NotImplementedError()
        return curBlock

    def opcode_PUSH_NULL(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        frame.stack.append(NULL)
        return curBlock

    def opcode_LOAD_ASSERTION_ERROR(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        frame.stack.append(AssertionError)
        return curBlock

    def opcode_LOAD_BUILD_CLASS(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        frame.stack.append(builtins.__build_class__)
        return curBlock

    def opcode_MAKE_CELL(self, frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction) -> BasicBlock:
        """
        Creates a new cell in slot i. If that slot is nonempty then that value is stored into the new cell.
        New in version 3.11.
        """
        v = frame.localsplus[instr.arg]
        if isinstance(v, CellType):
            pass
        else:
            frame.localsplus[instr.arg] = CellType(v)

        return curBlock
