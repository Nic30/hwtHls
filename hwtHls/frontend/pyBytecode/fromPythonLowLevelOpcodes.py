import builtins
from dis import Instruction, dis
from inspect import ismethod
import operator
from pathlib import Path
from types import FunctionType, CellType, MethodType
from typing import Callable, Dict, Union, Optional

from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hwIO import HwIO
from hwt.hwIOs.std import HwIOSignal
from hwt.mainBases import HwIOBase
from hwt.pyUtils.arrayQuery import flatten
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.indexExpansion import expandBeforeUse, \
    PyObjectHwSubscriptRef, expandBeforeUseSequence
from hwtHls.frontend.pyBytecode.instructions import CMP_OPS, BINARY_OPS, UN_OPS, BUILD_OPS, BINARY_OP, NOP, \
    POP_TOP, COPY, SWAP, LOAD_DEREF, LOAD_ATTR, LOAD_FAST, LOAD_CONST, LOAD_GLOBAL, \
    LOAD_METHOD, LOAD_CLOSURE, STORE_ATTR, STORE_FAST, STORE_DEREF, CALL, CALL_FUNCTION_EX, CALL_INTRINSIC_1, \
    COMPARE_OP, GET_ITER, UNPACK_SEQUENCE, MAKE_FUNCTION, STORE_SUBSCR, EXTENDED_ARG, DELETE_DEREF, DELETE_FAST, \
    FORMAT_VALUE, IS_OP, RAISE_VARARGS, LOAD_ASSERTION_ERROR, \
    RESUME, MAKE_CELL, KW_NAMES, NULL, PUSH_NULL, BINARY_SUBSCR, COPY_FREE_VARS, \
    CONTAINS_OP, INPLACE_UPDATE_OPS, LOAD_BUILD_CLASS, BINARY_SLICE, STORE_SLICE, \
    LOAD_FAST_CHECK, LOAD_FAST_AND_CLEAR, END_FOR, CALL_INTRINSIC_1_FUNCTIONS
from hwtHls.frontend.pyBytecode.ioProxyAddressed import IoProxyAddressed
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInPreproc, \
    PyBytecodeInline, _PyBytecodePragma, PyBytecodePreprocHwCopy
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue
from hwtHls.frontend.pyBytecode.hwIterator import HwIterator


class PyBytecodeToSsaLowLevelOpcodes():
    """
    https://docs.python.org/3/library/dis.html
    https://github.com/zrax/pycdc
    """

    def __init__(self):
        self.opcodeDispatch: Dict[int, Callable[[], SsaBasicBlock]] = {
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
            LOAD_CONST: self.opcode_LOAD_CONST,
            LOAD_GLOBAL: self.opcode_LOAD_GLOBAL,
            LOAD_METHOD: self.opcode_LOAD_METHOD,
            STORE_ATTR: self.opcode_STORE_ATTR,
            STORE_FAST: self.opcode_STORE_FAST,
            COPY_FREE_VARS: self.opcode_COPY_FREE_VARS,
            RESUME: self.opcode_RESUME,
            CALL: self.opcode_CALL,
            CALL_FUNCTION_EX: self.opcode_CALL_FUNCTION_EX,
            CALL_INTRINSIC_1: self.opcode_CALL_INTRINSIC_1,
            COMPARE_OP: self.opcode_COMPARE_OP,
            GET_ITER: self.opcode_GET_ITER,
            EXTENDED_ARG: self.opcode_EXTENDED_ARG,
            UNPACK_SEQUENCE: self.opcode_UNPACK_SEQUENCE,
            MAKE_FUNCTION: self.opcode_MAKE_FUNCTION,
            STORE_SUBSCR: self.opcode_STORE_SUBSCR,
            STORE_SLICE: self.opcode_STORE_SLICE,
            FORMAT_VALUE: self.opcode_FORMAT_VALUE,
            IS_OP: self.opcode_IS_OP,
            RAISE_VARARGS: self.opcode_RAISE_VARARGS,
            PUSH_NULL: self.opcode_PUSH_NULL,
            LOAD_ASSERTION_ERROR: self.opcode_LOAD_ASSERTION_ERROR,
            LOAD_BUILD_CLASS: self.opcode_LOAD_BUILD_CLASS,
            MAKE_CELL: self.opcode_MAKE_CELL,
            KW_NAMES: self.opcodeMakeStoreForLater("_last_KW_NAMES"),
        }
        opD = self.opcodeDispatch
        for createFn, opcodes in [
                (self.opcodeMakeUnaryOp, UN_OPS),
                (self.opcodeMakeBuildOp, BUILD_OPS),
                (self.opcodeMakeInplaceUpdate, INPLACE_UPDATE_OPS),
            ]:
            for opcode, op in opcodes.items():
                opD[opcode] = createFn(op)

        self._last_KW_NAMES: Optional[Instruction] = None

    def _stackIndex(self, stack: list, index: int):
        # in C:
        # TOP    = stack_pointer[-1]
        # SECOND = stack_pointer[-2]
        # here in python:
        # TOP    = stack[-1] = stack[len(stack)-1] = item0
        # SECOND = stack[-2] = stack[len(stack)-2] = item1
        return len(stack) - index

    def opcode_NOP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

    def opcode_POP_TOP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        res = frame.stack.pop()
        res, curBlock = expandBeforeUse(self, instr.offset, frame, res, curBlock)
        if isinstance(res, HlsWrite):
            res: HlsWrite
            dst = res.dst
            if isinstance(dst, PyObjectHwSubscriptRef):
                hls = self.hls
                if isinstance(dst.sequence, IoProxyAddressed):
                    raise AssertionError(dst, "This should already been expanded when HlsWrite was generated")
                return dst.expandSetitemAsSwitchCase(self, instr.offset, frame, curBlock,
                                                     lambda i, _dst: hls.write(res._origSrc, _dst))

        toSsa = self.toSsa
        if isinstance(res, HlsWrite):
            curBlock = toSsa.visit_Write(curBlock, res)
        elif isinstance(res, HlsRead):
            curBlock, _ = toSsa.visit_expr(curBlock, res)
        elif isinstance(res, HdlAssignmentContainer):
            curBlock = toSsa.visit_Assignment(curBlock, res)
        elif self._isHwtCall(res):
            curBlock, _ = toSsa.visit_expr(curBlock, res)
        elif isinstance(res, (list, tuple)) and len(res) > 0 and isinstance(res[0], (HlsWrite, HlsRead, HdlAssignmentContainer)):
            # if this a list or tuple of objects left on stack try if objects inside should be translated to ssa
            curBlock = toSsa.visit_CodeBlock_list(curBlock, res)
        elif isinstance(res, _PyBytecodePragma):
            res.apply(self, frame, curBlock, instr)

        return curBlock

    def opcode_END_FOR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Removes the top two values from the stack.
        Equivalent to POP_TOP; POP_TOP. Used to clean up at the end of loops, hence the name.
        Added in version 3.12.
        """
        curBlock = self.opcode_POP_TOP(frame, curBlock, instr)
        curBlock = self.opcode_POP_TOP(frame, curBlock, instr)
        return curBlock

    def opcode_COPY(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Push the i-th item to the top of the stack. The item is not removed from its original location.
        New in version 3.11.
        """
        stack = frame.stack
        stack.append(stack[self._stackIndex(stack, instr.arg)])
        return curBlock

    def opcode_SWAP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

    def opcode_BINARY_SUBSCR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction, key=NULL) -> SsaBasicBlock:
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
        container, curBlock = expandBeforeUse(self, instr.offset, frame, container, curBlock)
        key, curBlock = expandBeforeUse(self, instr.offset, frame, key, curBlock)
        if (isinstance(key, (RtlSignal, HwIO, SsaValue)) and
            not isinstance(container, (RtlSignal, SsaValue, HConst))):
            # if this is indexing using hw value on non hw object we need to expand it to a switch-case on individual cases
            # must generate blocks for switch cases,
            # for this we need container to keep track of start/end for each block because we do not have this newly generated blocks in original CFG
            o = PyObjectHwSubscriptRef(instr.offset, container, key)
            stack.append(o)
            return curBlock

        stack.append(container[key])

        return curBlock

    def _popSliceFromStack(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        end = stack.pop()
        start = stack.pop()

        end, curBlock = expandBeforeUse(self, instr.offset, frame, end, curBlock)
        start, curBlock = expandBeforeUse(self, instr.offset, frame, start, curBlock)
        key = slice(start, end)
        return key, curBlock

    def opcode_BINARY_SLICE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

    def opcode_CONTAINS_OP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        CONTAINS_OP(invert)
        Performs in comparison, or not in if invert is 1.
        New in version 3.9.
        """
        stack = frame.stack
        b = stack.pop()
        a = stack.pop()
        a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        b, curBlock = expandBeforeUse(self, instr.offset, frame, b, curBlock)
        invert = instr.argval
        if invert:
            res = a not in b
        else:
            res = a in b
        stack.append(res)
        return curBlock

    def opcode_BINARY_OP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        isInplace, binOp = BINARY_OPS[instr.arg]

        b = stack.pop()
        if isInplace:
            b, curBlock = expandBeforeUse(self, instr.offset, frame, b, curBlock)
            a = stack.pop()
            if isinstance(a, PyObjectHwSubscriptRef):
                a: PyObjectHwSubscriptRef
                # we expand as a regular bin op, and store later in store_subscript
                a, curBlock = a.expandIndexOnPyObjAsSwitchCase(self, instr.offset, frame, curBlock)
                # .expandSetitemAsSwitchCase(frame, curBlock, lambda _, dst: dst(inplaceOp(dst, b)))
            stack.append(binOp(a, b))
        else:
            a = stack.pop()
            a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
            b, curBlock = expandBeforeUse(self, instr.offset, frame, b, curBlock)
            stack.append(binOp(a, b))

        return curBlock

    def opcode_DELETE_FAST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        localsplus = frame.localsplus
        v = localsplus[instr.arg]
        assert v is not NULL, "Delete of uninitalized"
        localsplus[instr.arg] = NULL
        return curBlock

    def opcode_DELETE_DEREF(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        v = frame.localsplus[instr.arg]
        assert v.get() is not NULL, "Delete of uninitalized"
        v.set(NULL)
        return curBlock

    def opcode_LOAD_CLOSURE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # nested scopes: access the cell object
        # Pushes a reference to the cell contained in slot i of the cell and free variable storage.
        # The name of the variable is co_cellvars[i] if i is less than the length of co_cellvars.
        # Otherwise it is co_freevars[i - len(co_cellvars)].
        v = frame.localsplus[instr.arg]
        assert isinstance(v, CellType), v
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_DEREF(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # nested scopes: access a variable through its cell object
        v = frame.localsplus[instr.arg]
        assert isinstance(v, CellType), (v, "LOAD_DEREF should be used only with Cell instances")
        _v = v.cell_contents
        assert _v is not NULL, (instr.argval, "used before defined")
        frame.stack.append(_v)
        return curBlock

    def opcode_STORE_DEREF(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        # nested scopes: access a variable through its cell object
        vVal = frame.stack.pop()
        vVal, curBlock = expandBeforeUse(self, instr.offset, frame, vVal, curBlock)
        v: CellType = frame.localsplus[instr.arg]
        assert isinstance(v, CellType), v
        _v = v.cell_contents
        preprocVarKey = instr.arg
        if preprocVarKey not in frame.preprocVars:
            if _v is NULL and isinstance(vVal, (HConst, RtlSignal, SsaValue)):
                # only if it is a value which generates HW variable
                t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                _v = self.hls.var(instr.argval, t)

            if isinstance(_v, (RtlSignal, HwIO)):
                # only if it is a hw variable, create assignment to HW variable
                v.cell_contents = _v
                return self._storeToHwSignal(curBlock, _v, vVal)

        if isinstance(vVal, PyBytecodeInPreproc):
            vVal = vVal.ref
            frame.preprocVars.add(preprocVarKey)

        v.cell_contents = vVal
        return curBlock

    def opcode_LOAD_ATTR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        LOAD_ATTR(namei)
    
        If the low bit of namei is not set, this replaces STACK[-1] with getattr(STACK[-1], co_names[namei>>1]).
        If the low bit of namei is set, this will attempt to load a method named co_names[namei>>1] from the STACK[-1] object. STACK[-1] is popped.
        This bytecode distinguishes two cases: if STACK[-1] has a method with the correct name, the bytecode pushes the unbound method and STACK[-1].
        STACK[-1] will be used as the first argument (self) by CALL when calling the unbound method. Otherwise, NULL and the object returned by the attribute lookup are pushed.
        Changed in version 3.12: If the low bit of namei is set, then a NULL or self is pushed to the stack before the attribute or unbound method respectively.
        """
        stack = frame.stack
        selfOrNull = instr.arg & 1
        v = stack[-1]
        v = getattr(v, instr.argval)
        stack[-1] = v
        if selfOrNull:
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
                    stack[-1] = NULL
                    stack.append(v)

        return curBlock

    def opcode_LOAD_FAST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction, check=False, clear=False) -> SsaBasicBlock:
        """
        Pushes a reference to the local co_varnames[var_num] onto the stack.

        Changed in version 3.12: This opcode is now only used in situations where the local variable is guaranteed
        to be initialized. It cannot raise UnboundLocalError.

        """
        v = frame.localsplus[instr.arg]
        if check:
            if v is NULL:
                raise UnboundLocalError(instr.argval, "used before defined")
        if clear:
            frame.localsplus[instr.arg] = NULL
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_FAST_CHECK(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        return self.opcode_LOAD_FAST(frame, curBlock, instr, check=True)

    def opcode_LOAD_FAST_AND_CLEAR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        return self.opcode_LOAD_FAST(frame, curBlock, instr, clear=True)

    def opcode_LOAD_CONST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        frame.stack.append(instr.argval)
        return curBlock

    def opcode_LOAD_GLOBAL(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Loads the global named co_names[namei>>1] onto the stack.
        Changed in version 3.11: If the low bit of namei is set, then a NULL is pushed to the stack before the global variable
        """
        if instr.arg & 0b1:
            frame.stack.append(NULL)

        if instr.argval in frame.fn.__globals__:
            v = frame.fn.__globals__[instr.argval]
        else:
            # assert instr.argval in builtins.__dict__, instr.argval
            v = builtins.__dict__[instr.argval]

        assert v is not NULL, (instr.argval, "used before defined")
        frame.stack.append(v)
        return curBlock

    def opcode_LOAD_METHOD(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Loads a method named co_names[namei] from the TOS object. TOS is popped. 
        This bytecode distinguishes two cases: if TOS has a method with the correct name,
        the bytecode pushes the unbound method and TOS. TOS will be used as
        the first argument (self) by CALL when calling the unbound method.
        Otherwise, NULL and the object return by the attribute lookup are pushed.
        New in version 3.7.
        """
        stack = frame.stack
        TOS = stack.pop()
        m = getattr(TOS, instr.argval)
        if isinstance(m, MethodType) and m.__self__ is None:
            # is unbound method
            stack.append(TOS)
        else:
            stack.append(NULL)
        stack.append(m)

        return curBlock

    def _storeToHwSignal(self, curBlock, dst: Union[RtlSignal, HwIOBase], src):
        srcIsRead = isinstance(src, HlsRead)
        if isinstance(src, SsaValue) and not srcIsRead:
            if isinstance(dst, HwIOBase):
                dst = dst._sig
            self.toSsa.m_ssa_u.writeVariable(dst, [], curBlock, src)
            return curBlock
        else:
            _src = src.data if srcIsRead else src
            stm = dst(_src)
            return self.toSsa.visit_CodeBlock_list(curBlock, flatten([stm, ]))

    def opcode_STORE_ATTR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        dstParent = stack.pop()
        dst = getattr(dstParent, instr.argval, None)
        src = stack.pop()
        src, curBlock = expandBeforeUse(self, instr.offset, frame, src, curBlock)
        if isinstance(dst, (RtlSignal, HwIO)):
            # stm = self.hls.write(src, dst)
            self._storeToHwSignal(curBlock, dst, src)
        else:
            setattr(dstParent, instr.argval, src)

        return curBlock

    def opcode_STORE_FAST(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        localsplus = frame.localsplus
        vVal = stack.pop()
        vVal, curBlock = expandBeforeUse(self, instr.offset, frame, vVal, curBlock)
        v = localsplus[instr.arg]
        varIndex = instr.arg
        if varIndex not in frame.preprocVars:
            if v is NULL and isinstance(vVal, (HConst, RtlSignal, HwIO, SsaValue, HwIO)):
                # only if it is a value which generates HW variable
                t = getattr(vVal, "_dtypeOrig", vVal._dtype)
                if isinstance(vVal, RtlSignal) and vVal.hasGenericName:
                    # add name also to right side of assignment because this is likely a variable definition and we want
                    # to name the defined value
                    vVal._name = instr.argval
                    vVal.hasGenericName = False
                v = self.hls.var(instr.argval, t)
                localsplus[varIndex] = v

            if isinstance(v, (RtlSignal, HwIO)):
                # only if it is a hw variable, create assignment to HW variable
                if isinstance(v, RtlSignal) and v.hasGenericName:
                    v._name = instr.argval
                    v.hasGenericName = False
                return self._storeToHwSignal(curBlock, v, vVal)

        if isinstance(vVal, PyBytecodeInPreproc):
            vVal = vVal.ref
            frame.preprocVars.add(varIndex)

        localsplus[varIndex] = vVal
        return curBlock

    def opcode_COPY_FREE_VARS(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

    def _translateCallInlined(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock,
                              fn: FunctionType, callSiteAddress: int, fnArgs: list, fnKwargs: dict):
        # create function entry point block, assign to all function parameters and prepare frame where we initialize preproc/hw variable meta
        # for variables from arguments
        fnName = getattr(fn, "__qualname__", fn.__name__)
        with self.dbgTracer.scoped("inlining", fnName):
            if self.debugBytecode:
                d = Path(self.debugDirectory) / self.toSsa.label
                d.mkdir(exist_ok=True)
                with open(d / f"00.bytecode.{fnName}.txt", "w") as f:
                    dis(fn, file=f)

            curBlockLabel = self.blockToLabel[curBlock]
            callFrame = PyBytecodeFrame.fromFunction(fn, curBlockLabel, callSiteAddress, fnArgs, fnKwargs, self.callStack)

            fnEntryBlockLabel = callFrame.blockTracker._getBlockLabel(0)
            # _fnEntryBlockLabel = fnEntryBlockLabel
            fnEntryBlock, fnEntryBlockIsNew = self._getOrCreateSsaBasicBlock(fnEntryBlockLabel)
            assert fnEntryBlockIsNew, "Must not reuse other existing block because every inline should generate new blocks only"
            curBlock.successors.addTarget(None, fnEntryBlock)

            if self.debugCfgGen:
                self._debugDump(callFrame, label=callFrame.fn.__name__)
            try:
                self._translateBytecodeBlock(callFrame, callFrame.bytecodeBlocks[0], fnEntryBlock)
            finally:
                if self.debugCfgGen:
                    self._debugDump(callFrame, label=callFrame.fn.__name__)

            curBlockAfterCall = SsaBasicBlock(self.toSsa.ssaCtx, f"{curBlock.label:s}_afterCall")
            self.labelToBlock[curBlockLabel].end = curBlockAfterCall
            self.blockToLabel[curBlockAfterCall] = curBlockLabel
            # iterate return points in frame and jump to curBlockAfterCall
            finalRetVal = None
            first = True
            for (_, retBlock, retVal) in callFrame.returnPoints:
                if first:
                    first = False
                elif finalRetVal is not retVal:
                    raise NotImplementedError("Currently function can return only a single instance from any return.", callFrame.returnPoints)

                if retVal is not None:
                    finalRetVal = retVal

                retBlock.successors.addTarget(None, curBlockAfterCall)
            self.dbgTracer.log(("inlining return from", fnName, finalRetVal))
            # retTy = fn.__annotations__.get("return")

            frame.stack.append(finalRetVal)
            # todo process return points and connected to curBlockAfterCall block in cfg
            self.callStack.pop()
            self._onAllPredecsKnown(frame, curBlockAfterCall)

            return curBlockAfterCall

    def opcode_IS_OP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

    def opcode_RESUME(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        A no-op. Performs internal tracing, debugging and optimization checks.
        The where operand marks where the RESUME occurs:
            0 The start of a function, which is neither a generator, coroutine nor an async generator
            1 After a yield expression
            2 After a yield from expression
            3 After an await expression
        """
        if instr.arg != 0:
            raise NotImplementedError(instr.arg)
        return curBlock

    def opcode_CALL(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        CALL(argc)
        Calls a callable object with the number of arguments specified by argc,
        including the named arguments specified by the preceding KW_NAMES, if any.
        On the stack are (in ascending order), either:
            NULL
            The callable
            The positional arguments
            The named arguments
        or:
            The callable
            self
            The remaining positional arguments
            The named arguments
    
        argc is the total of the positional and named arguments, excluding self when a NULL is not present.
        CALL pops all arguments and the callable object off the stack, calls the callable object with those arguments,
        and pushes the return value returned by the callable object.
        New in version 3.11.
        """
        stack = frame.stack

        argCnt = instr.arg
        if argCnt == 0:
            args = []
        else:
            args = stack[-argCnt:]

        for _ in range(argCnt):
            stack.pop()

        _self = stack.pop()
        assert _self is not NULL, ("callable/self must be initialized")
        m = stack.pop()
        if m is NULL:
            m = _self
            _self = NULL
        expandArgs = self._shouldExpandArgsOfFn(m)

        kwNames = self._last_KW_NAMES
        kwargs = {}
        if kwNames is not None:
            self._last_KW_NAMES = None
            kwNamesVal = frame.fn.__code__.co_consts[kwNames.arg]
            kwArgCnt = len(kwNamesVal)  # kwargs are stored behind args
            for kwName, a in zip(kwNamesVal, args[-kwArgCnt:]):
                if expandArgs:
                    a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
                kwargs[kwName] = a
            del args[-kwArgCnt:]

        if isinstance(_self, PyBytecodeInline) and m == _self.__call__.__func__:
            return self._translateCallInlined(frame, curBlock, _self.ref, instr.offset, args, kwargs)
        elif isinstance(m, PyBytecodeInline):
            return self._translateCallInlined(frame, curBlock, m.ref, instr.offset, args, kwargs)
        elif m is PyBytecodePreprocHwCopy:
            assert len(args) == 1, args
            assert not kwargs, (m, kwargs)
            curBlock, res, = self.toSsa.visit_expr(curBlock, args[0])
        else:
            if getattr(m, "__hlsIsLowLevelFn", False):
                if _self is NULL:
                    res = m(*args, **kwargs)
                else:
                    res = m(_self, *args, **kwargs)
            else:
                expandedArgs, curBlock = expandBeforeUseSequence(self, instr.offset, frame, args, curBlock)
                if _self is NULL:
                    res = m(*expandedArgs, **kwargs)
                else:
                    res = m(_self, *expandedArgs, **kwargs)

        stack.append(res)
        return curBlock

    def opcode_CALL_FUNCTION_EX(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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
        assert _self is not NULL, ("callable/self must be initialized")
        m = stack.pop()
        if m is NULL:
            m = _self
            _self = NULL
        expandArgs = self._shouldExpandArgsOfFn(m)
        if expandArgs:
            args, curBlock = expandBeforeUseSequence(self, instr.offset, frame, args, curBlock)
            kwargs = {}
            for kwName, a in kwargs.items():
                a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
                kwargs[kwName] = a

        if isinstance(m, PyBytecodeInline):
            return self._translateCallInlined(frame, curBlock, m.ref, instr.offset, args, kwargs)
        elif m is PyBytecodePreprocHwCopy:
            assert len(args) == 1, args
            assert not kwargs, kwargs
            curBlock, res, = self.toSsa.visit_expr(curBlock, args[0])
        else:
            if _self is NULL:
                res = m(*args, **kwargs)
            else:
                res = m(_self, *args, **kwargs)

        stack.append(res)
        return curBlock

    def opcode_CALL_INTRINSIC_1(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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
        return not isinstance(fn, PyBytecodeInline) and fn is not PyBytecodePreprocHwCopy and not getattr(fn, "__hlsIsLowLevelFn", False)

    def opcode_COMPARE_OP(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        # https://github.com/python/cpython/issues/117270
        binOp = CMP_OPS[instr.arg >> 4]
        b = stack.pop()
        a = stack.pop()
        a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        b, curBlock = expandBeforeUse(self, instr.offset, frame, b, curBlock)
        stack.append(binOp(a, b))
        return curBlock

    def opcode_GET_ITER(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        a = stack.pop()
        a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
        it = iter(a)
        stack.append(it)
        if isinstance(it, HwIterator):
            self.dbgTracer.log(("for loop hw iterator", curBlock.label))
            curBlock = it.hwInit(self, frame, curBlock)
        return curBlock

    def opcode_EXTENDED_ARG(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        return curBlock

    def opcode_UNPACK_SEQUENCE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        stack = frame.stack
        seq = stack.pop()
        stack.extend(reversed(tuple(seq)))
        return curBlock

    def opcode_MAKE_FUNCTION(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        MAKE_FUNCTION (flags)
        Pushes a new function object on the stack.  From bottom to top, the consumed
        stack must consist of values if the argument carries a specified flag value
        
        * ``0x01`` a tuple of default values for positional-only and
          positional-or-keyword parameters in positional order
        * ``0x02`` a dictionary of keyword-only parameters' default values
        * ``0x04`` a tuple of strings containing parameters' annotations
        * ``0x08`` a tuple containing cells for free variables, making a closure
        * the code associated with the function (at TOS)
        
        .. versionchanged:: 3.10
           Flag value ``0x04`` is a tuple of strings instead of dictionary
        
        .. versionchanged:: 3.11
           Qualified name at TOS was removed in favor of co_qualname usage
        """
        # MAKE_FUNCTION_FLAGS = ('defaults', 'kwdefaults', 'annotations', 'closure')
        stack = frame.stack
        # name = stack.pop()
        # assert isinstance(name, str), name
        code = stack.pop()

        if instr.arg & 1:
            # a tuple of default values for positional-only and positional-or-keyword parameters in positional order
            defaults = stack.pop()
        else:
            defaults = ()

        if instr.arg & (1 << 1):
            # a dictionary of keyword-only parameters’ default values
            raise NotImplementedError()

        if instr.arg & (1 << 2):
            # a tuple of strings containing parameters’ annotations
            # Changed in version 3.10: Flag value 0x04 is a tuple of strings instead of dictionary
            raise NotImplementedError()

        if instr.arg & (1 << 3):
            closure = stack.pop()
        else:
            closure = ()

        # PyCodeObject *code, PyObject *globals,
        # PyObject *name, PyObject *defaults, PyObject *closure
        newFn = FunctionType(code, frame.fn.__globals__, code.co_qualname, defaults, closure)
        stack.append(newFn)
        return curBlock

    def opcode_STORE_SUBSCR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction, key=NULL) -> SsaBasicBlock:
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
        key, curBlock = expandBeforeUse(self, instr.offset, frame, key, curBlock)
        value, curBlock = expandBeforeUse(self, instr.offset, frame, value, curBlock)

        if isinstance(key, (RtlSignal, SsaValue, HwIOSignal)) and not isinstance(container, (RtlSignal, SsaValue, HwIOSignal)):
            if not isinstance(container, PyObjectHwSubscriptRef):
                container = PyObjectHwSubscriptRef(instr.offset, container, key)
            return container.expandSetitemAsSwitchCase(self, instr.offset, frame, curBlock, lambda i, dst: dst(value))

        if isinstance(container, (RtlSignal, HwIOSignal)):
            if isinstance(key, (RtlSignal, SsaValue, HwIOSignal)):
                raise NotImplementedError()
            else:
                stm = container[key](value)
                self.toSsa.visit_CodeBlock_list(curBlock, flatten([stm, ]))
                return curBlock

        operator.setitem(container, key, value)
        # stack.append()
        return curBlock

    def opcode_STORE_SLICE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

        def opcodeInplaceUpdate(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

        def opcode_UN_OP(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            stack = frame.stack
            a = stack.pop()
            a, curBlock = expandBeforeUse(self, instr.offset, frame, a, curBlock)
            stack.append(unOp(a))
            return curBlock

        return opcode_UN_OP

    def opcodeMakeStoreForLater(self, attribName: str):

        def opcode_StoreForLater(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            setattr(self, attribName, instr)
            return curBlock

        return opcode_StoreForLater

    def opcodeMakeBuildOp(self, buildOp: Callable[[Instruction, list], None]):

        def opcode_BUILD_OP(frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
            buildOp(instr, frame.stack)
            return curBlock

        return opcode_BUILD_OP

    def opcode_FORMAT_VALUE(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        """
        Used for implementing formatted literal strings (f-strings). Pops an optional fmt_spec from the stack, then a required value. flags is interpreted as follows:
            (flags & 0x03) == 0x00: value is formatted as-is.
            (flags & 0x03) == 0x01: call str() on value before formatting it.
            (flags & 0x03) == 0x02: call repr() on value before formatting it.
            (flags & 0x03) == 0x03: call ascii() on value before formatting it.
            (flags & 0x04) == 0x04: pop fmt_spec from the stack and use it, else use an empty fmt_spec.

        Formatting is performed using PyObject_Format(). The result is pushed on the stack.
        New in version 3.6.
        """
        flags = instr.arg
        frmt = frame.stack.pop()
        v = frame.stack.pop()
        if (flags & 0x03) == 0x00:
            pass
        elif (flags & 0x03) == 0x01:
            v = str(v)
        elif (flags & 0x03) == 0x02:
            v = repr(v)
        elif (flags & 0x03) == 0x03:
            v = ascii(v)
        else:
            raise NotImplementedError(instr)

        frame.stack.append(format(v, frmt))
        return curBlock

    def opcode_RAISE_VARARGS(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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

    def opcode_PUSH_NULL(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        frame.stack.append(NULL)
        return curBlock

    def opcode_LOAD_ASSERTION_ERROR(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        frame.stack.append(AssertionError)
        return curBlock

    def opcode_LOAD_BUILD_CLASS(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
        frame.stack.append(builtins.__build_class__)
        return curBlock

    def opcode_MAKE_CELL(self, frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction) -> SsaBasicBlock:
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
